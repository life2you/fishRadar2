"""
设置管理路由
"""
import os
import re
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_process_service, require_admin_user
from src.infrastructure.config.env_manager import env_manager
from src.infrastructure.config.settings import (
    scraper_settings,
)
from src.domain.models.ai_account import AIAccountCreate, AIAccountUpdate
from src.services.ai_request_compat import (
    CHAT_COMPLETIONS_API_MODE,
    RESPONSES_API_MODE,
    build_ai_request_params,
    create_ai_response_sync,
    is_chat_completions_api_unsupported_error,
    is_responses_api_unsupported_error,
)
from src.services.ai_response_parser import extract_ai_response_content
from src.services.notification_config_service import (
    NotificationSettingsValidationError,
    build_configured_channels,
    build_notification_settings_response,
    build_notification_status_flags,
    load_notification_settings,
    model_dump,
    notification_settings_to_storage_payload,
    prepare_notification_test_settings,
    prepare_notification_settings_update,
)
from src.services.notification_service import build_notification_service
from src.services.process_service import ProcessService
from src.services.auth_service import (
    create_activation_codes,
    get_tenant_detail,
    list_activation_codes,
    list_tenants,
    update_tenant_access,
)
from src.services.tenant_notification_access_service import (
    get_tenant_notification_channels,
    save_tenant_notification_channels,
)
from src.domain.models.auth import AuthenticatedUser
from src.services.ai_account_service import (
    create_ai_account,
    delete_ai_account,
    get_ai_account,
    has_configured_ai_provider,
    list_ai_accounts,
    record_ai_account_test_result,
    redact_ai_account,
    update_ai_account,
)
from src.services.account_state_service import has_default_login_state_sync
from src.services.platform_settings_service import (
    load_ai_runtime_values_sync,
    load_failure_guard_settings_sync,
    load_rotation_settings_sync,
    save_ai_runtime_values_sync,
    save_failure_guard_settings_sync,
    save_notification_config_values_sync,
    save_rotation_settings_sync,
)


router = APIRouter(prefix="/api/settings", tags=["settings"])
AI_TEST_PROMPT = "Reply with OK only."
AI_TEST_MAX_OUTPUT_TOKENS = 32


def _compact_ai_test_error(exc: Exception) -> str:
    raw_message = str(exc).strip() or exc.__class__.__name__
    compact_message = re.sub(r"<[^>]+>", " ", raw_message)
    compact_message = re.sub(r"\s+", " ", compact_message).strip(" .")
    lower_message = compact_message.lower()
    if "example domain" in lower_message:
        return "接口返回了网页内容，请检查 API Base URL 是否填写正确。"
    if compact_message and compact_message != raw_message:
        return compact_message[:140]
    return raw_message[:140]


class NotificationSettingsModel(BaseModel):
    """通知设置模型"""

    NTFY_TOPIC_URL: Optional[str] = None
    GOTIFY_URL: Optional[str] = None
    GOTIFY_TOKEN: Optional[str] = None
    BARK_URL: Optional[str] = None
    WX_BOT_URL: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    TELEGRAM_API_BASE_URL: Optional[str] = None
    WEBHOOK_URL: Optional[str] = None
    WEBHOOK_METHOD: Optional[str] = None
    WEBHOOK_HEADERS: Optional[str] = None
    WEBHOOK_CONTENT_TYPE: Optional[str] = None
    WEBHOOK_QUERY_PARAMETERS: Optional[str] = None
    WEBHOOK_BODY: Optional[str] = None
    PCURL_TO_MOBILE: Optional[bool] = None


class NotificationTestRequest(BaseModel):
    """通知测试请求"""

    channel: Optional[str] = None
    settings: NotificationSettingsModel = Field(default_factory=NotificationSettingsModel)


class AIAccountTestModel(BaseModel):
    api_key: Optional[str] = None
    base_url: str
    model_name: str


class RotationSettingsModel(BaseModel):
    ACCOUNT_ROTATION_ENABLED: Optional[bool] = None
    ACCOUNT_ROTATION_MODE: Optional[str] = None
    ACCOUNT_ROTATION_RETRY_LIMIT: Optional[int] = None
    ACCOUNT_BLACKLIST_TTL: Optional[int] = None
    PROXY_ROTATION_ENABLED: Optional[bool] = None
    PROXY_ROTATION_MODE: Optional[str] = None
    PROXY_POOL: Optional[str] = None
    PROXY_ROTATION_RETRY_LIMIT: Optional[int] = None
    PROXY_BLACKLIST_TTL: Optional[int] = None


class AIRuntimeSettingsModel(BaseModel):
    PROXY_URL: Optional[str] = None
    AI_DEBUG_MODE: Optional[bool] = None
    ENABLE_RESPONSE_FORMAT: Optional[bool] = None
    ENABLE_THINKING: Optional[bool] = None
    SKIP_AI_ANALYSIS: Optional[bool] = None
    AI_ANALYSIS_CONCURRENCY: Optional[int] = Field(default=None, ge=1, le=32)
    SELLER_PROFILE_CACHE_TTL: Optional[int] = Field(default=None, ge=0, le=86400)


