from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class LoginThrottleDecision:
    blocked: bool
    retry_after_seconds: int = 0


@dataclass
class _LimiterEntry:
    window_started_at: datetime
    failed_attempts: int = 0
    blocked_until: datetime | None = None


class LoginRateLimiter:
    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: int,
        block_seconds: int,
    ) -> None:
        self.max_attempts = max(1, int(max_attempts))
        self.window_seconds = max(60, int(window_seconds))
        self.block_seconds = max(60, int(block_seconds))
        self._entries: dict[str, _LimiterEntry] = {}

    def _now(self) -> datetime:
        return datetime.now()

    def _reset_window_if_needed(self, entry: _LimiterEntry, now: datetime) -> None:
        if now - entry.window_started_at >= timedelta(seconds=self.window_seconds):
            entry.window_started_at = now
            entry.failed_attempts = 0

    def _clear_if_idle(self, key: str, entry: _LimiterEntry, now: datetime) -> None:
        if entry.blocked_until and now < entry.blocked_until:
            return
        if now - entry.window_started_at >= timedelta(seconds=self.window_seconds):
            self._entries.pop(key, None)

    def evaluate(self, key: str) -> LoginThrottleDecision:
        now = self._now()
        entry = self._entries.get(key)
        if entry is None:
            return LoginThrottleDecision(blocked=False)
        if entry.blocked_until and now < entry.blocked_until:
            retry_after = max(1, int((entry.blocked_until - now).total_seconds()))
            return LoginThrottleDecision(blocked=True, retry_after_seconds=retry_after)
        self._clear_if_idle(key, entry, now)
        return LoginThrottleDecision(blocked=False)

    def record_failure(self, key: str) -> LoginThrottleDecision:
        now = self._now()
        decision = self.evaluate(key)
        if decision.blocked:
            return decision

        entry = self._entries.get(key)
        if entry is None:
            entry = _LimiterEntry(window_started_at=now)
            self._entries[key] = entry
        else:
            self._reset_window_if_needed(entry, now)

        entry.failed_attempts += 1
        if entry.failed_attempts >= self.max_attempts:
            entry.blocked_until = now + timedelta(seconds=self.block_seconds)
            retry_after = max(1, int((entry.blocked_until - now).total_seconds()))
            return LoginThrottleDecision(blocked=True, retry_after_seconds=retry_after)
        return LoginThrottleDecision(blocked=False)

    def record_success(self, key: str) -> None:
        self._entries.pop(key, None)
