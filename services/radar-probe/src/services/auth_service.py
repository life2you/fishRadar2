"""
Database-backed authentication and tenant access service.
"""
from __future__ import annotations

import asyncio
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from src.domain.models.auth import AuthenticatedUser
from src.infrastructure.config.settings import settings as app_settings
from src.infrastructure.persistence.mysql_connection import mysql_connection
from src.infrastructure.security.passwords import hash_password, verify_password


AUTH_SESSION_COOKIE = "auth_session"
DEFAULT_ADMIN_TENANT_SLUG = "platform-admin"
DEFAULT_ADMIN_TENANT_NAME = "Platform Admin"
SESSION_TTL_DAYS = 7
ACTIVATION_CODE_GROUP = 4
ACTIVATION_CODE_PARTS = 4


def _now_dt() -> datetime:
    return datetime.now()


def _now_iso() -> str:
    return _now_dt().isoformat()


def _session_expiry_iso() -> str:
    return (_now_dt() + timedelta(days=SESSION_TTL_DAYS)).isoformat()


def _duration_expiry_iso(duration_minutes: int) -> str:
    return (_now_dt() + timedelta(minutes=duration_minutes)).isoformat()


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _row_value(row, key: str, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or "tenant"


def _next_numeric_id(conn, table_name: str) -> int:
    row = conn.execute(
        f"SELECT COALESCE(MAX(id), 0) AS max_id FROM {table_name}"
    ).fetchone()
    return int(row["max_id"]) + 1


def _build_unique_tenant_slug(conn, tenant_name: str, username: str) -> str:
    base_slug = _slugify(tenant_name) or _slugify(username)
    slug = base_slug
    suffix = 2
    while True:
        row = conn.execute(
            "SELECT id FROM tenants WHERE slug = ? LIMIT 1",
            (slug,),
        ).fetchone()
        if row is None:
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


def _row_to_authenticated_user(row, *, session_token: str | None = None) -> AuthenticatedUser | None:
    if not row:
        return None
    tenant_status = _row_value(row, "tenant_status")
    tenant_ai_enabled = _as_bool(_row_value(row, "tenant_ai_enabled"))
    tenant_activation_required = _as_bool(_row_value(row, "tenant_activation_required"))
    tenant_activated_at = (
        str(_row_value(row, "tenant_activated_at"))
        if _row_value(row, "tenant_activated_at") is not None
        else None
    )
    tenant_access_expires_at = (
        str(_row_value(row, "tenant_access_expires_at"))
        if _row_value(row, "tenant_access_expires_at") is not None
        else None
    )
    return AuthenticatedUser(
        user_id=int(_row_value(row, "user_id")),
        username=str(_row_value(row, "username")),
        role=str(_row_value(row, "role")),
        display_name=str(_row_value(row, "display_name")) if _row_value(row, "display_name") is not None else None,
        tenant_id=int(_row_value(row, "tenant_id")) if _row_value(row, "tenant_id") is not None else None,
        tenant_name=str(_row_value(row, "tenant_name")) if _row_value(row, "tenant_name") is not None else None,
        tenant_status=str(tenant_status) if tenant_status is not None else None,
        tenant_ai_enabled=tenant_ai_enabled,
        tenant_activation_required=tenant_activation_required,
        tenant_activated_at=tenant_activated_at,
        tenant_access_expires_at=tenant_access_expires_at,
        session_token=session_token,
    )


def bootstrap_default_auth_data() -> None:
    with mysql_connection() as conn:
        tenant_row = conn.execute(
            "SELECT id FROM tenants WHERE slug = ? LIMIT 1",
            (DEFAULT_ADMIN_TENANT_SLUG,),
        ).fetchone()
        if tenant_row is None:
            conn.execute(
                """
                INSERT INTO tenants (
                    name, slug, status, ai_enabled, activation_required, activated_at, created_at
                ) VALUES (?, ?, 'active', 1, 0, ?, ?)
                """,
                (DEFAULT_ADMIN_TENANT_NAME, DEFAULT_ADMIN_TENANT_SLUG, _now_iso(), _now_iso()),
            )
            conn.commit()
            tenant_row = conn.execute(
                "SELECT id FROM tenants WHERE slug = ? LIMIT 1",
                (DEFAULT_ADMIN_TENANT_SLUG,),
            ).fetchone()
        else:
            conn.execute(
                """
                UPDATE tenants
                SET ai_enabled = 1,
                    activation_required = 0,
                    activated_at = COALESCE(activated_at, ?)
                WHERE slug = ?
                """,
                (_now_iso(), DEFAULT_ADMIN_TENANT_SLUG),
            )
            conn.commit()

        user_count_row = conn.execute("SELECT COUNT(1) AS total FROM users").fetchone()
        if int(user_count_row["total"]) <= 0:
            username = app_settings.web_username
            password = app_settings.web_password
            password_hash = hash_password(password)
            now = _now_iso()
            user_id = _next_numeric_id(conn, "users")
            tenant_id = int(tenant_row["id"])

            conn.execute(
                """
                INSERT INTO users (id, username, password_hash, role, status, display_name, created_at)
                VALUES (?, ?, ?, 'admin', 'active', ?, ?)
                """,
                (user_id, username, password_hash, username, now),
            )
            conn.execute(
                """
                INSERT INTO user_tenant_memberships (user_id, tenant_id, membership_role, created_at)
                VALUES (?, ?, 'owner', ?)
                """,
                (user_id, tenant_id, now),
            )
            conn.commit()


def _membership_for_user(conn, user_id: int):
    return conn.execute(
        """
        SELECT
            m.tenant_id,
            t.name AS tenant_name,
            t.status AS tenant_status,
            t.ai_enabled AS tenant_ai_enabled,
            t.activation_required AS tenant_activation_required,
            t.activated_at AS tenant_activated_at,
            t.access_expires_at AS tenant_access_expires_at
        FROM user_tenant_memberships AS m
        JOIN tenants AS t ON t.id = m.tenant_id
        WHERE m.user_id = ?
        ORDER BY m.id ASC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()


def _build_user_context(conn, user_row, *, session_token: str | None = None) -> AuthenticatedUser:
    membership = _membership_for_user(conn, int(user_row["id"]))
    row = {
        "user_id": int(user_row["id"]),
        "username": user_row["username"],
        "role": user_row["role"],
        "display_name": _row_value(user_row, "display_name"),
        "tenant_id": membership["tenant_id"] if membership else None,
        "tenant_name": membership["tenant_name"] if membership else None,
        "tenant_status": membership["tenant_status"] if membership else None,
        "tenant_ai_enabled": membership["tenant_ai_enabled"] if membership else 0,
        "tenant_activation_required": membership["tenant_activation_required"] if membership else 0,
        "tenant_activated_at": membership["tenant_activated_at"] if membership else None,
        "tenant_access_expires_at": membership["tenant_access_expires_at"] if membership else None,
    }
    return _row_to_authenticated_user(row, session_token=session_token)  # type: ignore[arg-type]


def count_users_sync() -> int:
    with mysql_connection() as conn:
        row = conn.execute("SELECT COUNT(1) AS total FROM users").fetchone()
    return int(row["total"]) if row else 0


def validate_admin_bootstrap_safety_sync() -> None:
    if not app_settings.enforce_production_admin_bootstrap_safety:
        return
    if not app_settings.uses_default_admin_bootstrap_credentials:
        return
    user_count = count_users_sync()
    if app_settings.is_production and user_count <= 0:
        raise RuntimeError(
            "生产环境禁止使用默认管理员初始账号启动空库，请先修改 WEB_USERNAME / WEB_PASSWORD。"
        )
    if app_settings.is_production:
        print(
            "[安全警告] 生产环境仍检测到默认 WEB_USERNAME / WEB_PASSWORD。"
            " 当前数据库已存在用户，不会自动创建默认管理员，但仍建议尽快清理该默认值。"
        )


def authenticate_credentials_sync(username: str, password: str) -> Optional[AuthenticatedUser]:
    with mysql_connection() as conn:
        user_row = conn.execute(
            """
            SELECT id, username, password_hash, role, status, display_name
            FROM users
            WHERE username = ?
            LIMIT 1
            """,
            (username,),
        ).fetchone()
        if user_row is None:
            return None
        if str(user_row["status"]) != "active":
            return None
        if not verify_password(password, str(user_row["password_hash"])):
            return None
        context = _build_user_context(conn, user_row)
        if context.role == "tenant" and context.tenant_status != "active":
            return None
        return context


async def authenticate_credentials(username: str, password: str) -> Optional[AuthenticatedUser]:
    return await asyncio.to_thread(authenticate_credentials_sync, username, password)


def register_tenant_user_sync(
    *,
    username: str,
    password: str,
    tenant_name: str,
    display_name: str | None = None,
) -> AuthenticatedUser:
    normalized_username = str(username or "").strip()
    normalized_tenant_name = str(tenant_name or "").strip()
    normalized_display_name = str(display_name or "").strip() or normalized_tenant_name
    if not normalized_username:
        raise ValueError("用户名不能为空")
    if len(normalized_username) < 3:
        raise ValueError("用户名至少需要 3 个字符")
    if not password or len(password) < 6:
        raise ValueError("密码至少需要 6 个字符")
    if not normalized_tenant_name:
        raise ValueError("租户名称不能为空")

    with mysql_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ? LIMIT 1",
            (normalized_username,),
        ).fetchone()
        if existing is not None:
            raise ValueError("用户名已存在")

        now = _now_iso()
        tenant_slug = _build_unique_tenant_slug(conn, normalized_tenant_name, normalized_username)
        conn.execute(
            """
            INSERT INTO tenants (
                name, slug, status, ai_enabled, activation_required, activated_at, created_at
            ) VALUES (?, ?, 'active', 0, 1, NULL, ?)
            """,
            (normalized_tenant_name, tenant_slug, now),
        )
        tenant_row = conn.execute(
            "SELECT id FROM tenants WHERE slug = ? LIMIT 1",
            (tenant_slug,),
        ).fetchone()
        user_id = _next_numeric_id(conn, "users")
        conn.execute(
            """
            INSERT INTO users (id, username, password_hash, role, status, display_name, created_at)
            VALUES (?, ?, ?, 'tenant', 'active', ?, ?)
            """,
            (user_id, normalized_username, hash_password(password), normalized_display_name, now),
        )
        conn.execute(
            """
            INSERT INTO user_tenant_memberships (user_id, tenant_id, membership_role, created_at)
            VALUES (?, ?, 'owner', ?)
            """,
            (user_id, int(tenant_row["id"]), now),
        )
        conn.commit()

        user_row = conn.execute(
            """
            SELECT id, username, role, status, display_name
            FROM users
            WHERE id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return _build_user_context(conn, user_row)


async def register_tenant_user(
    *,
    username: str,
    password: str,
    tenant_name: str,
    display_name: str | None = None,
) -> AuthenticatedUser:
    return await asyncio.to_thread(
        register_tenant_user_sync,
        username=username,
        password=password,
        tenant_name=tenant_name,
        display_name=display_name,
    )


def create_session_sync(user: AuthenticatedUser) -> str:
    token = secrets.token_urlsafe(32)
    with mysql_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO auth_sessions (
                session_token, user_id, tenant_id, expires_at, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                token,
                user.user_id,
                user.tenant_id,
                _session_expiry_iso(),
                _now_iso(),
            ),
        )
        conn.commit()
    return token


async def create_session(user: AuthenticatedUser) -> str:
    return await asyncio.to_thread(create_session_sync, user)


def get_user_by_session_sync(session_token: str) -> Optional[AuthenticatedUser]:
    with mysql_connection() as conn:
        row = conn.execute(
            """
            SELECT s.session_token, s.expires_at, u.id, u.username, u.role, u.status, u.display_name
            FROM auth_sessions AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.session_token = ?
            LIMIT 1
            """,
            (session_token,),
        ).fetchone()
        if row is None:
            return None
        expires_at = str(row["expires_at"] or "")
        if expires_at and datetime.fromisoformat(expires_at) < _now_dt():
            conn.execute("DELETE FROM auth_sessions WHERE session_token = ?", (session_token,))
            conn.commit()
            return None
        if str(row["status"]) != "active":
            return None
        context = _build_user_context(conn, row, session_token=session_token)
        if context.role == "tenant" and context.tenant_status != "active":
            return None
        return context


async def get_user_by_session(session_token: str) -> Optional[AuthenticatedUser]:
    return await asyncio.to_thread(get_user_by_session_sync, session_token)


def delete_session_sync(session_token: str) -> None:
    with mysql_connection() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE session_token = ?", (session_token,))
        conn.commit()


async def delete_session(session_token: str) -> None:
    await asyncio.to_thread(delete_session_sync, session_token)


def _serialize_tenant_row(row) -> dict:
    access_expires_at = (
        str(row["access_expires_at"])
        if _row_value(row, "access_expires_at") is not None
        else None
    )
    expires_at = _parse_iso_dt(access_expires_at)
    access_expired = expires_at is not None and expires_at <= _now_dt()
    activated_at = str(row["activated_at"]) if _row_value(row, "activated_at") is not None else None
    activation_required = _as_bool(_row_value(row, "activation_required"))
    workspace_enabled = (
        str(row["status"]) == "active"
        and ((not activation_required) or bool(activated_at))
        and not access_expired
    )
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "slug": str(row["slug"]),
        "status": str(row["status"]),
        "ai_enabled": _as_bool(_row_value(row, "ai_enabled")),
        "activation_required": activation_required,
        "activated_at": activated_at,
        "access_expires_at": access_expires_at,
        "access_expired": access_expired,
        "workspace_enabled": workspace_enabled,
        "can_use_ai": workspace_enabled and _as_bool(_row_value(row, "ai_enabled")),
        "created_at": str(row["created_at"]),
        "member_count": int(_row_value(row, "member_count") or 0),
    }