class FailureGuardSettingsModel(BaseModel):
    TASK_FAILURE_THRESHOLD: Optional[int] = Field(default=None, ge=1, le=100)
    TASK_FAILURE_PAUSE_SECONDS: Optional[int] = Field(default=None, ge=60, le=31536000)
    TASK_FAILURE_TZ: Optional[str] = None


class TenantAccessUpdateModel(BaseModel):
    status: Optional[str] = None
    ai_enabled: Optional[bool] = None
    activation_required: Optional[bool] = None
    extend_access_minutes: Optional[int] = Field(default=None, ge=1, le=525600)


class ActivationCodeCreateModel(BaseModel):
    quantity: int = Field(default=5, ge=1, le=100)
    duration_minutes: int = Field(default=1440, ge=1, le=525600)
    note: Optional[str] = None


class TenantNotificationChannelsModel(BaseModel):
    channels: list[str] = Field(default_factory=list)


@router.get("/notifications")
async def get_notification_settings():
    return build_notification_settings_response(load_notification_settings())


@router.put("/notifications")
async def update_notification_settings(settings: NotificationSettingsModel):
    try:
        _updates, _deletions, merged_settings = prepare_notification_settings_update(
            model_dump(settings, exclude_unset=True),
            load_notification_settings(),
        )
    except NotificationSettingsValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await asyncio.to_thread(
        save_notification_config_values_sync,
        notification_settings_to_storage_payload(merged_settings),
    )
    return {
        "message": "通知设置已成功更新",
        "configured_channels": build_configured_channels(merged_settings),
    }


