from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import dependencies as deps
from api.routes import tenant_settings
from src.domain.models.auth import AuthenticatedUser
from src.infrastructure.persistence.mysql_bootstrap import bootstrap_mysql_storage


def _build_tenant_settings_client(tmp_path, monkeypatch, mysql_test_env) -> TestClient:
    monkeypatch.chdir(tmp_path)
    bootstrap_mysql_storage(
        legacy_result_dir=str(tmp_path / "jsonl"),
        legacy_price_history_dir=str(tmp_path / "price_history"),
    )

    app = FastAPI()
    app.include_router(tenant_settings.router)

    async def override_require_workspace_user():
        return AuthenticatedUser(
            user_id=2,
            username="tenant_demo",
            role="tenant",
            tenant_id=22,
            tenant_name="Demo Tenant",
            tenant_status="active",
            tenant_ai_enabled=True,
            tenant_activation_required=True,
            tenant_activated_at="2026-01-01T00:00:00",
            tenant_access_expires_at="2099-01-01T00:00:00",
        )

    app.dependency_overrides[deps.require_workspace_user] = override_require_workspace_user
    return TestClient(app)


def test_tenant_notification_settings_round_trip_and_channel_test(
    tmp_path, monkeypatch, mysql_test_env
):
    monkeypatch.setenv("NTFY_TOPIC_URL", "https://ntfy.sh/platform-admin")
    monkeypatch.delenv("WX_BOT_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_BASE_URL", raising=False)
    client = _build_tenant_settings_client(tmp_path, monkeypatch, mysql_test_env)

    update_response = client.put(
        "/api/tenant-settings/notifications",
        json={
            "NTFY_TOPIC_URL": "https://ntfy.sh/catchyu-demo",
            "PCURL_TO_MOBILE": True,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["configured_channels"] == ["ntfy"]

    fetch_response = client.get("/api/tenant-settings/notifications")
    assert fetch_response.status_code == 200
    payload = fetch_response.json()
    assert payload["NTFY_TOPIC_URL"] == "https://ntfy.sh/catchyu-demo"
    assert payload["CONFIGURED_CHANNELS"] == ["ntfy"]
    assert payload["AVAILABLE_CHANNELS"] == ["ntfy"]

    captured = []

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    def _fake_post(url, data=None, headers=None, timeout=None, **kwargs):
        captured.append(
            {
                "url": url,
                "data": data,
                "headers": headers,
            }
        )
        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)

    test_response = client.post(
        "/api/tenant-settings/notifications/test",
        json={
            "channel": "ntfy",
            "settings": {},
        },
    )
    assert test_response.status_code == 200
    result_payload = test_response.json()
    assert result_payload["results"]["ntfy"]["success"] is True
    assert captured[0]["url"] == "https://ntfy.sh/catchyu-demo"


def test_tenant_notification_settings_reject_disallowed_channel(
    tmp_path, monkeypatch, mysql_test_env
):
    monkeypatch.setenv("WX_BOT_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=platform")
    monkeypatch.delenv("NTFY_TOPIC_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_BASE_URL", raising=False)
    client = _build_tenant_settings_client(tmp_path, monkeypatch, mysql_test_env)

    fetch_response = client.get("/api/tenant-settings/notifications")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["AVAILABLE_CHANNELS"] == ["wecom"]

    update_response = client.put(
        "/api/tenant-settings/notifications",
        json={"NTFY_TOPIC_URL": "https://ntfy.sh/not-allowed"},
    )
    assert update_response.status_code == 422
    assert "未向租户开放" in update_response.text
