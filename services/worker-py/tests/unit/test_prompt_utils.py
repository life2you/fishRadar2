import asyncio

import pytest

import src.prompt_utils as prompt_utils
from src.domain.models.ai_account import AIAccount
from src.services.ai_response_parser import EmptyAIResponseError


def test_generate_criteria_closes_ai_client_after_success(monkeypatch, tmp_path):
    close_state = {"closed": False}

    class FakeAIClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def is_available(self):
            return True

        def refresh(self):
            raise AssertionError("refresh should not be called")

        async def _call_ai(self, *_args, **_kwargs):
            return "generated criteria"

        async def close(self):
            close_state["closed"] = True

    monkeypatch.setattr(prompt_utils, "AIClient", FakeAIClient)
    monkeypatch.setattr(
        prompt_utils,
        "list_ai_route_candidates",
        lambda **_kwargs: _resolved_candidates(),
    )
    monkeypatch.setattr(
        prompt_utils,
        "get_prompt_content",
        lambda _path: "reference",
    )

    result = asyncio.run(
        prompt_utils.generate_criteria("need a gpu", "prompts/reference.txt")
    )

    assert result == "generated criteria"
    assert close_state["closed"] is True


def test_generate_criteria_closes_ai_client_after_ai_failure(monkeypatch, tmp_path):
    close_state = {"closed": False}

    class FakeAIClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def is_available(self):
            return True

        def refresh(self):
            raise AssertionError("refresh should not be called")

        async def _call_ai(self, *_args, **_kwargs):
            raise EmptyAIResponseError("AI响应内容为空。")

        async def close(self):
            close_state["closed"] = True

    monkeypatch.setattr(prompt_utils, "AIClient", FakeAIClient)
    monkeypatch.setattr(
        prompt_utils,
        "list_ai_route_candidates",
        lambda **_kwargs: _resolved_candidates(),
    )
    monkeypatch.setattr(
        prompt_utils,
        "get_prompt_content",
        lambda _path: "reference",
    )

    with pytest.raises(RuntimeError, match="所有 AI 账号生成分析标准均失败: AI响应内容为空"):
        asyncio.run(prompt_utils.generate_criteria("need a gpu", "prompts/reference.txt"))

    assert close_state["closed"] is True


async def _resolved_candidates():
    return [
        AIAccount(
            id=1,
            name="text-account",
            api_key="sk-test",
            base_url="https://example.com/v1",
            model_name="demo-model",
            supports_text=True,
            supports_image=False,
            enabled=True,
            priority=1,
        )
    ]
