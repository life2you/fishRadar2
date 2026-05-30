from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.ai_request_compat import (
    CHAT_COMPLETIONS_API_MODE,
    RESPONSES_API_MODE,
    build_ai_request_params,
    create_ai_response_sync,
    is_chat_completions_api_unsupported_error,
)
from src.services.ai_response_parser import extract_ai_response_content
from src.infrastructure.persistence.mysql_connection import mysql_connection
from src.services.platform_settings_service import load_ai_runtime_values_sync

AI_TEST_PROMPT = "Reply with OK only."
AI_TEST_MAX_OUTPUT_TOKENS = 32


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def compact_error(exc: Exception) -> str:
    return str(exc).strip()[:140] or exc.__class__.__name__


async def main() -> int:
    raw = {}
    try:
        raw = json.loads(sys.stdin.read() or "{}")
        api_key = str(raw.get("api_key") or "")
        base_url = str(raw.get("base_url") or "")
        model_name = str(raw.get("model_name") or "")
        account_id = raw.get("account_id")
        proxy_url = load_ai_runtime_values_sync().get("PROXY_URL", "")

        from openai import OpenAI
        import httpx

        client_params = {
            "api_key": api_key,
            "base_url": base_url,
            "timeout": httpx.Timeout(30.0),
        }
        if proxy_url:
            client_params["http_client"] = httpx.Client(proxy=proxy_url)

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

        payload = {
            "success": True,
            "message": "AI模型连接测试成功！",
            "response": extract_ai_response_content(response),
        }
        if account_id is not None:
            now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
            with mysql_connection() as conn:
                conn.execute(
                    """
                    UPDATE ai_accounts
                    SET last_test_status = ?, last_test_message = ?, last_tested_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    ("success", payload["message"], now, now, int(account_id)),
                )
                conn.commit()
        emit({"type": "result", "payload": payload})
        return 0
    except Exception as exc:
        payload = {
            "success": False,
            "message": f"AI模型连接测试失败: {compact_error(exc)}",
        }
        account_id = raw.get("account_id")
        if account_id is not None:
            now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
            with mysql_connection() as conn:
                conn.execute(
                    """
                    UPDATE ai_accounts
                    SET last_test_status = ?, last_test_message = ?, last_tested_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    ("failed", payload["message"], now, now, int(account_id)),
                )
                conn.commit()
        emit({"type": "result", "payload": payload})
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
