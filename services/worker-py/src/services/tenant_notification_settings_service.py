"""
租户级通知配置服务
"""
from __future__ import annotations

import json
from datetime import datetime

from src.infrastructure.config.settings import DEFAULT_TELEGRAM_API_BASE_URL
from src.infrastructure.persistence.mysql_connection import mysql_connection
from src.services.notification_config_service import (
    NotificationSettingsValidationError,
    build_configured_channels,
    build_notification_settings_from_values,
    build_notification_settings_response,
    notification_settings_to_values,
    prepare_notification_settings_update,
    prepare_notification_test_settings,
)


def _default_notification_values() -> dict:
    return {
        "ntfy_topic_url": None,
        "gotify_url": None,
        "gotify_token": None,
        "bark_url": None,
        "wx_bot_url": None,
        "telegram_bot_token": None,
        "telegram_chat_id": None,
        "telegram_api_base_url": DEFAULT_TELEGRAM_API_BASE_URL,
        "webhook_url": None,
        "webhook_method": "POST",
        "webhook_headers": None,
        "webhook_content_type": "JSON",
        "webhook_query_parameters": None,
        "webhook_body": None,
        "pcurl_to_mobile": True,
    }


def load_tenant_notification_settings_sync(tenant_id: int):
    with mysql_connection() as conn:
        row = conn.execute(
            """
            SELECT settings_json
            FROM tenant_notification_settings
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        ).fetchone()

    if row is None or not row.get("settings_json"):
        return build_notification_settings_from_values(_default_notification_values())

    stored_values = json.loads(row["settings_json"])
    values = _default_notification_values()
    values.update(stored_values)
    return build_notification_settings_from_values(values)


async def load_tenant_notification_settings(tenant_id: int):
    from asyncio import to_thread

    return await to_thread(load_tenant_notification_settings_sync, tenant_id)


def get_tenant_notification_settings_response_sync(tenant_id: int) -> dict:
    return build_notification_settings_response(
        load_tenant_notification_settings_sync(tenant_id),
    )


async def get_tenant_notification_settings_response(tenant_id: int) -> dict:
    from asyncio import to_thread

    return await to_thread(get_tenant_notification_settings_response_sync, tenant_id)


def save_tenant_notification_settings_sync(tenant_id: int, patch_payload: dict) -> dict:
    existing_settings = load_tenant_notification_settings_sync(tenant_id)
    _, _, merged_settings = prepare_notification_settings_update(
        patch_payload,
        existing_settings,
    )
    settings_json = json.dumps(
        notification_settings_to_values(merged_settings),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    updated_at = datetime.now().isoformat()

    with mysql_connection() as conn:
        conn.execute(
            """
            INSERT INTO tenant_notification_settings (
                tenant_id, settings_json, updated_at
            ) VALUES (?, ?, ?)
            ON DUPLICATE KEY UPDATE
                settings_json = VALUES(settings_json),
                updated_at = VALUES(updated_at)
            """,
            (tenant_id, settings_json, updated_at),
        )
        conn.commit()

    return {
        "message": "租户通知设置已更新",
        "configured_channels": build_configured_channels(merged_settings),
    }


async def save_tenant_notification_settings(tenant_id: int, patch_payload: dict) -> dict:
    from asyncio import to_thread

    return await to_thread(save_tenant_notification_settings_sync, tenant_id, patch_payload)


def build_tenant_notification_test_settings_sync(
    tenant_id: int,
    patch_payload: dict,
    *,
    channel: str | None = None,
):
    existing_settings = load_tenant_notification_settings_sync(tenant_id)
    return prepare_notification_test_settings(
        patch_payload,
        existing_settings,
        channel=channel,
    )


async def build_tenant_notification_test_settings(
    tenant_id: int,
    patch_payload: dict,
    *,
    channel: str | None = None,
):
    from asyncio import to_thread

    return await to_thread(
        build_tenant_notification_test_settings_sync,
        tenant_id,
        patch_payload,
        channel=channel,
    )


__all__ = [
    "NotificationSettingsValidationError",
    "build_tenant_notification_test_settings",
    "build_tenant_notification_test_settings_sync",
    "get_tenant_notification_settings_response",
    "get_tenant_notification_settings_response_sync",
    "load_tenant_notification_settings",
    "load_tenant_notification_settings_sync",
    "save_tenant_notification_settings",
    "save_tenant_notification_settings_sync",
]
