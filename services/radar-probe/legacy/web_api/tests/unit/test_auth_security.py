import os
from datetime import timedelta

import pytest
from fastapi import Response

import sys
from pathlib import Path

os.environ.setdefault(
    "APP_DATABASE_URL",
    "mysql://root:123456@host.docker.internal:3306/fishradar_feature_time_test?charset=utf8mb4",
)

LEGACY_ROOT = Path(__file__).resolve().parents[2]
WORKER_ROOT = LEGACY_ROOT.parents[1]
for candidate in (LEGACY_ROOT, WORKER_ROOT):
    text_path = str(candidate)
    if text_path not in sys.path:
        sys.path.insert(0, text_path)

import app as app_module
from src.services import auth_service
from src.services.login_rate_limiter import LoginRateLimiter


def test_validate_admin_bootstrap_safety_rejects_default_admin_on_empty_prod(monkeypatch):
    monkeypatch.setattr(auth_service.app_settings, "app_env", "production", raising=False)
    monkeypatch.setattr(auth_service.app_settings, "web_username", "admin", raising=False)
    monkeypatch.setattr(auth_service.app_settings, "web_password", "admin123", raising=False)
    monkeypatch.setattr(auth_service, "count_users_sync", lambda: 0)

    with pytest.raises(RuntimeError, match="默认管理员初始账号"):
        auth_service.validate_admin_bootstrap_safety_sync()


def test_validate_admin_bootstrap_safety_allows_existing_users_in_prod(monkeypatch):
    monkeypatch.setattr(auth_service.app_settings, "app_env", "production", raising=False)
    monkeypatch.setattr(auth_service.app_settings, "web_username", "admin", raising=False)
    monkeypatch.setattr(auth_service.app_settings, "web_password", "admin123", raising=False)
    monkeypatch.setattr(auth_service, "count_users_sync", lambda: 2)

    auth_service.validate_admin_bootstrap_safety_sync()


def test_set_auth_cookie_uses_secure_flag_in_production(monkeypatch):
    monkeypatch.setattr(app_module.app_settings, "app_env", "production", raising=False)
    monkeypatch.setattr(app_module.app_settings, "auth_cookie_secure", False, raising=False)

    response = Response()
    app_module._set_auth_cookie(response, "session-token")

    assert "Secure" in response.headers["set-cookie"]


def test_login_rate_limiter_blocks_after_threshold():
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=300, block_seconds=900)

    assert limiter.record_failure("1.1.1.1").blocked is False
    assert limiter.record_failure("1.1.1.1").blocked is False
    decision = limiter.record_failure("1.1.1.1")

    assert decision.blocked is True
    assert decision.retry_after_seconds > 0


def test_login_rate_limiter_clears_after_success():
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=300, block_seconds=900)

    limiter.record_failure("1.1.1.1")
    limiter.record_success("1.1.1.1")

    assert limiter.evaluate("1.1.1.1").blocked is False


def test_login_rate_limiter_unblocks_after_expiry(monkeypatch):
    limiter = LoginRateLimiter(max_attempts=1, window_seconds=300, block_seconds=60)
    first_now = limiter._now()
    later = first_now + timedelta(seconds=61)

    monkeypatch.setattr(limiter, "_now", lambda: first_now)
    assert limiter.record_failure("1.1.1.1").blocked is True

    monkeypatch.setattr(limiter, "_now", lambda: later)
    assert limiter.evaluate("1.1.1.1").blocked is False
