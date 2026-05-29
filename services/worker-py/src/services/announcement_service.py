import asyncio
from datetime import datetime
from typing import Optional

from src.infrastructure.persistence.mysql_connection import mysql_connection
from src.services.auth_service import list_tenants_sync
from src.services.notification_service import send_product_notification


def _now_iso() -> str:
    return datetime.now().isoformat()


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _serialize_announcement_row(row) -> dict:
    return {
        "id": int(row["id"]),
        "title": str(row["title"]),
        "content": str(row["content"]),
        "level": str(row["level"]),
        "status": str(row["status"]),
        "dismissible": bool(row["dismissible"]),
        "published_at": str(row["published_at"]) if row["published_at"] is not None else None,
        "expires_at": str(row["expires_at"]) if row["expires_at"] is not None else None,
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "created_by_user_id": int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
    }


def list_announcements_sync(*, include_inactive: bool = True) -> list[dict]:
    with mysql_connection() as conn:
        if include_inactive:
            rows = conn.execute(
                """
                SELECT id, title, content, level, status, dismissible, published_at, expires_at,
                       created_at, updated_at, created_by_user_id
                FROM announcements
                ORDER BY
                    CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                    COALESCE(published_at, updated_at) DESC,
                    id DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, title, content, level, status, dismissible, published_at, expires_at,
                       created_at, updated_at, created_by_user_id
                FROM announcements
                WHERE status = 'active'
                  AND (published_at IS NULL OR published_at <= ?)
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY COALESCE(published_at, updated_at) DESC, id DESC
                """,
                (_now_iso(), _now_iso()),
            ).fetchall()
    return [_serialize_announcement_row(row) for row in rows]


async def list_announcements(*, include_inactive: bool = True) -> list[dict]:
    return await asyncio.to_thread(list_announcements_sync, include_inactive=include_inactive)


def create_announcement_sync(
    *,
    title: str,
    content: str,
    level: str,
    status: str,
    dismissible: bool,
    published_at: Optional[str],
    expires_at: Optional[str],
    created_by_user_id: Optional[int],
) -> dict:
    now = _now_iso()
    normalized_published_at = _normalize_optional_text(published_at)
    if status == "active" and normalized_published_at is None:
        normalized_published_at = now

    with mysql_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO announcements (
                title, content, level, status, dismissible,
                published_at, expires_at, created_at, updated_at, created_by_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title.strip(),
                content.strip(),
                level,
                status,
                1 if dismissible else 0,
                normalized_published_at,
                _normalize_optional_text(expires_at),
                now,
                now,
                created_by_user_id,
            ),
        )
        announcement_id = int(cursor.lastrowid)
        conn.commit()
        row = conn.execute(
            """
            SELECT id, title, content, level, status, dismissible, published_at, expires_at,
                   created_at, updated_at, created_by_user_id
            FROM announcements
            WHERE id = ?
            LIMIT 1
            """,
            (announcement_id,),
        ).fetchone()
    return _serialize_announcement_row(row)


async def create_announcement(**kwargs) -> dict:
    return await asyncio.to_thread(create_announcement_sync, **kwargs)


def update_announcement_sync(
    announcement_id: int,
    *,
    title: Optional[str] = None,
    content: Optional[str] = None,
    level: Optional[str] = None,
    status: Optional[str] = None,
    dismissible: Optional[bool] = None,
    published_at: Optional[str] = None,
    expires_at: Optional[str] = None,
) -> dict:
    with mysql_connection() as conn:
        existing = conn.execute(
            """
            SELECT id, title, content, level, status, dismissible, published_at, expires_at,
                   created_at, updated_at, created_by_user_id
            FROM announcements
            WHERE id = ?
            LIMIT 1
            """,
            (announcement_id,),
        ).fetchone()
        if existing is None:
            raise ValueError("公告不存在")

        next_title = title.strip() if title is not None else str(existing["title"])
        next_content = content.strip() if content is not None else str(existing["content"])
        next_level = level or str(existing["level"])
        next_status = status or str(existing["status"])
        next_dismissible = dismissible if dismissible is not None else bool(existing["dismissible"])
        next_published_at = (
            _normalize_optional_text(published_at)
            if published_at is not None
            else (str(existing["published_at"]) if existing["published_at"] is not None else None)
        )
        if next_status == "active" and not next_published_at:
            next_published_at = _now_iso()
        next_expires_at = (
            _normalize_optional_text(expires_at)
            if expires_at is not None
            else (str(existing["expires_at"]) if existing["expires_at"] is not None else None)
        )

        conn.execute(
            """
            UPDATE announcements
            SET title = ?,
                content = ?,
                level = ?,
                status = ?,
                dismissible = ?,
                published_at = ?,
                expires_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                next_title,
                next_content,
                next_level,
                next_status,
                1 if next_dismissible else 0,
                next_published_at,
                next_expires_at,
                _now_iso(),
                announcement_id,
            ),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT id, title, content, level, status, dismissible, published_at, expires_at,
                   created_at, updated_at, created_by_user_id
            FROM announcements
            WHERE id = ?
            LIMIT 1
            """,
            (announcement_id,),
        ).fetchone()
    return _serialize_announcement_row(row)


async def update_announcement(announcement_id: int, **kwargs) -> dict:
    return await asyncio.to_thread(update_announcement_sync, announcement_id, **kwargs)


def delete_announcement_sync(announcement_id: int) -> None:
    with mysql_connection() as conn:
        conn.execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))
        conn.commit()


async def delete_announcement(announcement_id: int) -> None:
    await asyncio.to_thread(delete_announcement_sync, announcement_id)


async def notify_announcement_to_tenants(
    *,
    title: str,
    content: str,
) -> dict:
    tenants = await asyncio.to_thread(list_tenants_sync)
    active_tenant_ids = [
        int(item["id"])
        for item in tenants
        if item.get("workspace_enabled")
    ]
    results: dict[int, dict] = {}
    for tenant_id in active_tenant_ids:
        try:
            results[tenant_id] = await send_product_notification(
                {
                    "商品标题": f"[平台公告] {title}",
                    "当前售价": "N/A",
                    "商品链接": "#",
                },
                content,
                tenant_id=tenant_id,
            )
        except Exception as exc:
            results[tenant_id] = {
                "success": False,
                "message": str(exc),
            }
    return results
