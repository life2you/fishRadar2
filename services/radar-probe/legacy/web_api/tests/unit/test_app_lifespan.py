import os
import asyncio

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


class _FakeTaskService:
    def __init__(self, _repo):
        self.updated = []

    async def get_all_tasks(self):
        return []

    async def update_task_status(self, task_id, is_running):
        self.updated.append((task_id, is_running))


class _FakeSchedulerService:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.reload_payload = None

    async def reload_jobs(self, tasks):
        self.reload_payload = list(tasks)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class _FakeProcessService:
    def __init__(self):
        self.stop_all_called = False
        self.background_started = False
        self.background_stopped = False
        self.snapshot_called = False
        self.restore_payload = None

    def consume_manual_restart_task_ids(self):
        return [2, 5]

    async def restore_manual_tasks(self, task_ids):
        self.restore_payload = list(task_ids)
        return list(task_ids)

    def start_background_tasks(self):
        self.background_started = True

    async def stop_background_tasks(self):
        self.background_stopped = True

    def snapshot_manual_tasks_for_restart(self):
        self.snapshot_called = True
        return [2, 5]

    async def stop_all(self):
        self.stop_all_called = True


def test_lifespan_cleans_task_logs_on_startup(monkeypatch):
    called = {}
    fake_scheduler = _FakeSchedulerService()
    fake_process = _FakeProcessService()

    monkeypatch.setattr(app_module, "scheduler_service", fake_scheduler)
    monkeypatch.setattr(app_module, "process_service", fake_process)
    monkeypatch.setattr(app_module, "TaskService", _FakeTaskService)
    monkeypatch.setattr(app_module, "MySQLTaskRepository", lambda: object())
    monkeypatch.setattr(app_module, "bootstrap_mysql_storage", lambda: called.setdefault("bootstrapped", True))
    monkeypatch.setattr(
        app_module,
        "cleanup_task_logs",
        lambda *args, **kwargs: called.setdefault("keep_days", kwargs.get("keep_days")),
    )
    monkeypatch.setattr(app_module.app_settings, "task_log_retention_days", 9)

    async def _run():
        async with app_module.lifespan(None):
            assert fake_scheduler.started is True
            assert fake_scheduler.reload_payload == []

    asyncio.run(_run())

    assert called["bootstrapped"] is True
    assert called["keep_days"] == 9
    assert fake_process.restore_payload == [2, 5]
    assert fake_process.background_started is True
    assert fake_process.background_stopped is True
    assert fake_process.snapshot_called is True
    assert fake_scheduler.stopped is True
    assert fake_process.stop_all_called is True
