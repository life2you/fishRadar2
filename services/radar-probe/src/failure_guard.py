"""Task-level failure circuit breaker backed by MySQL."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from src.infrastructure.persistence.mysql_connection import mysql_connection
from src.services.platform_settings_service import load_failure_guard_settings_sync


try:
    from zoneinfo import ZoneInfo  # py3.9+

    def _load_tz(name: str):
        return ZoneInfo(name)


except Exception:  # pragma: no cover

    def _load_tz(name: str):
        return None


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now(tz_name: str, now: Optional[datetime] = None) -> datetime:
    if now is not None:
        return now
    tz = _load_tz(tz_name)
    if tz is None:
        return datetime.now()
    return datetime.now(tz)


def _today_str(tz_name: str, now: Optional[datetime] = None) -> str:
    return _now(tz_name, now=now).date().isoformat()


def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat()


def _str_to_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _get_mtime(path: Optional[str]) -> Optional[float]:
    if not path:
        return None
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _cookie_changed(
    cookie_path: Optional[str], previous_mtime: Optional[float]
) -> bool:
    if not cookie_path:
        return False
    current = _get_mtime(cookie_path)
    if current is None or previous_mtime is None:
        return False
    return current > (previous_mtime + 1e-6)


@dataclass(frozen=True)
class SkipDecision:
    skip: bool
    should_notify: bool
    reason: str
    paused_until: Optional[datetime]
    consecutive_failures: int


class FailureGuard:
    def __init__(
        self,
        path: Optional[str] = None,
        *,
        threshold: Optional[int] = None,
        pause_seconds: Optional[int] = None,
        tz_name: Optional[str] = None,
    ):
        # `path` is kept only to avoid breaking older call sites; runtime state is stored in DB.
        configured = load_failure_guard_settings_sync()
        self.threshold = max(
            1,
            threshold
            or _as_int(configured.get("TASK_FAILURE_THRESHOLD"), 3),
        )
        self.pause_seconds = max(
            60,
            pause_seconds
            or _as_int(configured.get("TASK_FAILURE_PAUSE_SECONDS"), 24 * 60 * 60),
        )
        self.tz_name = (
            tz_name
            or str(configured.get("TASK_FAILURE_TZ") or "Asia/Shanghai")
        )

    def _default_entry(self, task_key: str, *, current: Optional[datetime] = None) -> dict:
        return {
            "task_key": task_key,
            "consecutive_failures": 0,
            "paused_until": None,
            "last_notified_date": None,
            "last_failure_reason": None,
            "last_failure_at": None,
            "last_success_at": None,
            "cookie_path": None,
            "cookie_mtime": None,
            "updated_at": _dt_to_str(current or _now(self.tz_name)),
        }

    def _ensure_row(self, conn, task_key: str, *, current: datetime) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO task_failure_guards (
                task_key, consecutive_failures, updated_at
            ) VALUES (?, 0, ?)
            """,
            (task_key, _dt_to_str(current)),
        )

    def _load_entry(
        self,
        conn,
        task_key: str,
        *,
        current: datetime,
        for_update: bool = False,
        create: bool = False,
    ) -> dict:
        if create:
            self._ensure_row(conn, task_key, current=current)
        query = """
            SELECT task_key, consecutive_failures, paused_until, last_notified_date,
                   last_failure_reason, last_failure_at, last_success_at,
                   cookie_path, cookie_mtime, updated_at
            FROM task_failure_guards
            WHERE task_key = ?
        """
        if for_update:
            query += " FOR UPDATE"
        row = conn.execute(query, (task_key,)).fetchone()
        if row is None:
            return self._default_entry(task_key, current=current)
        entry = self._default_entry(task_key, current=current)
        entry.update(dict(row))
        return entry

    def _save_entry(self, conn, entry: dict) -> None:
        conn.execute(
            """
            INSERT INTO task_failure_guards (
                task_key, consecutive_failures, paused_until, last_notified_date,
                last_failure_reason, last_failure_at, last_success_at,
                cookie_path, cookie_mtime, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                consecutive_failures = VALUES(consecutive_failures),
                paused_until = VALUES(paused_until),
                last_notified_date = VALUES(last_notified_date),
                last_failure_reason = VALUES(last_failure_reason),
                last_failure_at = VALUES(last_failure_at),
                last_success_at = VALUES(last_success_at),
                cookie_path = VALUES(cookie_path),
                cookie_mtime = VALUES(cookie_mtime),
                updated_at = VALUES(updated_at)
            """,
            (
                entry["task_key"],
                int(entry.get("consecutive_failures") or 0),
                entry.get("paused_until"),
                entry.get("last_notified_date"),
                entry.get("last_failure_reason"),
                entry.get("last_failure_at"),
                entry.get("last_success_at"),
                entry.get("cookie_path"),
                entry.get("cookie_mtime"),
                entry.get("updated_at"),
            ),
        )

    def record_success(self, task_key: str, *, now: Optional[datetime] = None) -> None:
        current = _now(self.tz_name, now=now)
        with mysql_connection() as conn:
            entry = self._default_entry(task_key, current=current)
            entry["last_success_at"] = _dt_to_str(current)
            self._save_entry(conn, entry)
            conn.commit()

    def should_skip_start(
        self,
        task_key: str,
        *,
        cookie_path: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> SkipDecision:
        current = _now(self.tz_name, now=now)
        today = _today_str(self.tz_name, now=current)

        with mysql_connection() as conn:
            entry = self._load_entry(
                conn,
                task_key,
                current=current,
                for_update=True,
                create=True,
            )

            paused_until = _str_to_dt(entry.get("paused_until"))
            consecutive = _as_int(entry.get("consecutive_failures"), 0)
            last_reason = (entry.get("last_failure_reason") or "").strip() or "未知错误"
            last_notified_date = entry.get("last_notified_date")

            previous_cookie_mtime = entry.get("cookie_mtime")
            try:
                previous_cookie_mtime = (
                    float(previous_cookie_mtime)
                    if previous_cookie_mtime is not None
                    else None
                )
            except (TypeError, ValueError):
                previous_cookie_mtime = None

            if (
                paused_until
                and paused_until > current
                and cookie_path
                and _cookie_changed(cookie_path, previous_cookie_mtime)
            ):
                reset_entry = self._default_entry(task_key, current=current)
                reset_entry["last_success_at"] = _dt_to_str(current)
                self._save_entry(conn, reset_entry)
                conn.commit()
                return SkipDecision(
                    skip=False,
                    should_notify=False,
                    reason="cookie_updated",
                    paused_until=None,
                    consecutive_failures=0,
                )

            if paused_until and current < paused_until:
                should_notify = last_notified_date != today
                if should_notify:
                    entry["last_notified_date"] = today
                    entry["updated_at"] = _dt_to_str(current)
                    self._save_entry(conn, entry)
                    conn.commit()

                return SkipDecision(
                    skip=True,
                    should_notify=should_notify,
                    reason=last_reason,
                    paused_until=paused_until,
                    consecutive_failures=consecutive,
                )

            return SkipDecision(
                skip=False,
                should_notify=False,
                reason="not_paused",
                paused_until=None,
                consecutive_failures=consecutive,
            )

    def record_failure(
        self,
        task_key: str,
        reason: str,
        *,
        cookie_path: Optional[str] = None,
        min_failures_to_pause: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> dict:
        current = _now(self.tz_name, now=now)
        today = _today_str(self.tz_name, now=current)
        cookie_mtime = _get_mtime(cookie_path)
        effective_threshold = max(1, int(min_failures_to_pause or self.threshold))

        result = {
            "should_notify": False,
            "opened_circuit": False,
            "paused_until": None,
            "consecutive_failures": 0,
        }

        with mysql_connection() as conn:
            entry = self._load_entry(
                conn,
                task_key,
                current=current,
                for_update=True,
                create=True,
            )

            previous_paused_until = _str_to_dt(entry.get("paused_until"))
            was_paused = bool(previous_paused_until and current < previous_paused_until)

            prev_mtime = entry.get("cookie_mtime")
            try:
                prev_mtime = float(prev_mtime) if prev_mtime is not None else None
            except (TypeError, ValueError):
                prev_mtime = None

            if cookie_path and _cookie_changed(cookie_path, prev_mtime):
                entry["consecutive_failures"] = 0
                entry["paused_until"] = None
                entry["last_notified_date"] = None

            consecutive = _as_int(entry.get("consecutive_failures"), 0) + 1
            entry["consecutive_failures"] = consecutive
            entry["last_failure_reason"] = (reason or "未知错误")[:1000]
            entry["last_failure_at"] = _dt_to_str(current)
            entry["updated_at"] = _dt_to_str(current)
            if cookie_path:
                entry["cookie_path"] = cookie_path
                if cookie_mtime is not None:
                    entry["cookie_mtime"] = cookie_mtime

            opened = False
            if consecutive >= effective_threshold:
                paused_until = current + timedelta(seconds=self.pause_seconds)
                entry["paused_until"] = _dt_to_str(paused_until)
                opened = not was_paused

                if entry.get("last_notified_date") != today:
                    entry["last_notified_date"] = today
                    result["should_notify"] = True

                result["paused_until"] = paused_until
            else:
                entry["paused_until"] = None

            self._save_entry(conn, entry)
            conn.commit()

            result["opened_circuit"] = opened
            result["consecutive_failures"] = consecutive
            return result
