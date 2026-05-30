from __future__ import annotations

from datetime import datetime

from src.domain.models.ai_account import AIAccount, AIAccountCreate, AIAccountUpdate
from src.infrastructure.persistence.mysql_connection import mysql_connection


AI_ACCOUNTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ai_accounts (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT 'AI账号ID',
    name VARCHAR(255) NOT NULL COMMENT 'AI账号名称',
    api_key TEXT NULL COMMENT 'AI账号密钥',
    base_url VARCHAR(512) NOT NULL COMMENT 'AI接口地址',
    model_name VARCHAR(255) NOT NULL COMMENT '模型名称',
    supports_image TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否支持图片分析',
    supports_text TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否支持纯文本分析',
    enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    priority INT NOT NULL DEFAULT 100 COMMENT '优先级，越小越优先',
    notes TEXT NULL COMMENT '备注说明',
    last_test_status VARCHAR(32) NULL COMMENT '最近测试状态',
    last_test_message TEXT NULL COMMENT '最近测试结果说明',
    last_tested_at VARCHAR(64) NULL COMMENT '最近测试时间',
    created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
    updated_at VARCHAR(64) NOT NULL COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI账号池表'
"""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_account(row: dict) -> AIAccount:
    return AIAccount(
        id=int(row["id"]),
        name=str(row["name"]),
        api_key=row.get("api_key"),
        base_url=str(row["base_url"]),
        model_name=str(row["model_name"]),
        supports_image=bool(row["supports_image"]),
        supports_text=bool(row["supports_text"]),
        enabled=bool(row["enabled"]),
        priority=int(row["priority"]),
        notes=row.get("notes"),
        last_test_status=row.get("last_test_status"),
        last_test_message=row.get("last_test_message"),
        last_tested_at=row.get("last_tested_at"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _ensure_ai_accounts_table(conn) -> None:
    conn.execute(AI_ACCOUNTS_TABLE_SQL)
    for column_name, column_sql in (
        ("last_test_status", "ALTER TABLE ai_accounts ADD COLUMN last_test_status VARCHAR(32) NULL COMMENT '最近测试状态'"),
        ("last_test_message", "ALTER TABLE ai_accounts ADD COLUMN last_test_message TEXT NULL COMMENT '最近测试结果说明'"),
        ("last_tested_at", "ALTER TABLE ai_accounts ADD COLUMN last_tested_at VARCHAR(64) NULL COMMENT '最近测试时间'"),
    ):
        if not _column_exists(conn, "ai_accounts", column_name):
            conn.execute(column_sql)


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = ?
          AND column_name = ?
        LIMIT 1
        """,
        (table_name, column_name),
    ).fetchone()
    return row is not None


async def list_ai_accounts(*, include_disabled: bool = True) -> list[AIAccount]:
    try:
        with mysql_connection() as conn:
            _ensure_ai_accounts_table(conn)
            query = """
                SELECT id, name, api_key, base_url, model_name, supports_image, supports_text,
                       enabled, priority, notes, last_test_status, last_test_message,
                       last_tested_at, created_at, updated_at
                FROM ai_accounts
            """
            params: list[object] = []
            if not include_disabled:
                query += " WHERE enabled = 1"
            query += " ORDER BY enabled DESC, priority ASC, id ASC"
            rows = conn.execute(query, params).fetchall()
        return [_row_to_account(row) for row in rows]
    except Exception:
        return []


async def get_ai_account(account_id: int) -> AIAccount | None:
    try:
        with mysql_connection() as conn:
            _ensure_ai_accounts_table(conn)
            row = conn.execute(
                """
                SELECT id, name, api_key, base_url, model_name, supports_image, supports_text,
                       enabled, priority, notes, last_test_status, last_test_message,
                       last_tested_at, created_at, updated_at
                FROM ai_accounts
                WHERE id = ?
                LIMIT 1
                """,
                (account_id,),
            ).fetchone()
        return _row_to_account(row) if row else None
    except Exception:
        return None


async def create_ai_account(payload: AIAccountCreate) -> AIAccount:
    now = _now_iso()
    with mysql_connection() as conn:
        _ensure_ai_accounts_table(conn)
        conn.execute(
            """
            INSERT INTO ai_accounts (
                name, api_key, base_url, model_name, supports_image, supports_text,
                enabled, priority, notes, last_test_status, last_test_message,
                last_tested_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name.strip(),
                (payload.api_key or "").strip() or None,
                payload.base_url.strip(),
                payload.model_name.strip(),
                int(payload.supports_image),
                int(payload.supports_text),
                int(payload.enabled),
                payload.priority,
                (payload.notes or "").strip() or None,
                None,
                None,
                None,
                now,
                now,
            ),
        )
        conn.commit()
        created_id = int(conn.execute("SELECT LAST_INSERT_ID() AS id").fetchone()["id"])
    created = await get_ai_account(created_id)
    if created is None:  # pragma: no cover
        raise RuntimeError("创建 AI 账号后读取失败")
    return created


async def update_ai_account(account_id: int, payload: AIAccountUpdate) -> AIAccount | None:
    existing = await get_ai_account(account_id)
    if existing is None:
        return None

    data = payload.model_dump(exclude_unset=True)
    updates: list[str] = []
    params: list[object] = []
    for field in ("name", "api_key", "base_url", "model_name", "supports_image", "supports_text", "enabled", "priority", "notes"):
        if field not in data:
            continue
        value = data[field]
        if field in {"name", "base_url", "model_name"} and value is not None:
            value = str(value).strip()
        if field in {"api_key", "notes"}:
            value = (str(value).strip() if value is not None else None) or None
        if field in {"supports_image", "supports_text", "enabled"} and value is not None:
            value = int(bool(value))
        updates.append(f"{field} = ?")
        params.append(value)
    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(account_id)

    with mysql_connection() as conn:
        _ensure_ai_accounts_table(conn)
        conn.execute(
            f"UPDATE ai_accounts SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
    return await get_ai_account(account_id)


async def delete_ai_account(account_id: int) -> bool:
    with mysql_connection() as conn:
        _ensure_ai_accounts_table(conn)
        affected = conn.execute("DELETE FROM ai_accounts WHERE id = ?", (account_id,))
        conn.commit()
        return affected._cursor.rowcount > 0


async def record_ai_account_test_result(account_id: int, *, success: bool, message: str) -> AIAccount | None:
    with mysql_connection() as conn:
        _ensure_ai_accounts_table(conn)
        conn.execute(
            """
            UPDATE ai_accounts
            SET last_test_status = ?, last_test_message = ?, last_tested_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                "success" if success else "failed",
                message.strip(),
                _now_iso(),
                _now_iso(),
                account_id,
            ),
        )
        conn.commit()
    return await get_ai_account(account_id)


def _supports_required_capability(account: AIAccount, *, require_images: bool) -> bool:
    if not account.enabled:
        return False
    if require_images:
        return bool(account.supports_image)
    return bool(account.supports_text)


async def list_ai_route_candidates(*, require_images: bool) -> list[AIAccount]:
    return [
        account
        for account in await list_ai_accounts(include_disabled=False)
        if _supports_required_capability(account, require_images=require_images)
    ]


async def has_configured_ai_provider() -> bool:
    accounts = await list_ai_accounts(include_disabled=False)
    return any(account.supports_text or account.supports_image for account in accounts)


def redact_ai_account(account: AIAccount) -> dict:
    payload = account.model_dump()
    payload["api_key"] = ""
    payload["api_key_set"] = bool(account.api_key)
    return payload
