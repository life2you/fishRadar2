from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import dependencies as deps
from api.routes import announcements
from src.domain.models.auth import AuthenticatedUser
from src.infrastructure.persistence.mysql_bootstrap import bootstrap_mysql_storage


def _build_admin_client(tmp_path, monkeypatch, mysql_test_env) -> TestClient:
    monkeypatch.chdir(tmp_path)
    bootstrap_mysql_storage(
        legacy_result_dir=str(tmp_path / "jsonl"),
        legacy_price_history_dir=str(tmp_path / "price_history"),
    )

    app = FastAPI()
    app.include_router(announcements.router)

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
    app.dependency_overrides[deps.require_workspace_user] = _admin_user
    return TestClient(app)


def _build_tenant_client(tmp_path, monkeypatch, mysql_test_env) -> TestClient:
    monkeypatch.chdir(tmp_path)
    bootstrap_mysql_storage(
        legacy_result_dir=str(tmp_path / "jsonl"),
        legacy_price_history_dir=str(tmp_path / "price_history"),
    )

    app = FastAPI()
    app.include_router(announcements.router)

    async def _tenant_user():
        return AuthenticatedUser(
            user_id=22,
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

    app.dependency_overrides[deps.require_workspace_user] = _tenant_user
    return TestClient(app)


def test_admin_can_create_and_list_announcements(tmp_path, monkeypatch, mysql_test_env):
    client = _build_admin_client(tmp_path, monkeypatch, mysql_test_env)

    create_response = client.post(
        "/api/announcements",
        json={
            "title": "系统升级通知",
            "content": "今晚 23:00 进行升级，期间任务可能延迟。",
            "level": "warning",
            "status": "active",
            "dismissible": True,
        },
    )
    assert create_response.status_code == 200
    item = create_response.json()["item"]
    assert item["title"] == "系统升级通知"
    assert item["status"] == "active"

    list_response = client.get("/api/announcements")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["title"] == "系统升级通知"


def test_tenant_only_receives_active_announcements(tmp_path, monkeypatch, mysql_test_env):
    admin_client = _build_admin_client(tmp_path, monkeypatch, mysql_test_env)
    tenant_client = _build_tenant_client(tmp_path, monkeypatch, mysql_test_env)

    admin_client.post(
        "/api/announcements",
        json={
            "title": "生效公告",
            "content": "这条公告应该展示给租户。",
            "level": "info",
            "status": "active",
            "dismissible": True,
        },
    )
    admin_client.post(
        "/api/announcements",
        json={
            "title": "草稿公告",
            "content": "这条公告不应该展示给租户。",
            "level": "info",
            "status": "draft",
            "dismissible": True,
        },
    )

    response = tenant_client.get("/api/announcements/active")
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["title"] for item in items] == ["生效公告"]


def test_admin_can_publish_announcement_and_notify_tenants(tmp_path, monkeypatch, mysql_test_env):
    client = _build_admin_client(tmp_path, monkeypatch, mysql_test_env)

    async def _fake_notify_announcement_to_tenants(**kwargs):
        return {"22": {"ntfy": {"success": True, "message": "发送成功"}}}

    monkeypatch.setattr(
        "src.api.routes.announcements.notify_announcement_to_tenants",
        _fake_notify_announcement_to_tenants,
    )

    response = client.post(
        "/api/announcements",
        json={
            "title": "升级完成通知",
            "content": "系统升级已经完成，可以正常继续使用。",
            "level": "success",
            "status": "active",
            "dismissible": True,
            "notify_tenants": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["item"]["title"] == "升级完成通知"
    assert payload["notification_result"] == {"22": {"ntfy": {"success": True, "message": "发送成功"}}}
