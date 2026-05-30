"""
AI 分析服务
封装 AI 分析相关的业务逻辑
"""
from typing import Dict, List, Optional

from src.infrastructure.external.ai_client import AIClient
from src.services.ai_account_service import list_ai_route_candidates


class AIAnalysisService:
    """AI 分析服务"""

    def __init__(self, ai_client: AIClient | None = None):
        self.ai_client = ai_client or AIClient()

    async def analyze_product(
        self,
        product_data: Dict,
        image_paths: List[str],
        prompt_text: str
    ) -> Optional[Dict]:
        """
        分析商品

        Args:
            product_data: 商品数据
            image_paths: 图片路径列表
            prompt_text: 分析提示词

        Returns:
            分析结果
        """
        require_images = bool(image_paths)
        candidates = await list_ai_route_candidates(require_images=require_images)
        if not candidates:
            print("没有可用的 AI 账号可执行当前分析")
            return None

        last_error: Exception | None = None
        for account in candidates:
            client = AIClient(account if account.id != 0 else None)
            if not client.is_available():
                continue
            try:
                result = await client.analyze(product_data, image_paths, prompt_text)
                if result and self._validate_result(result):
                    return result
                print(f"AI 分析结果验证失败，账号: {account.name}")
            except Exception as e:
                last_error = e
                print(f"AI 分析服务出错，账号 {account.name}: {e}")
            finally:
                await client.close()

        if last_error:
            print(f"AI 分析全部候选账号失败: {last_error}")
        return None

    def _validate_result(self, result: Dict) -> bool:
        """验证 AI 分析结果的格式"""
        required_fields = [
            "prompt_version",
            "is_recommended",
            "reason",
            "risk_tags",
            "criteria_analysis"
        ]

        # 检查必需字段
        for field in required_fields:
            if field not in result:
                print(f"AI 响应缺少必需字段: {field}")
                return False

        # 检查数据类型
        if not isinstance(result.get("is_recommended"), bool):
            print("is_recommended 字段不是布尔类型")
            return False

        if not isinstance(result.get("risk_tags"), list):
            print("risk_tags 字段不是列表类型")
            return False

        criteria_analysis = result.get("criteria_analysis", {})
        if not isinstance(criteria_analysis, dict) or not criteria_analysis:
            print("criteria_analysis 必须是非空字典")
            return False

        return True