def list_tenants_sync() -> list[dict]:
    with mysql_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                t.id,
                t.name,
                t.slug,
                t.status,
                t.ai_enabled,
                t.activation_required,
                t.activated_at,
                t.access_expires_at,
                t.created_at,
                COUNT(m.id) AS member_count
            FROM tenants AS t
            LEFT JOIN user_tenant_memberships AS m ON m.tenant_id = t.id
            GROUP BY
                t.id,
                t.name,
                t.slug,
                t.status,
                t.ai_enabled,
                t.activation_required,
                t.activated_at,
                t.access_expires_at,
                t.created_at
            ORDER BY t.id DESC
            """
        ).fetchall()
        return [_serialize_tenant_row(row) for row in rows]


async def list_tenants() -> list[dict]:
    return await asyncio.to_thread(list_tenants_sync)


def get_tenant_workspace_status_sync(tenant_id: int) -> dict:
    with mysql_connection() as conn:
        row = conn.execute(
            """
            SELECT status, activation_required, activated_at, access_expires_at
            FROM tenants
            WHERE id = ?
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
        if row is None:
            return {
                "exists": False,
                "status": "missing",
                "access_expired": False,
                "workspace_enabled": False,
                "access_expires_at": None,
            }

    access_expires_at = (
        str(row["access_expires_at"])
        if _row_value(row, "access_expires_at") is not None
        else None
    )
    expires_at = _parse_iso_dt(access_expires_at)
    access_expired = expires_at is not None and expires_at <= _now_dt()
    activation_required = _as_bool(_row_value(row, "activation_required"))
    activated_at = str(row["activated_at"]) if _row_value(row, "activated_at") is not None else None
    workspace_enabled = (
        str(row["status"]) == "active"
        and ((not activation_required) or bool(activated_at))
        and not access_expired
    )
    return {
        "exists": True,
        "status": str(row["status"]),
        "access_expired": access_expired,
        "workspace_enabled": workspace_enabled,
        "access_expires_at": access_expires_at,
    }


