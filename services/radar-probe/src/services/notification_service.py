"""
通知服务
统一管理所有通知渠道
"""
import asyncio
from typing import Dict, List

from src.infrastructure.external.notification_clients.base import NotificationClient
from src.infrastructure.external.notification_clients.factory import build_notification_clients
from src.services.notification_config_service import load_notification_settings
from src.infrastructure.config.settings import NotificationSettings
from src.services.tenant_notification_settings_service import (
    load_tenant_notification_settings_sync,
)


class NotificationService:
    """通知服务"""

    def __init__(self, clients: List[NotificationClient]):
        self.clients = [client for client in clients if client.is_enabled()]

    async def send_notification(
        self,
        product_data: Dict,
        reason: str,
    ) -> Dict[str, Dict[str, str | bool]]:
        """
        发送通知到所有启用的渠道

        Returns:
            各渠道发送结果，包含成功状态和消息
        """
        if not self.clients:
            return {}

        tasks = [
            self._send_with_result(client, product_data, reason)
            for client in self.clients
        ]
        results = await asyncio.gather(*tasks)
        return {result["channel"]: result for result in results}

    async def send_test_notification(self) -> Dict[str, Dict[str, str | bool]]:
        test_product = {
            "商品标题": "[测试通知] 闲鱼智能监控",
            "当前售价": "0",
            "商品链接": "https://www.goofish.com/",
        }
        return await self.send_notification(
            test_product,
            "这是一条测试通知，用于验证推送渠道是否可用。",
        )

    async def _send_with_result(
        self,
        client: NotificationClient,
        product_data: Dict,
        reason: str,
    ) -> Dict[str, str | bool]:
        try:
            await client.send(product_data, reason)
            return {
                "channel": client.channel_key,
                "label": client.display_name,
                "success": True,
                "message": "发送成功",
            }
        except Exception as exc:
            return {
                "channel": client.channel_key,
                "label": client.display_name,
                "success": False,
                "message": str(exc),
            }


def build_notification_service(
    settings: NotificationSettings | None = None,
    *,
    tenant_id: int | None = None,
) -> NotificationService:
    if settings is not None:
        notification_settings = settings
    elif tenant_id is not None:
        notification_settings = load_tenant_notification_settings_sync(tenant_id)
    else:
        notification_settings = load_notification_settings()
    return NotificationService(build_notification_clients(notification_settings))


async def send_product_notification(
    product_data: Dict,
    reason: str,
    tenant_id: int | None = None,
) -> Dict[str, Dict[str, str | bool]]:
    service = build_notification_service(tenant_id=tenant_id)
    if not service.clients:
        if tenant_id is None:
            print("警告：当前未配置任何通知渠道，跳过通知。")
        else:
            print(f"警告：租户 {tenant_id} 未配置任何通知渠道，跳过通知。")
        return {}
    return await service.send_notification(product_data, reason)
