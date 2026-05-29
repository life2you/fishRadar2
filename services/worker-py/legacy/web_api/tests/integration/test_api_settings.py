import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api import dependencies as deps
from api.routes import settings
from src.domain.models.auth import AuthenticatedUser
from src.infrastructure.config.env_manager import env_manager
from src.infrastructure.persistence.mysql_connection import mysql_connection


_SETTINGS_ENV_KEYS = [
    "ACCOUNT_ROTATION_ENABLED",
    "ACCOUNT_ROTATION_MODE",
    "ACCOUNT_ROTATION_RETRY_LIMIT",
    "ACCOUNT_BLACKLIST_TTL",
    "PROXY_ROTATION_ENABLED",
    "PROXY_ROTATION_MODE",
    "PROXY_POOL",
    "PROXY_ROTATION_RETRY_LIMIT",
    "PROXY_BLACKLIST_TTL",
    "AI_DEBUG_MODE",
    "ENABLE_RESPONSE_FORMAT",
    "ENABLE_THINKING",
    "SKIP_AI_ANALYSIS",
    "AI_ANALYSIS_CONCURRENCY",
    "SELLER_PROFILE_CACHE_TTL",
    "PROXY_URL",
    "TASK_FAILURE_THRESHOLD",
    "TASK_FAILURE_PAUSE_SECONDS",
    "TASK_FAILURE_TZ",
    "NTFY_TOPIC_URL",
    "GOTIFY_URL",
    "GOTIFY_TOKEN",
    "BARK_URL",
    "WX_BOT_URL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_API_BASE_URL",
    "WEBHOOK_URL",
    "WEBHOOK_METHOD",
    "WEBHOOK_HEADERS",
    "WEBHOOK_CONTENT_TYPE",
    "WEBHOOK_QUERY_PARAMETERS",
    "WEBHOOK_BODY",
    "PCURL_TO_MOBILE",
]


class _IdleProcessService:
    def __init__(self) -> None:
        self.processes = {}


def _build_settings_client() -> TestClient:
    app = FastAPI()
    app.include_router(settings.router)
    app.dependency_overrides[deps.get_process_service] = _IdleProcessService
    async def _admin_user():
        return AuthenticatedUser(
            user_id=1,
            username="admin",
            role="admin",
            tenant_id=1,
            tenant_name="Platform Admin",
            tenant_status="active",
            tenant_ai_enabled=True,
            tenant_activation_required=False,
            tenant_activated_at="2026-01-01T00:00:00",
        )
    app.dependency_overrides[deps.require_admin_user] = _admin_user
    return TestClient(app)


def _read_app_metadata_value(key: str) -> str | None:
    with mysql_connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_metadata WHERE `key` = ?",
            (key,),
        ).fetchone()
    return None if row is None else row.get("value")


def _clear_settings_env(monkeypatch) -> None:
    for key in _SETTINGS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_rotation_settings_include_account_rotation_fields(tmp_path, monkeypatch, mysql_test_env):
    _clear_settings_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "ACCOUNT_ROTATION_ENABLED=false",
                "ACCOUNT_ROTATION_MODE=per_task",
                "ACCOUNT_ROTATION_RETRY_LIMIT=2",
                "ACCOUNT_BLACKLIST_TTL=300",
                "PROXY_ROTATION_ENABLED=false",
                "PROXY_ROTATION_MODE=per_task",
                "PROXY_ROTATION_RETRY_LIMIT=2",
                "PROXY_BLACKLIST_TTL=300",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(env_manager, "env_file", env_file)

    client = _build_settings_client()

    response = client.get("/api/settings/rotation")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ACCOUNT_ROTATION_ENABLED"] is False
    assert payload["ACCOUNT_ROTATION_MODE"] == "per_task"

    update_response = client.put(
        "/api/settings/rotation",
        json={
            "ACCOUNT_ROTATION_ENABLED": True,
            "ACCOUNT_ROTATION_MODE": "on_failure",
            "ACCOUNT_ROTATION_RETRY_LIMIT": 4,
            "ACCOUNT_BLACKLIST_TTL": 900,
        },
    )
    assert update_response.status_code == 200

    latest = client.get("/api/settings/rotation")
    assert latest.status_code == 200
    latest_payload = latest.json()
    assert latest_payload["ACCOUNT_ROTATION_ENABLED"] is True
    assert latest_payload["ACCOUNT_ROTATION_MODE"] == "on_failure"
    assert latest_payload["ACCOUNT_ROTATION_RETRY_LIMIT"] == 4
    assert latest_payload["ACCOUNT_BLACKLIST_TTL"] == 900
    stored = json.loads(_read_app_metadata_value("platform:rotation_settings") or "{}")
    assert stored["ACCOUNT_ROTATION_ENABLED"] is True
    assert stored["ACCOUNT_ROTATION_MODE"] == "on_failure"