async def get_tenant_workspace_status(tenant_id: int) -> dict:
    return await asyncio.to_thread(get_tenant_workspace_status_sync, tenant_id)


def update_tenant_access_sync(
    tenant_id: int,
    *,
    status: str | None = None,
    ai_enabled: bool | None = None,
    activation_required: bool | None = None,
    extend_access_minutes: int | None = None,
) -> dict:
    if status is not None and status not in {"active", "disabled"}:
        raise ValueError("租户状态仅支持 active 或 disabled")
    normalized_extend_access_minutes = None
    if extend_access_minutes is not None:
        normalized_extend_access_minutes = max(1, min(int(extend_access_minutes), 60 * 24 * 365))
    if all(
        value is None
        for value in (status, ai_enabled, activation_required, normalized_extend_access_minutes)
    ):
        raise ValueError("没有可更新的租户字段")

    with mysql_connection() as conn:
        row = conn.execute(
            """
            SELECT id, slug, activation_required, activated_at, access_expires_at
            FROM tenants
            WHERE id = ?
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
        if row is None:
            raise ValueError("租户不存在")
        if str(row["slug"]) == DEFAULT_ADMIN_TENANT_SLUG and activation_required is True:
            raise ValueError("管理员租户不能开启激活限制")
        if str(row["slug"]) == DEFAULT_ADMIN_TENANT_SLUG and status == "disabled":
            raise ValueError("管理员租户不能被停用")

        updates: list[str] = []
        params: list = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if ai_enabled is not None:
            updates.append("ai_enabled = ?")
            params.append(1 if ai_enabled else 0)
        if activation_required is not None:
            updates.append("activation_required = ?")
            params.append(1 if activation_required else 0)
            if not activation_required:
                updates.append("activated_at = COALESCE(activated_at, ?)")
                params.append(_now_iso())
                updates.append("access_expires_at = NULL")

        if normalized_extend_access_minutes is not None:
            base_time = _now_dt()
            current_expires_at = _parse_iso_dt(
                str(row["access_expires_at"])
                if _row_value(row, "access_expires_at") is not None
                else None
            )
            if current_expires_at is not None and current_expires_at > base_time:
                base_time = current_expires_at
            next_expiry = (base_time + timedelta(minutes=normalized_extend_access_minutes)).isoformat()
            if "activated_at = COALESCE(activated_at, ?)" not in updates:
                updates.append("activated_at = COALESCE(activated_at, ?)")
                params.append(_now_iso())
            updates = [item for item in updates if item != "access_expires_at = NULL"]
            updates.append("access_expires_at = ?")
            params.append(next_expiry)
            if _as_bool(_row_value(row, "activation_required")) and status != "disabled":
                updates.append("status = 'active'")

        conn.execute(
            f"UPDATE tenants SET {', '.join(updates)} WHERE id = ?",
            tuple(params + [tenant_id]),
        )
        conn.commit()
        updated = conn.execute(
            """
            SELECT
                t.id,
                t.name,
                t.slug,
                t.status,
                t.ai_enabled,
                t.activation_required,
                t.activated_at,
                t.access_expires_at,
                t.created_at,
                COUNT(m.id) AS member_count
            FROM tenants AS t
            LEFT JOIN user_tenant_memberships AS m ON m.tenant_id = t.id
            WHERE t.id = ?
            GROUP BY
                t.id,
                t.name,
                t.slug,
                t.status,
                t.ai_enabled,
                t.activation_required,
                t.activated_at,
                t.access_expires_at,
                t.created_at
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
        return _serialize_tenant_row(updated)


async def update_tenant_access(
    tenant_id: int,
    *,
    status: str | None = None,
    ai_enabled: bool | None = None,
    activation_required: bool | None = None,
    extend_access_minutes: int | None = None,
) -> dict:
    return await asyncio.to_thread(
        update_tenant_access_sync,
        tenant_id,
        status=status,
        ai_enabled=ai_enabled,
        activation_required=activation_required,
        extend_access_minutes=extend_access_minutes,
    )


def get_tenant_detail_sync(tenant_id: int) -> dict:
    with mysql_connection() as conn:
        tenant_row = conn.execute(
            """
            SELECT
                t.id,
                t.name,
                t.slug,
                t.status,
                t.ai_enabled,
                t.activation_required,
                t.activated_at,
                t.access_expires_at,
                t.created_at,
                COUNT(m.id) AS member_count
            FROM tenants AS t
            LEFT JOIN user_tenant_memberships AS m ON m.tenant_id = t.id
            WHERE t.id = ?
            GROUP BY
                t.id,
                t.name,
                t.slug,
                t.status,
                t.ai_enabled,
                t.activation_required,
                t.activated_at,
                t.access_expires_at,
                t.created_at
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
        if tenant_row is None:
            raise ValueError("租户不存在")

        task_counts = conn.execute(
            """
            SELECT
                COUNT(1) AS total_tasks,
                SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) AS enabled_tasks,
                SUM(CASE WHEN is_running = 1 THEN 1 ELSE 0 END) AS running_tasks
            FROM tasks
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        ).fetchone()
        result_counts = conn.execute(
            """
            SELECT
                COUNT(DISTINCT result_filename) AS result_files,
                COUNT(1) AS scanned_items,
                SUM(CASE WHEN is_recommended = 1 AND analysis_source = 'ai' THEN 1 ELSE 0 END) AS ai_recommended_items,
                SUM(CASE WHEN is_recommended = 1 AND analysis_source = 'keyword' THEN 1 ELSE 0 END) AS keyword_recommended_items,
                MAX(crawl_time) AS latest_crawl_time
            FROM result_items
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        ).fetchone()
        latest_code = conn.execute(
            """
            SELECT
                code,
                status,
                duration_minutes,
                note,
                created_at,
                redeemed_at
            FROM activation_codes
            WHERE redeemed_by_tenant_id = ?
            ORDER BY redeemed_at DESC, id DESC
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()

        return {
            "tenant": _serialize_tenant_row(tenant_row),
            "metrics": {
                "task_count": int(_row_value(task_counts, "total_tasks") or 0),
                "enabled_task_count": int(_row_value(task_counts, "enabled_tasks") or 0),
                "running_task_count": int(_row_value(task_counts, "running_tasks") or 0),
                "result_file_count": int(_row_value(result_counts, "result_files") or 0),
                "scanned_item_count": int(_row_value(result_counts, "scanned_items") or 0),
                "ai_recommended_item_count": int(_row_value(result_counts, "ai_recommended_items") or 0),
                "keyword_recommended_item_count": int(_row_value(result_counts, "keyword_recommended_items") or 0),
                "recommended_item_count": int(_row_value(result_counts, "ai_recommended_items") or 0)
                + int(_row_value(result_counts, "keyword_recommended_items") or 0),
                "latest_crawl_time": str(_row_value(result_counts, "latest_crawl_time"))
                if _row_value(result_counts, "latest_crawl_time") is not None
                else None,
            },
            "latest_activation_code": (
                {
                    "code": str(latest_code["code"]),
                    "status": str(latest_code["status"]),
                    "duration_minutes": int(_row_value(latest_code, "duration_minutes") or 0),
                    "note": str(latest_code["note"]) if _row_value(latest_code, "note") is not None else None,
                    "created_at": str(latest_code["created_at"]),
                    "redeemed_at": str(latest_code["redeemed_at"])
                    if _row_value(latest_code, "redeemed_at") is not None
                    else None,
                }
                if latest_code is not None
                else None
            ),
        }


async def get_tenant_detail(tenant_id: int) -> dict:
    return await asyncio.to_thread(get_tenant_detail_sync, tenant_id)


def _generate_activation_code() -> str:
    parts = []
    for _ in range(ACTIVATION_CODE_PARTS):
        parts.append(secrets.token_hex(4).upper()[:ACTIVATION_CODE_GROUP])
    return "-".join(parts)


def create_activation_codes_sync(
    *,
    quantity: int,
    duration_minutes: int,
    note: str | None,
    created_by_user_id: int,
) -> list[dict]:
    normalized_quantity = max(1, min(int(quantity), 100))
    normalized_duration_minutes = max(1, min(int(duration_minutes), 60 * 24 * 365))
    normalized_note = str(note or "").strip() or None
    created_at = _now_iso()
    created_codes: list[dict] = []
    with mysql_connection() as conn:
        for _ in range(normalized_quantity):
            code = _generate_activation_code()
            while conn.execute(
                "SELECT id FROM activation_codes WHERE code = ? LIMIT 1",
                (code,),
            ).fetchone() is not None:
                code = _generate_activation_code()
            conn.execute(
                """
                INSERT INTO activation_codes (
                    code, status, duration_minutes, note, created_by_user_id, redeemed_by_tenant_id,
                    redeemed_by_user_id, redeemed_at, created_at
                ) VALUES (?, 'unused', ?, ?, ?, NULL, NULL, NULL, ?)
                """,
                (code, normalized_duration_minutes, normalized_note, created_by_user_id, created_at),
            )
            created_codes.append(
                {
                    "code": code,
                    "status": "unused",
                    "duration_minutes": normalized_duration_minutes,
                    "note": normalized_note,
                    "created_by_user_id": created_by_user_id,
                    "redeemed_by_tenant_id": None,
                    "redeemed_by_user_id": None,
                    "redeemed_at": None,
                    "created_at": created_at,
                }
            )
        conn.commit()
    return created_codes


async def create_activation_codes(
    *,
    quantity: int,
    duration_minutes: int,
    note: str | None,
    created_by_user_id: int,
) -> list[dict]:
    return await asyncio.to_thread(
        create_activation_codes_sync,
        quantity=quantity,
        duration_minutes=duration_minutes,
        note=note,
        created_by_user_id=created_by_user_id,
    )


def list_activation_codes_sync() -> list[dict]:
    with mysql_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.code,
                c.status,
                c.duration_minutes,
                c.note,
                c.created_by_user_id,
                c.redeemed_by_tenant_id,
                c.redeemed_by_user_id,
                c.redeemed_at,
                c.created_at,
                t.name AS redeemed_tenant_name
            FROM activation_codes AS c
            LEFT JOIN tenants AS t ON t.id = c.redeemed_by_tenant_id
            ORDER BY c.id DESC
            """
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "code": str(row["code"]),
                "status": str(row["status"]),
                "duration_minutes": int(_row_value(row, "duration_minutes") or 0),
                "note": str(row["note"]) if _row_value(row, "note") is not None else None,
                "created_by_user_id": int(row["created_by_user_id"]) if _row_value(row, "created_by_user_id") is not None else None,
                "redeemed_by_tenant_id": int(row["redeemed_by_tenant_id"]) if _row_value(row, "redeemed_by_tenant_id") is not None else None,
                "redeemed_by_user_id": int(row["redeemed_by_user_id"]) if _row_value(row, "redeemed_by_user_id") is not None else None,
                "redeemed_at": str(row["redeemed_at"]) if _row_value(row, "redeemed_at") is not None else None,
                "created_at": str(row["created_at"]),
                "redeemed_tenant_name": str(row["redeemed_tenant_name"]) if _row_value(row, "redeemed_tenant_name") is not None else None,
            }
            for row in rows
        ]


async def list_activation_codes() -> list[dict]:
    return await asyncio.to_thread(list_activation_codes_sync)


def redeem_activation_code_sync(code: str, current_user: AuthenticatedUser) -> AuthenticatedUser:
    if current_user.role != "tenant" or current_user.tenant_id is None:
        raise ValueError("只有租户账号可以激活")
    if current_user.workspace_enabled:
        raise ValueError("当前租户已激活，无需重复使用卡密")
    normalized_code = str(code or "").strip().upper()
    if not normalized_code:
        raise ValueError("卡密不能为空")

    with mysql_connection() as conn:
        code_row = conn.execute(
            """
            SELECT id, code, status, redeemed_by_tenant_id, duration_minutes
            FROM activation_codes
            WHERE code = ?
            LIMIT 1
            """,
            (normalized_code,),
        ).fetchone()
        if code_row is None:
            raise ValueError("卡密不存在")
        status = str(code_row["status"])
        if status == "disabled":
            raise ValueError("卡密已停用")
        if status == "redeemed":
            raise ValueError("卡密已被使用")

        now = _now_iso()
        duration_minutes = max(1, int(code_row["duration_minutes"] or 1))
        access_expires_at = _duration_expiry_iso(duration_minutes)
        conn.execute(
            """
            UPDATE activation_codes
            SET status = 'redeemed',
                redeemed_by_tenant_id = ?,
                redeemed_by_user_id = ?,
                redeemed_at = ?
            WHERE id = ?
            """,
            (current_user.tenant_id, current_user.user_id, now, int(code_row["id"])),
        )
        conn.execute(
            """
            UPDATE tenants
            SET activated_at = ?,
                access_expires_at = ?,
                status = 'active'
            WHERE id = ?
            """,
            (now, access_expires_at, current_user.tenant_id),
        )
        conn.commit()

        user_row = conn.execute(
            """
            SELECT id, username, role, status, display_name
            FROM users
            WHERE id = ?
            LIMIT 1
            """,
            (current_user.user_id,),
        ).fetchone()
        return _build_user_context(conn, user_row, session_token=current_user.session_token)


async def redeem_activation_code(code: str, current_user: AuthenticatedUser) -> AuthenticatedUser:
    return await asyncio.to_thread(redeem_activation_code_sync, code, current_user)
