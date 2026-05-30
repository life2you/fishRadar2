"""
租户可用通知渠道开关服务
"""
from __future__ import annotations

import asyncio
import json

from src.infrastructure.persistence.mysql_connection import mysql_connection
from src.services.notification_config_service import (
    build_configured_channels,
    load_notification_settings,
    normalize_notification_channels,
)


TENANT_NOTIFICATION_CHANNELS_KEY = "tenant_notification_channels"


def get_tenant_notification_channels_sync() -> list[str]:
    with mysql_connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_metadata WHERE `key` = ?",
            (TENANT_NOTIFICATION_CHANNELS_KEY,),
        ).fetchone()

    if row is None or not row.get("value"):
        return build_configured_channels(load_notification_settings())

    try:
        parsed = json.loads(str(row["value"]))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return normalize_notification_channels(parsed)


async def get_tenant_notification_channels() -> list[str]:
    return await asyncio.to_thread(get_tenant_notification_channels_sync)


def save_tenant_notification_channels_sync(channels: list[str]) -> list[str]:
    normalized = normalize_notification_channels(channels)
    payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    with mysql_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_metadata(`key`, value) VALUES (?, ?)",
            (TENANT_NOTIFICATION_CHANNELS_KEY, payload),
        )
        conn.commit()
    return normalized


async def save_tenant_notification_channels(channels: list[str]) -> list[str]:
    return await asyncio.to_thread(save_tenant_notification_channels_sync, channels)