def test_notification_settings_redact_sensitive_values_and_expose_flags(tmp_path, monkeypatch, mysql_test_env):
    _clear_settings_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "NTFY_TOPIC_URL=https://ntfy.sh/demo-topic",
                "GOTIFY_URL=https://gotify.example.com",
                "GOTIFY_TOKEN=secret-token",
                "BARK_URL=https://api.day.app/private-key/",
                "WX_BOT_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret",
                "TELEGRAM_BOT_TOKEN=telegram-secret",
                "TELEGRAM_CHAT_ID=123456",
                "TELEGRAM_API_BASE_URL=https://tg.example.com/proxy",
                "WEBHOOK_URL=https://hooks.example.com/notify?token=secret",
                'WEBHOOK_HEADERS={"Authorization":"Bearer secret"}',
                'WEBHOOK_BODY={"message":"{{content}}"}',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(env_manager, "env_file", env_file)
    client = _build_settings_client()

    response = client.get("/api/settings/notifications")

    assert response.status_code == 200
    payload = response.json()
    assert payload["NTFY_TOPIC_URL"] == "https://ntfy.sh/demo-topic"
    assert payload["GOTIFY_URL"] == "https://gotify.example.com"
    assert payload["TELEGRAM_CHAT_ID"] == "123456"
    assert payload["TELEGRAM_API_BASE_URL"] == "https://tg.example.com/proxy"
    assert payload["BARK_URL"] == ""
    assert payload["WX_BOT_URL"] == ""
    assert payload["GOTIFY_TOKEN"] == ""
    assert payload["TELEGRAM_BOT_TOKEN"] == ""
    assert payload["WEBHOOK_URL"] == ""
    assert payload["WEBHOOK_HEADERS"] == ""
    assert payload["BARK_URL_SET"] is True
    assert payload["WX_BOT_URL_SET"] is True
    assert payload["GOTIFY_TOKEN_SET"] is True
    assert payload["TELEGRAM_BOT_TOKEN_SET"] is True
    assert payload["WEBHOOK_URL_SET"] is True
    assert payload["WEBHOOK_HEADERS_SET"] is True
    assert payload["WEBHOOK_BODY"] == '{"message":"{{content}}"}'


def test_update_notification_settings_rejects_invalid_channel_config(tmp_path, monkeypatch, mysql_test_env):
    _clear_settings_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(env_manager, "env_file", env_file)
    client = _build_settings_client()

    gotify_response = client.put(
        "/api/settings/notifications",
        json={"GOTIFY_URL": "https://gotify.example.com"},
    )
    assert gotify_response.status_code == 422
    assert "GOTIFY_TOKEN" in gotify_response.text

    telegram_proxy_response = client.put(
        "/api/settings/notifications",
        json={"TELEGRAM_API_BASE_URL": "not-a-url"},
    )
    assert telegram_proxy_response.status_code == 422
    assert "TELEGRAM_API_BASE_URL" in telegram_proxy_response.text

    webhook_response = client.put(
        "/api/settings/notifications",
        json={
            "WEBHOOK_URL": "https://hooks.example.com/notify",
            "WEBHOOK_METHOD": "POST",
            "WEBHOOK_CONTENT_TYPE": "JSON",
            "WEBHOOK_HEADERS": '{"Authorization": "Bearer secret"',
        },
    )
    assert webhook_response.status_code == 422
    assert "WEBHOOK_HEADERS" in webhook_response.text


