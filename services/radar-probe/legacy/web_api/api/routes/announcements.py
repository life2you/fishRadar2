from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import require_admin_user, require_workspace_user
from src.domain.models.auth import AuthenticatedUser
from src.services.announcement_service import (
    create_announcement,
    delete_announcement,
    list_announcements,
    notify_announcement_to_tenants,
    update_announcement,
)


router = APIRouter(prefix="/api/announcements", tags=["announcements"])


class AnnouncementCreateModel(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    level: str = Field(default="info")
    status: str = Field(default="draft")
    dismissible: bool = True
    notify_tenants: bool = False
    published_at: Optional[str] = None
    expires_at: Optional[str] = None


class AnnouncementUpdateModel(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = Field(default=None, min_length=1)
    level: Optional[str] = None
    status: Optional[str] = None
    dismissible: Optional[bool] = None
    notify_tenants: bool = False
    published_at: Optional[str] = None
    expires_at: Optional[str] = None


def _should_notify_now(item: dict) -> bool:
    if item.get("status") != "active":
        return False
    published_at = item.get("published_at")
    if not published_at:
        return True
    try:
        return datetime.fromisoformat(str(published_at)) <= datetime.now()
    except ValueError:
        return True


def _validate_level(level: Optional[str]) -> None:
    if level is None:
        return
    if level not in {"info", "success", "warning"}:
        raise HTTPException(status_code=422, detail="公告级别仅支持 info、success、warning")


def _validate_status(status: Optional[str]) -> None:
    if status is None:
        return
    if status not in {"draft", "active", "archived"}:
        raise HTTPException(status_code=422, detail="公告状态仅支持 draft、active、archived")


@router.get("")
async def get_announcements(
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    include_inactive = current_user.role == "admin"
    return {"items": await list_announcements(include_inactive=include_inactive)}


@router.get("/active")
async def get_active_announcements(
    _current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    return {"items": await list_announcements(include_inactive=False)}


@router.post("")
async def post_announcement(
    payload: AnnouncementCreateModel,
    current_user: AuthenticatedUser = Depends(require_admin_user),
):
    _validate_level(payload.level)
    _validate_status(payload.status)
    item = await create_announcement(
        title=payload.title,
        content=payload.content,
        level=payload.level,
        status=payload.status,
        dismissible=payload.dismissible,
        published_at=payload.published_at,
        expires_at=payload.expires_at,
        created_by_user_id=current_user.user_id,
    )
    notification_result = None
    if payload.notify_tenants and _should_notify_now(item):
        notification_result = await notify_announcement_to_tenants(
            title=item["title"],
            content=item["content"],
        )
    return {"message": "公告已创建", "item": item, "notification_result": notification_result}


@router.patch("/{announcement_id}")
async def patch_announcement(
    announcement_id: int,
    payload: AnnouncementUpdateModel,
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    _validate_level(payload.level)
    _validate_status(payload.status)
    try:
        item = await update_announcement(
            announcement_id,
            title=payload.title,
            content=payload.content,
            level=payload.level,
            status=payload.status,
            dismissible=payload.dismissible,
            published_at=payload.published_at,
            expires_at=payload.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    notification_result = None
    if payload.notify_tenants and _should_notify_now(item):
        notification_result = await notify_announcement_to_tenants(
            title=item["title"],
            content=item["content"],
        )
    return {"message": "公告已更新", "item": item, "notification_result": notification_result}


@router.delete("/{announcement_id}")
async def remove_announcement(
    announcement_id: int,
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    await delete_announcement(announcement_id)
    return {"message": "公告已删除"}