@router.post("/notifications/test")
async def test_notification_settings(payload: NotificationTestRequest):
    try:
        merged_settings = prepare_notification_test_settings(
            model_dump(payload.settings, exclude_unset=True),
            load_notification_settings(),
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


@router.get("/tenant-notification-channels")
async def get_tenant_notification_channel_settings(
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    return {"channels": await get_tenant_notification_channels()}


@router.put("/tenant-notification-channels")
async def update_tenant_notification_channel_settings(
    payload: TenantNotificationChannelsModel,
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    channels = await save_tenant_notification_channels(payload.channels)
    return {
        "message": "租户可用通知方式已更新",
        "channels": channels,
    }


@router.get("/tenants")
async def get_tenant_access_settings(
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    return {"items": await list_tenants()}


@router.patch("/tenants/{tenant_id}")
async def patch_tenant_access_settings(
    tenant_id: int,
    payload: TenantAccessUpdateModel,
    process_service: ProcessService = Depends(get_process_service),
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    try:
        item = await update_tenant_access(
            tenant_id,
            status=payload.status,
            ai_enabled=payload.ai_enabled,
            activation_required=payload.activation_required,
            extend_access_minutes=payload.extend_access_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not item.get("workspace_enabled", True):
        await process_service.stop_tasks_for_tenant(tenant_id)
    return {"message": "租户权限已更新", "item": item}


@router.get("/tenants/{tenant_id}")
async def get_tenant_access_detail(
    tenant_id: int,
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    try:
        return await get_tenant_detail(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/activation-codes")
async def get_activation_codes(
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    return {"items": await list_activation_codes()}


@router.post("/activation-codes")
async def post_activation_codes(
    payload: ActivationCodeCreateModel,
    current_user: AuthenticatedUser = Depends(require_admin_user),
):
    items = await create_activation_codes(
        quantity=payload.quantity,
        duration_minutes=payload.duration_minutes,
        note=payload.note,
        created_by_user_id=current_user.user_id,
    )
    return {"message": "卡密已生成", "items": items}


@router.get("/rotation")
async def get_rotation_settings():
    return await asyncio.to_thread(load_rotation_settings_sync)


@router.put("/rotation")
async def update_rotation_settings(settings: RotationSettingsModel):
    payload = model_dump(settings, exclude_unset=True)
    await asyncio.to_thread(save_rotation_settings_sync, payload)
    return {"message": "轮换设置已成功更新"}


@router.get("/ai-runtime")
async def get_ai_runtime_settings():
    return await asyncio.to_thread(load_ai_runtime_values_sync)


@router.put("/ai-runtime")
async def update_ai_runtime_settings(settings: AIRuntimeSettingsModel):
    payload = model_dump(settings, exclude_unset=True)
    await asyncio.to_thread(save_ai_runtime_values_sync, payload)
    return {"message": "AI 运行参数已成功更新"}


@router.get("/failure-guard")
async def get_failure_guard_settings():
    return await asyncio.to_thread(load_failure_guard_settings_sync)


@router.put("/failure-guard")
async def update_failure_guard_settings(settings: FailureGuardSettingsModel):
    payload = model_dump(settings, exclude_unset=True)
    await asyncio.to_thread(save_failure_guard_settings_sync, payload)
    return {"message": "失败熔断设置已成功更新"}


@router.get("/ai-accounts")
async def get_ai_accounts(
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    items = [redact_ai_account(account) for account in await list_ai_accounts()]
    return {"items": items}


@router.post("/ai-accounts")
async def post_ai_account(
    payload: AIAccountCreate,
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    if not payload.supports_image and not payload.supports_text:
        raise HTTPException(status_code=422, detail="至少需要开启一种能力：图片分析或文本分析")
    created = await create_ai_account(payload)
    return {"message": "AI账号已创建", "item": redact_ai_account(created)}


@router.patch("/ai-accounts/{account_id}")
async def patch_ai_account(
    account_id: int,
    payload: AIAccountUpdate,
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    existing = await get_ai_account(account_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="AI账号未找到")

    final_supports_image = payload.supports_image if payload.supports_image is not None else existing.supports_image
    final_supports_text = payload.supports_text if payload.supports_text is not None else existing.supports_text
    if not final_supports_image and not final_supports_text:
        raise HTTPException(status_code=422, detail="至少需要开启一种能力：图片分析或文本分析")

    updated = await update_ai_account(account_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="AI账号未找到")
    return {"message": "AI账号已更新", "item": redact_ai_account(updated)}


@router.delete("/ai-accounts/{account_id}")
async def remove_ai_account(
    account_id: int,
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    deleted = await delete_ai_account(account_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="AI账号未找到")
    return {"message": "AI账号已删除"}


@router.post("/ai-accounts/test")
async def test_ai_account_settings(
    settings: AIAccountTestModel,
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    return await _run_ai_test(
        {
            "OPENAI_API_KEY": settings.api_key or "",
            "OPENAI_BASE_URL": settings.base_url,
            "OPENAI_MODEL_NAME": settings.model_name,
            "PROXY_URL": load_ai_runtime_values_sync().get("PROXY_URL", ""),
        }
    )


@router.post("/ai-accounts/{account_id}/test")
async def test_existing_ai_account(
    account_id: int,
    _current_user: AuthenticatedUser = Depends(require_admin_user),
):
    account = await get_ai_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="AI账号未找到")

    result = await _run_ai_test(
        {
            "OPENAI_API_KEY": account.api_key or "",
            "OPENAI_BASE_URL": account.base_url,
            "OPENAI_MODEL_NAME": account.model_name,
            "PROXY_URL": load_ai_runtime_values_sync().get("PROXY_URL", ""),
        }
    )
    updated = await record_ai_account_test_result(
        account_id,
        success=bool(result.get("success")),
        message=str(result.get("message") or ""),
    )
    return {
        **result,
        "item": redact_ai_account(updated) if updated else None,
    }


@router.get("/status")
async def get_system_status(
    process_service: ProcessService = Depends(get_process_service),
):
    state_file = "xianyu_state.json"
    login_state_exists = has_default_login_state_sync()
    env_file_exists = os.path.exists(env_manager.env_file)
    notification_settings = load_notification_settings()
    running_task_ids = [
        task_id
        for task_id, process in process_service.processes.items()
        if process and process.returncode is None
    ]

    return {
        "ai_configured": await has_configured_ai_provider(),
        "notification_configured": notification_settings.has_any_notification_enabled(),
        "headless_mode": scraper_settings.run_headless,
        "running_in_docker": scraper_settings.running_in_docker,
        "scraper_running": len(running_task_ids) > 0,
        "running_task_ids": running_task_ids,
        "login_state_file": {
            "exists": login_state_exists,
            "path": state_file,
        },
        "env_file": {
            "exists": env_file_exists,
            **build_notification_status_flags(notification_settings),
        },
        "failure_guard": load_failure_guard_settings_sync(),
        "configured_notification_channels": build_configured_channels(notification_settings),
    }


async def _run_ai_test(settings: dict):
    try:
        from openai import OpenAI
        import httpx

        client_params = {
            "api_key": settings.get("OPENAI_API_KEY", ""),
            "base_url": settings.get("OPENAI_BASE_URL", ""),
            "timeout": httpx.Timeout(30.0),
        }

        proxy_url = settings.get("PROXY_URL", "")
        if proxy_url:
            client_params["http_client"] = httpx.Client(proxy=proxy_url)

        model_name = settings.get("OPENAI_MODEL_NAME", "")
        client = OpenAI(**client_params)
        messages = [{"role": "user", "content": AI_TEST_PROMPT}]
        api_mode = CHAT_COMPLETIONS_API_MODE

        try:
            response = create_ai_response_sync(
                client,
                api_mode,
                build_ai_request_params(
                    api_mode,
                    model=model_name,
                    messages=messages,
                    max_output_tokens=AI_TEST_MAX_OUTPUT_TOKENS,
                ),
            )
        except Exception as exc:
            if not is_chat_completions_api_unsupported_error(exc):
                raise
            api_mode = RESPONSES_API_MODE
            response = create_ai_response_sync(
                client,
                api_mode,
                build_ai_request_params(
                    api_mode,
                    model=model_name,
                    messages=messages,
                    max_output_tokens=AI_TEST_MAX_OUTPUT_TOKENS,
                ),
            )

        return {
            "success": True,
            "message": "AI模型连接测试成功！",
            "response": extract_ai_response_content(response),
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"AI模型连接测试失败: {_compact_ai_test_error(exc)}",
        }