def test_system_status_includes_notification_channel_flags(tmp_path, monkeypatch, mysql_test_env):
    _clear_settings_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "NTFY_TOPIC_URL=https://ntfy.sh/demo-topic",
                "GOTIFY_URL=https://gotify.example.com",
                "GOTIFY_TOKEN=secret-token",
                "BARK_URL=https://api.day.app/private-key/",
                "WX_BOT_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret",
                "TELEGRAM_BOT_TOKEN=telegram-secret",
                "TELEGRAM_CHAT_ID=123456",
                "WEBHOOK_URL=https://hooks.example.com/notify",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(env_manager, "env_file", env_file)
    client = _build_settings_client()

    response = client.get("/api/settings/status")

    assert response.status_code == 200
    env_payload = response.json()["env_file"]
    assert env_payload["ntfy_topic_url_set"] is True
    assert env_payload["gotify_url_set"] is True
    assert env_payload["gotify_token_set"] is True
    assert env_payload["bark_url_set"] is True
    assert env_payload["wx_bot_url_set"] is True
    assert env_payload["telegram_bot_token_set"] is True
    assert env_payload["telegram_chat_id_set"] is True
    assert env_payload["webhook_url_set"] is True


def test_notification_test_endpoint_merges_stored_secret_values(tmp_path, monkeypatch, mysql_test_env):
    _clear_settings_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TELEGRAM_BOT_TOKEN=stored-token",
                "TELEGRAM_CHAT_ID=10001",
                "TELEGRAM_API_BASE_URL=https://tg-proxy.example.com/base",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(env_manager, "env_file", env_file)
    client = _build_settings_client()

    captured = {}

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)

    response = client.post(
        "/api/settings/notifications/test",
        json={
            "channel": "telegram",
            "settings": {
                "TELEGRAM_CHAT_ID": "20002",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]["telegram"]["success"] is True
    assert captured["url"] == "https://tg-proxy.example.com/base/botstored-token/sendMessage"
    assert captured["json"]["chat_id"] == "20002"


def test_notification_test_endpoint_ignores_other_channel_dirty_fields(tmp_path, monkeypatch, mysql_test_env):
    _clear_settings_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NTFY_TOPIC_URL=https://ntfy.sh/demo-topic\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(env_manager, "env_file", env_file)
    client = _build_settings_client()

    captured = []

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    def _fake_post(url, data=None, headers=None, timeout=None, **kwargs):
        captured.append({
            "url": url,
            "data": data,
            "headers": headers,
        })
        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)

    response = client.post(
        "/api/settings/notifications/test",
        json={
            "channel": "ntfy",
            "settings": {
                "GOTIFY_URL": "not-a-url",
                "WEBHOOK_BODY": '{"message":"{{content}}"}',
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert list(payload["results"]) == ["ntfy"]
    assert payload["results"]["ntfy"]["success"] is True
    assert len(captured) == 1
    assert captured[0]["url"] == "https://ntfy.sh/demo-topic"


def test_notification_settings_fall_back_to_runtime_environment_when_env_file_missing(
    tmp_path, monkeypatch, mysql_test_env
):
    _clear_settings_env(monkeypatch)
    env_file = tmp_path / ".env"
    monkeypatch.setattr(env_manager, "env_file", env_file)
    monkeypatch.setenv("NTFY_TOPIC_URL", "https://ntfy.sh/runtime-topic")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "runtime-telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "20001")
    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "https://runtime-tg-proxy.example.com")
    monkeypatch.setenv("BARK_URL", "https://api.day.app/runtime-secret/")
    client = _build_settings_client()

    response = client.get("/api/settings/notifications")

    assert response.status_code == 200
    payload = response.json()
    assert payload["NTFY_TOPIC_URL"] == "https://ntfy.sh/runtime-topic"
    assert payload["TELEGRAM_CHAT_ID"] == "20001"
    assert payload["TELEGRAM_API_BASE_URL"] == "https://runtime-tg-proxy.example.com"
    assert payload["BARK_URL"] == ""
    assert payload["BARK_URL_SET"] is True
    assert payload["TELEGRAM_BOT_TOKEN_SET"] is True
    assert sorted(payload["CONFIGURED_CHANNELS"]) == ["bark", "ntfy", "telegram"]
    stored = json.loads(_read_app_metadata_value("platform:notification_settings") or "{}")
    assert stored["NTFY_TOPIC_URL"] == "https://ntfy.sh/runtime-topic"
    assert stored["TELEGRAM_CHAT_ID"] == "20001"


def test_ai_runtime_settings_round_trip(mysql_test_env):
    client = _build_settings_client()

    initial = client.get("/api/settings/ai-runtime")
    assert initial.status_code == 200
    assert initial.json()["ENABLE_RESPONSE_FORMAT"] is True

    update = client.put(
        "/api/settings/ai-runtime",
        json={
            "PROXY_URL": "http://127.0.0.1:7890",
            "AI_DEBUG_MODE": True,
            "ENABLE_THINKING": True,
            "SKIP_AI_ANALYSIS": True,
            "AI_ANALYSIS_CONCURRENCY": 4,
            "SELLER_PROFILE_CACHE_TTL": 600,
        },
    )
    assert update.status_code == 200

    latest = client.get("/api/settings/ai-runtime")
    assert latest.status_code == 200
    payload = latest.json()
    assert payload["PROXY_URL"] == "http://127.0.0.1:7890"
    assert payload["AI_DEBUG_MODE"] is True
    assert payload["ENABLE_THINKING"] is True
    assert payload["SKIP_AI_ANALYSIS"] is True
    assert payload["AI_ANALYSIS_CONCURRENCY"] == 4
    assert payload["SELLER_PROFILE_CACHE_TTL"] == 600


def test_failure_guard_settings_round_trip(mysql_test_env):
    client = _build_settings_client()

    update = client.put(
        "/api/settings/failure-guard",
        json={
            "TASK_FAILURE_THRESHOLD": 5,
            "TASK_FAILURE_PAUSE_SECONDS": 7200,
            "TASK_FAILURE_TZ": "UTC",
        },
    )
    assert update.status_code == 200

    latest = client.get("/api/settings/failure-guard")
    assert latest.status_code == 200
    payload = latest.json()
    assert payload["TASK_FAILURE_THRESHOLD"] == 5
    assert payload["TASK_FAILURE_PAUSE_SECONDS"] == 7200
    assert payload["TASK_FAILURE_TZ"] == "UTC"


def test_ai_account_crud_round_trip(mysql_test_env):
    client = _build_settings_client()

    create_response = client.post(
        "/api/settings/ai-accounts",
        json={
            "name": "图片主账号",
            "api_key": "sk-demo",
            "base_url": "https://example.com/v1",
            "model_name": "demo-vision",
            "supports_image": True,
            "supports_text": False,
            "enabled": True,
            "priority": 10,
            "notes": "只处理图片任务",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()["item"]
    assert created["name"] == "图片主账号"
    assert created["api_key"] == ""
    assert created["api_key_set"] is True

    list_response = client.get("/api/settings/ai-accounts")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["supports_image"] is True
    assert items[0]["supports_text"] is False
    assert items[0]["last_test_status"] is None

    account_id = created["id"]
    update_response = client.patch(
        f"/api/settings/ai-accounts/{account_id}",
        json={
            "supports_text": True,
            "priority": 5,
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()["item"]
    assert updated["supports_text"] is True
    assert updated["priority"] == 5

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = self
            self.chat = type("_Chat", (), {"completions": self})()

        def create(self, **kwargs):
            if "messages" in kwargs:
                raise Exception("Error code: 404 - page not found")
            return type(
                "_Response",
                (),
                {"output_text": "OK"},
            )()

    import openai

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)
    try:
        test_response = client.post(f"/api/settings/ai-accounts/{account_id}/test")
    finally:
        monkeypatch.undo()

    assert test_response.status_code == 200
    tested = test_response.json()["item"]
    assert tested["last_test_status"] == "success"
    assert "测试成功" in tested["last_test_message"]
    assert tested["last_tested_at"] is not None

    delete_response = client.delete(f"/api/settings/ai-accounts/{account_id}")
    assert delete_response.status_code == 200

    final_list = client.get("/api/settings/ai-accounts")
    assert final_list.status_code == 200
    assert final_list.json()["items"] == []
