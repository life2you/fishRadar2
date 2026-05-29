import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# Add repository root to the path so package imports work consistently
legacy_root = Path(__file__).resolve().parents[1]
worker_root = legacy_root.parents[1]
sys.path.insert(0, str(legacy_root))
sys.path.insert(0, str(worker_root))

from api import dependencies as deps
from api.routes import tasks
from src.domain.models.auth import AuthenticatedUser
from src.infrastructure.persistence.mysql_task_repository import MySQLTaskRepository
from src.services.task_service import TaskService
from src.services.task_generation_service import TaskGenerationService


DEFAULT_TEST_MYSQL_URL = os.getenv(
    "TEST_MYSQL_URL",
    "mysql://root:123456@127.0.0.1:3306/fishradar_pytest?charset=utf8mb4",
)


def build_test_database_url(test_name: str) -> str:
    parsed = urlparse(DEFAULT_TEST_MYSQL_URL)
    base_database = parsed.path.lstrip("/") or "fishradar_pytest"
    suffix = re.sub(r"[^a-z0-9]+", "_", test_name.lower()).strip("_") or "case"
    unique_suffix = uuid.uuid4().hex[:8]
    max_total_length = 64
    reserved = len(unique_suffix) + 2
    max_base_length = max_total_length - reserved - 16
    trimmed_base = base_database[:max(12, max_base_length)]
    max_suffix_length = max_total_length - len(trimmed_base) - reserved
    suffix = suffix[:max(8, max_suffix_length)]
    database_name = f"{trimmed_base}_{suffix}_{unique_suffix}"
    query = urlencode(dict(parse_qsl(parsed.query, keep_blank_values=True)) or {"charset": "utf8mb4"})
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{database_name}",
            "",
            query,
            "",
        )
    )


@pytest.fixture()
def mysql_test_env(monkeypatch, request):
    database_url = build_test_database_url(request.node.name)
    monkeypatch.setenv("APP_DATABASE_URL", database_url)
    return database_url


@pytest.fixture()
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture()
def load_json_fixture(fixtures_dir):
    def _load(name: str):
        return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))

    return _load


@pytest.fixture()
def sample_task_payload():
    return {
        "task_name": "Sony A7M4",
        "enabled": True,
        "keyword": "sony a7m4",
        "description": "Good condition body with accessories",
        "analyze_images": True,
        "max_pages": 2,
        "personal_only": True,
        "min_price": "8000",
        "max_price": "16000",
        "cron": "*/15 * * * *",
        "ai_prompt_base_file": "prompts/base_prompt.txt",
        "ai_prompt_criteria_file": "prompts/sony_a7m4_criteria.txt",
        "decision_mode": "ai",
        "keyword_rules": [],
    }


class FakeProcessService:
    def __init__(self):
        self.started = []
        self.stopped = []
        self.reindexed = []
        self._on_started = None
        self._on_stopped = None

    def set_lifecycle_hooks(self, *, on_started=None, on_stopped=None):
        self._on_started = on_started
        self._on_stopped = on_stopped

    async def start_task(self, task_id: int, task_name: str) -> bool:
        self.started.append((task_id, task_name))
        if self._on_started:
            await self._on_started(task_id)
        return True

    async def stop_task(self, task_id: int):
        self.stopped.append(task_id)
        if self._on_stopped:
            await self._on_stopped(task_id)

    def reindex_after_delete(self, deleted_task_id: int):
        self.reindexed.append(deleted_task_id)


class FakeSchedulerService:
    def __init__(self):
        self.reload_calls = 0
        self.next_run_times = {}

    async def reload_jobs(self, tasks):
        self.reload_calls += 1
        base = datetime(2026, 3, 19, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.next_run_times = {
            task.id: base + timedelta(minutes=(index + 1) * 15)
            for index, task in enumerate(tasks)
            if task.id is not None and task.enabled and task.cron
        }

    def get_next_run_time(self, task_id: int):
        return self.next_run_times.get(task_id)


@pytest.fixture()
def api_context(tmp_path, monkeypatch, mysql_test_env):
    repository = MySQLTaskRepository()
    task_service = TaskService(repository)
    process_service = FakeProcessService()
    scheduler_service = FakeSchedulerService()
    task_generation_service = TaskGenerationService()

    app = FastAPI()
    app.include_router(tasks.router)

    def override_get_task_service():
        return task_service

    def override_get_process_service():
        return process_service

    def override_get_scheduler_service():
        return scheduler_service

    def override_get_task_generation_service():
        return task_generation_service

    async def override_require_authenticated_user():
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

    async def mark_started(task_id: int):
        await task_service.update_task_status(task_id, True)

    async def mark_stopped(task_id: int):
        task = await task_service.get_task(task_id)
        if task:
            await task_service.update_task_status(task_id, False)

    process_service.set_lifecycle_hooks(on_started=mark_started, on_stopped=mark_stopped)

    app.dependency_overrides[deps.get_task_service] = override_get_task_service
    app.dependency_overrides[deps.get_process_service] = override_get_process_service
    app.dependency_overrides[deps.get_scheduler_service] = override_get_scheduler_service
    app.dependency_overrides[deps.get_task_generation_service] = override_get_task_generation_service
    app.dependency_overrides[deps.require_authenticated_user] = override_require_authenticated_user
    app.dependency_overrides[deps.require_workspace_user] = override_require_authenticated_user

    return {
        "app": app,
        "database_url": mysql_test_env,
        "process_service": process_service,
        "scheduler_service": scheduler_service,
        "task_generation_service": task_generation_service,
    }


@pytest.fixture()
def api_client(api_context):
    return TestClient(api_context["app"])
