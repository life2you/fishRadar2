from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.notification_service import build_notification_service
from src.services.notification_config_service import (
    NotificationSettingsValidationError,
    assert_notification_patch_allowed,
    load_notification_settings,
    model_dump,
    prepare_notification_test_settings,
)
from src.services.tenant_notification_access_service import get_tenant_notification_channels
from src.services.tenant_notification_settings_service import (
    build_tenant_notification_test_settings,
)


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


async def main() -> int:
    try:
        raw = json.loads(sys.stdin.read() or "{}")
        scope = str(raw.get("scope") or "platform")
        channel = raw.get("channel")
        settings = raw.get("settings") or {}

        if scope == "tenant":
            tenant_id = int(raw.get("tenant_id") or 0)
            available_channels = await get_tenant_notification_channels()
            assert_notification_patch_allowed(settings, available_channels)
            if channel and channel not in available_channels:
                raise NotificationSettingsValidationError(f"渠道 {channel} 当前未向租户开放")
            merged = await build_tenant_notification_test_settings(
                tenant_id,
                settings,
                channel=channel,
            )
        else:
            merged = prepare_notification_test_settings(
                settings,
                load_notification_settings(),
                channel=channel,
            )

        service = build_notification_service(merged)
        if not service.clients:
            if channel:
                raise NotificationSettingsValidationError(f"渠道 {channel} 未配置或不受支持")
            raise NotificationSettingsValidationError("请至少配置一个可用的通知渠道")

        results = await service.send_test_notification()
        if channel:
            if channel not in results:
                raise NotificationSettingsValidationError(f"渠道 {channel} 未配置或不受支持")
            results = {channel: results[channel]}
        emit({"type": "result", "payload": {"message": "测试通知已执行", "results": results}})
        return 0
    except Exception as exc:
        emit({"type": "error", "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
