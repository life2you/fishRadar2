"""
租户自助设置路由
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import require_workspace_user
from src.domain.models.auth import AuthenticatedUser
from src.services.notification_config_service import (
    NotificationSettingsValidationError,
    assert_notification_patch_allowed,
    model_dump,
)
from src.services.tenant_notification_access_service import (
    get_tenant_notification_channels,
)
from src.services.notification_service import build_notification_service
from src.services.tenant_notification_settings_service import (
    build_tenant_notification_test_settings,
    get_tenant_notification_settings_response,
    save_tenant_notification_settings,
)


router = APIRouter(prefix="/api/tenant-settings", tags=["tenant-settings"])


class NotificationSettingsModel(BaseModel):
    NTFY_TOPIC_URL: str | None = None
    GOTIFY_URL: str | None = None
    GOTIFY_TOKEN: str | None = None
    BARK_URL: str | None = None
    WX_BOT_URL: str | None = None
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None
    TELEGRAM_API_BASE_URL: str | None = None
    WEBHOOK_URL: str | None = None
    WEBHOOK_METHOD: str | None = None
    WEBHOOK_HEADERS: str | None = None
    WEBHOOK_CONTENT_TYPE: str | None = None
    WEBHOOK_QUERY_PARAMETERS: str | None = None
    WEBHOOK_BODY: str | None = None
    PCURL_TO_MOBILE: bool | None = None


class NotificationTestRequest(BaseModel):
    channel: str | None = None
    settings: NotificationSettingsModel = Field(default_factory=NotificationSettingsModel)


def _require_tenant_user(current_user: AuthenticatedUser) -> int:
    if current_user.role != "tenant" or current_user.tenant_id is None:
        raise HTTPException(status_code=403, detail="当前账号无权访问该资源")
    return current_user.tenant_id


@router.get("/notifications")
async def get_tenant_notification_settings(
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    tenant_id = _require_tenant_user(current_user)
    payload = await get_tenant_notification_settings_response(tenant_id)
    payload["AVAILABLE_CHANNELS"] = await get_tenant_notification_channels()
    return payload


@router.put("/notifications")
async def update_tenant_notification_settings(
    settings: NotificationSettingsModel,
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    tenant_id = _require_tenant_user(current_user)
    try:
        patch_payload = model_dump(settings, exclude_unset=True)
        assert_notification_patch_allowed(
            patch_payload,
            await get_tenant_notification_channels(),
        )
        return await save_tenant_notification_settings(
            tenant_id,
            patch_payload,
        )
    except NotificationSettingsValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/notifications/test")
async def test_tenant_notification_settings(
    payload: NotificationTestRequest,
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    tenant_id = _require_tenant_user(current_user)
    try:
        patch_payload = model_dump(payload.settings, exclude_unset=True)
        available_channels = await get_tenant_notification_channels()
        assert_notification_patch_allowed(patch_payload, available_channels)
        if payload.channel and payload.channel not in available_channels:
            raise NotificationSettingsValidationError(f"渠道 {payload.channel} 当前未向租户开放")
        merged_settings = await build_tenant_notification_test_settings(
            tenant_id,
            patch_payload,
            channel=payload.channel,
        )
    except NotificationSettingsValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    service = build_notification_service(merged_settings)
    if not service.clients:
        if payload.channel:
            raise HTTPException(
                status_code=422,
                detail=f"渠道 {payload.channel} 未配置或不受支持",
            )
        raise HTTPException(status_code=422, detail="请至少配置一个可用的通知渠道")

    results = await service.send_test_notification()
    if payload.channel:
        if payload.channel not in results:
            raise HTTPException(
                status_code=422,
                detail=f"渠道 {payload.channel} 未配置或不受支持",
            )
        results = {payload.channel: results[payload.channel]}

    return {
        "message": "测试通知已执行",
        "results": results,
    }
