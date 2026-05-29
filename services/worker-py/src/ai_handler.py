"""
兼容层：保留旧 ai_handler 导出，内部统一转向新的服务实现。
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from src.infrastructure.external.ai_client import AIClient
from src.services.ai_account_service import list_ai_route_candidates
from src.services.image_runtime_service import (
    DEFAULT_IMAGE_DOWNLOAD_CONCURRENCY,
    IMAGE_DOWNLOAD_HEADERS,
    _build_image_save_path,
    _download_single_image,
    download_all_images,
    cleanup_task_images,
)
from src.services.notification_service import build_notification_service


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            print(text.encode("ascii", errors="ignore").decode("ascii"))
        except Exception:
            print("[输出包含无法显示的字符]")


def cleanup_ai_logs(logs_dir: str, keep_days: int = 1) -> None:
    try:
        cutoff = datetime.now() - timedelta(days=keep_days)
        for filename in os.listdir(logs_dir):
            if not filename.endswith(".log"):
                continue
            try:
                timestamp = datetime.strptime(filename[:15], "%Y%m%d_%H%M%S")
            except ValueError:
                continue
            if timestamp < cutoff:
                os.remove(os.path.join(logs_dir, filename))
    except Exception as exc:
        safe_print(f"   [日志] 清理AI日志时出错: {exc}")


def encode_image_to_base64(image_path: str):
    return AIClient.encode_image(image_path)


def validate_ai_response_format(parsed_response) -> bool:
    required_fields = [
        "prompt_version",
        "is_recommended",
        "reason",
        "risk_tags",
        "criteria_analysis",
    ]
    for field in required_fields:
        if field not in parsed_response:
            safe_print(f"   [AI分析] 警告：响应缺少必需字段 '{field}'")
            return False

    criteria_analysis = parsed_response.get("criteria_analysis", {})
    if not isinstance(criteria_analysis, dict) or not criteria_analysis:
        safe_print("   [AI分析] 警告：criteria_analysis必须是非空字典")
        return False

    if "seller_type" not in criteria_analysis:
        safe_print("   [AI分析] 警告：criteria_analysis缺少必需字段 'seller_type'")
        return False

    if not isinstance(parsed_response.get("is_recommended"), bool):
        safe_print("   [AI分析] 警告：is_recommended字段不是布尔类型")
        return False

    if not isinstance(parsed_response.get("risk_tags"), list):
        safe_print("   [AI分析] 警告：risk_tags字段不是列表类型")
        return False

    return True


async def send_ntfy_notification(product_data, reason, tenant_id=None):
    """兼容旧调用名，内部统一走 NotificationService。"""
    service = build_notification_service(tenant_id=tenant_id)
    if not service.clients:
        if tenant_id is None:
            safe_print("警告：未配置任何通知服务，跳过通知。")
        else:
            safe_print(f"警告：租户 {tenant_id} 未配置任何通知服务，跳过通知。")
        return {}

    results = await service.send_notification(product_data, reason)
    for channel, result in results.items():
        if result["success"]:
            safe_print(f"   -> {channel} 通知发送成功。")
        else:
            safe_print(f"   -> {channel} 通知发送失败: {result['message']}")
    return results


async def get_ai_analysis(product_data, image_paths=None, prompt_text=""):
    """
    兼容旧 AI 分析入口。

    主运行链路已经统一走 AIAnalysisService / AIClient，这里仅保留给旧脚本或
    外部调用使用，直接委托默认 AIClient 执行。
    """
    if not prompt_text:
        safe_print("   [AI分析] 错误：未提供AI分析所需的prompt文本。")
        return None

    candidates = await list_ai_route_candidates(require_images=bool(image_paths))
    if not candidates:
        safe_print("   [AI分析] 错误：当前没有可用的 AI 账号。")
        return None
    for account in candidates:
        client = AIClient(account)
        if not client.is_available():
            await client.close()
            continue
        try:
            result = await client.analyze(product_data, image_paths or [], prompt_text)
            if result and validate_ai_response_format(result):
                return result
        finally:
            await client.close()
    return None


__all__ = [
    "AIClient",
    "DEFAULT_IMAGE_DOWNLOAD_CONCURRENCY",
    "IMAGE_DOWNLOAD_HEADERS",
    "_build_image_save_path",
    "_download_single_image",
    "cleanup_ai_logs",
    "cleanup_task_images",
    "download_all_images",
    "encode_image_to_base64",
    "get_ai_analysis",
    "safe_print",
    "send_ntfy_notification",
    "validate_ai_response_format",
]
