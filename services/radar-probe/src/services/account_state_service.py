from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.infrastructure.config.settings import scraper_settings
from src.infrastructure.config.env_manager import env_manager
from src.infrastructure.persistence.mysql_connection import mysql_connection


ACCOUNT_STATE_KIND_ACCOUNT = "account"
ACCOUNT_STATE_KIND_DEFAULT = "default"
DEFAULT_LOGIN_STATE_NAME = "__default__"
RUNTIME_ACCOUNT_STATE_DIR = "data/runtime_state"

ACCOUNT_STATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS account_states (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '登录态记录ID',
    name VARCHAR(255) NOT NULL COMMENT '登录态名称',
    kind VARCHAR(32) NOT NULL COMMENT '登录态类型(account/default)',
    state_json LONGTEXT NOT NULL COMMENT '登录态JSON内容',
    created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
    updated_at VARCHAR(64) NOT NULL COMMENT '更新时间',
    UNIQUE KEY uniq_account_state_kind_name (kind, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='登录态存储表'
"""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _strip_quotes(value: str) -> str:
    if not value:
        return value
    if value.startswith(("\"", "'")) and value.endswith(("\"", "'")):
        return value[1:-1]
    return value


def get_legacy_account_state_dir() -> str:
    raw = env_manager.get_value("ACCOUNT_STATE_DIR", "state") or "state"
    return _strip_quotes(raw.strip()) or "state"


def get_runtime_account_state_dir() -> str:
    return RUNTIME_ACCOUNT_STATE_DIR


def get_runtime_default_state_file() -> str:
    return scraper_settings.state_file


def ensure_account_states_table(conn) -> None:
    conn.execute(ACCOUNT_STATES_TABLE_SQL)


def validate_state_json(content: str) -> str:
    text = str(content or "").strip()
    if not text:
        raise ValueError("登录态内容不能为空。")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("提供的内容不是有效的JSON格式。") from exc
    return json.dumps(parsed, ensure_ascii=False)


def build_account_reference(name: str) -> str:
    return f"state/{name}.json"


def parse_account_name_from_reference(reference: Optional[str]) -> Optional[str]:
    text = str(reference or "").strip()
    if not text:
        return None
    if text.startswith("account:"):
        text = text.split(":", 1)[1]
    text = text.replace("\\", "/")
    filename = text.rsplit("/", 1)[-1]
    if filename.endswith(".json"):
        filename = filename[:-5]
    return filename.strip() or None


def resolve_runtime_account_path(reference: Optional[str], *, runtime_dir: Optional[str] = None) -> Optional[str]:
    account_name = parse_account_name_from_reference(reference)
    if not account_name:
        return None
    base_dir = runtime_dir or get_runtime_account_state_dir()
    return str(Path(base_dir) / f"{account_name}.json")


def _list_account_rows_sync(*, kind: str) -> list[dict]:
    with mysql_connection() as conn:
        ensure_account_states_table(conn)
        rows = conn.execute(
            """
            SELECT id, name, kind, state_json, created_at, updated_at
            FROM account_states
            WHERE kind = ?
            ORDER BY name ASC
            """,
            (kind,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_account_states_sync() -> list[dict]:
    rows = _list_account_rows_sync(kind=ACCOUNT_STATE_KIND_ACCOUNT)
    return [
        {
            "name": row["name"],
            "path": build_account_reference(row["name"]),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
    ]


def get_account_state_sync(name: str) -> dict | None:
    with mysql_connection() as conn:
        ensure_account_states_table(conn)
        row = conn.execute(
            """
            SELECT id, name, kind, state_json, created_at, updated_at
            FROM account_states
            WHERE kind = ? AND name = ?
            LIMIT 1
            """,
            (ACCOUNT_STATE_KIND_ACCOUNT, name),
        ).fetchone()
    if row is None:
        return None
    payload = dict(row)
    return {
        "name": payload["name"],
        "path": build_account_reference(payload["name"]),
        "content": payload["state_json"],
        "updated_at": payload.get("updated_at"),
    }


def upsert_account_state_sync(name: str, content: str) -> dict:
    normalized_content = validate_state_json(content)
    now = _now_iso()
    with mysql_connection() as conn:
        ensure_account_states_table(conn)
        conn.execute(
            """
            INSERT INTO account_states (name, kind, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                state_json = VALUES(state_json),
                updated_at = VALUES(updated_at)
            """,
            (name, ACCOUNT_STATE_KIND_ACCOUNT, normalized_content, now, now),
        )
        conn.commit()
    return get_account_state_sync(name)


def delete_account_state_sync(name: str) -> bool:
    with mysql_connection() as conn:
        ensure_account_states_table(conn)
        cursor = conn.execute(
            "DELETE FROM account_states WHERE kind = ? AND name = ?",
            (ACCOUNT_STATE_KIND_ACCOUNT, name),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_default_login_state_sync() -> dict | None:
    with mysql_connection() as conn:
        ensure_account_states_table(conn)
        row = conn.execute(
            """
            SELECT name, state_json, updated_at
            FROM account_states
            WHERE kind = ? AND name = ?
            LIMIT 1
            """,
            (ACCOUNT_STATE_KIND_DEFAULT, DEFAULT_LOGIN_STATE_NAME),
        ).fetchone()
    return dict(row) if row else None


def upsert_default_login_state_sync(content: str) -> None:
    normalized_content = validate_state_json(content)
    now = _now_iso()
    with mysql_connection() as conn:
        ensure_account_states_table(conn)
        conn.execute(
            """
            INSERT INTO account_states (name, kind, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                state_json = VALUES(state_json),
                updated_at = VALUES(updated_at)
            """,
            (
                DEFAULT_LOGIN_STATE_NAME,
                ACCOUNT_STATE_KIND_DEFAULT,
                normalized_content,
                now,
                now,
            ),
        )
        conn.commit()


def delete_default_login_state_sync() -> bool:
    with mysql_connection() as conn:
        ensure_account_states_table(conn)
        cursor = conn.execute(
            "DELETE FROM account_states WHERE kind = ? AND name = ?",
            (ACCOUNT_STATE_KIND_DEFAULT, DEFAULT_LOGIN_STATE_NAME),
        )
        conn.commit()
        return cursor.rowcount > 0


def has_default_login_state_sync() -> bool:
    return get_default_login_state_sync() is not None


def materialize_runtime_account_states_sync(
    *,
    runtime_state_dir: Optional[str] = None,
    runtime_default_state_file: Optional[str] = None,
) -> dict:
    state_dir = Path(runtime_state_dir or get_runtime_account_state_dir())
    state_dir.mkdir(parents=True, exist_ok=True)
    default_state_file = Path(runtime_default_state_file or get_runtime_default_state_file())
    default_state_file.parent.mkdir(parents=True, exist_ok=True)

    accounts = _list_account_rows_sync(kind=ACCOUNT_STATE_KIND_ACCOUNT)
    for stale_file in state_dir.glob("*.json"):
        stale_file.unlink(missing_ok=True)
    for row in accounts:
        target_path = state_dir / f"{row['name']}.json"
        target_path.write_text(str(row["state_json"]), encoding="utf-8")

    default_state = get_default_login_state_sync()
    if default_state:
        default_state_file.write_text(str(default_state["state_json"]), encoding="utf-8")
    elif default_state_file.exists():
        default_state_file.unlink()

    return {
        "runtime_state_dir": str(state_dir),
        "runtime_default_state_file": str(default_state_file),
        "accounts": [row["name"] for row in accounts],
        "default_exists": bool(default_state),
    }
