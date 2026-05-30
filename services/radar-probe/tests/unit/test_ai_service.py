import asyncio

from src.domain.models.ai_account import AIAccount
from src.services.ai_service import AIAnalysisService


def test_analyze_product_requests_image_candidates(monkeypatch):
    observed = {"require_images": None}

    async def fake_candidates(*, require_images: bool):
        observed["require_images"] = require_images
        return []

    monkeypatch.setattr("src.services.ai_service.list_ai_route_candidates", fake_candidates)

    result = asyncio.run(
        AIAnalysisService(ai_client=object()).analyze_product(
            product_data={"title": "Sony A7"},
            image_paths=["/tmp/a.jpg"],
            prompt_text="analyze",
        )
    )

    assert result is None
    assert observed["require_images"] is True


def test_analyze_product_falls_back_to_next_account(monkeypatch):
    call_order: list[str] = []
    closed_accounts: list[str] = []

    accounts = [
        AIAccount(
            id=1,
            name="text-primary",
            api_key="sk-1",
            base_url="https://example.com/v1",
            model_name="text-model",
            supports_text=True,
            supports_image=False,
            enabled=True,
            priority=1,
        ),
        AIAccount(
            id=2,
            name="text-secondary",
            api_key="sk-2",
            base_url="https://example.com/v1",
            model_name="text-model-2",
            supports_text=True,
            supports_image=False,
            enabled=True,
            priority=2,
        ),
    ]

    async def fake_candidates(*, require_images: bool):
        assert require_images is False
        return accounts

    class FakeAIClient:
        def __init__(self, account=None):
            self.account = account

        def is_available(self):
            return True

        async def analyze(self, *_args, **_kwargs):
            call_order.append(self.account.name)
            if self.account.name == "text-primary":
                raise RuntimeError("primary failed")
            return {
                "prompt_version": "v1",
                "is_recommended": True,
                "reason": "looks good",
                "risk_tags": [],
                "criteria_analysis": {"price": "ok"},
            }

        async def close(self):
            closed_accounts.append(self.account.name)

    monkeypatch.setattr("src.services.ai_service.list_ai_route_candidates", fake_candidates)
    monkeypatch.setattr("src.services.ai_service.AIClient", FakeAIClient)

    result = asyncio.run(
        AIAnalysisService(ai_client=object()).analyze_product(
            product_data={"title": "Sony A7"},
            image_paths=[],
            prompt_text="analyze",
        )
    )

    assert result is not None
    assert result["is_recommended"] is True
    assert call_order == ["text-primary", "text-secondary"]
    assert closed_accounts == ["text-primary", "text-secondary"]
