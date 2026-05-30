import asyncio
import sys
from types import SimpleNamespace

from src.services.process_service import ProcessService


def _build_service(monkeypatch) -> ProcessService:
    monkeypatch.setattr(
        "src.services.process_service.FailureGuard",
        lambda: SimpleNamespace(
            threshold=3,
            should_skip_start=lambda *args, **kwargs: SimpleNamespace(
                skip=False,
                should_notify=False,
                reason="",
                consecutive_failures=0,
                paused_until=None,
            ),
        ),
    )
    return ProcessService()


class FakeProcess:
    def __init__(self, pid: int):
        self.pid = pid
        self.returncode = None
        self._done = asyncio.Event()

    async def wait(self):
        await self._done.wait()
        return self.returncode

    def finish(self, returncode: int = 0):
        self.returncode = returncode
        self._done.set()

    def terminate(self):
        self.finish(-15)

    def kill(self):
        self.finish(-9)


def test_process_service_marks_task_stopped_when_process_exits(monkeypatch, tmp_path):
    fake_process = FakeProcess(pid=4321)
    events = []

    async def run_scenario():
        service = _build_service(monkeypatch)

        stopped = asyncio.Event()

        async def on_started(task_id: int):
            events.append(("started", task_id))

        async def on_stopped(task_id: int):
            events.append(("stopped", task_id))
            stopped.set()

        service.set_lifecycle_hooks(on_started=on_started, on_stopped=on_stopped)

        async def fake_create_subprocess_exec(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(
            "src.services.process_service.build_task_log_path",
            lambda task_id, _task_name: str(tmp_path / f"task-{task_id}.log"),
        )
        monkeypatch.setattr(
            "src.services.process_service.materialize_runtime_account_states_sync",
            lambda **_kwargs: {
                "runtime_state_dir": str(tmp_path / "runtime_state"),
                "runtime_default_state_file": str(tmp_path / "xianyu_state.json"),
            },
        )
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        started = await service.start_task(0, "task-a")
        assert started is True
        assert events == [("started", 0)]
        assert service.is_running(0) is True

        fake_process.finish(0)
        await asyncio.wait_for(stopped.wait(), timeout=1)

        assert ("stopped", 0) in events
        assert service.is_running(0) is False

    asyncio.run(run_scenario())


def test_process_service_reindexes_runtime_maps_after_delete(monkeypatch):
    service = _build_service(monkeypatch)
    proc_a = object()
    proc_c = object()
    watcher_a = object()
    watcher_c = object()

    service.processes = {0: proc_a, 2: proc_c}
    service.log_paths = {0: "a.log", 2: "c.log"}
    service.task_names = {0: "A", 2: "C"}
    service.exit_watchers = {0: watcher_a, 2: watcher_c}

    service.reindex_after_delete(1)

    assert service.processes == {0: proc_a, 1: proc_c}
    assert service.log_paths == {0: "a.log", 1: "c.log"}
    assert service.task_names == {0: "A", 1: "C"}
    assert service.exit_watchers == {0: watcher_a, 1: watcher_c}


def test_process_service_adds_debug_limit_arg_when_env_enabled(monkeypatch):
    monkeypatch.setenv("SPIDER_DEBUG_LIMIT", "1")
    service = _build_service(monkeypatch)

    command = service._build_spawn_command(7, "task-a")

    assert command == [
        sys.executable,
        "-u",
        "spider_v2.py",
        "--task-id",
        "7",
        "--debug-limit",
        "1",
    ]


def test_process_service_denies_start_when_tenant_workspace_disabled(monkeypatch):
    async def run_scenario():
        service = _build_service(monkeypatch)

        monkeypatch.setattr(
            "src.services.process_service.get_tenant_workspace_status_sync",
            lambda tenant_id: {
                "exists": True,
                "status": "active",
                "access_expired": True,
                "workspace_enabled": False,
                "access_expires_at": "2026-01-01T00:00:00",
            },
        )
        monkeypatch.setattr(service, "_resolve_tenant_id", lambda _task_id: 4)

        create_called = False

        async def fake_create_subprocess_exec(*_args, **_kwargs):
            nonlocal create_called
            create_called = True
            return FakeProcess(pid=9999)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        started = await service.start_task(0, "tenant-task")
        assert started is False
        assert create_called is False

    asyncio.run(run_scenario())


def test_process_service_stops_running_task_when_tenant_workspace_expires(monkeypatch, tmp_path):
    fake_process = FakeProcess(pid=5678)

    async def run_scenario():
        service = _build_service(monkeypatch)

        monkeypatch.setattr(
            "src.services.process_service.build_task_log_path",
            lambda task_id, _task_name: str(tmp_path / f"task-{task_id}.log"),
        )
        monkeypatch.setattr(
            "src.services.process_service.materialize_runtime_account_states_sync",
            lambda **_kwargs: {
                "runtime_state_dir": str(tmp_path / "runtime_state"),
                "runtime_default_state_file": str(tmp_path / "xianyu_state.json"),
            },
        )
        monkeypatch.setattr(service, "_resolve_tenant_id", lambda _task_id: 4)

        status_holder = {
            "exists": True,
            "status": "active",
            "access_expired": False,
            "workspace_enabled": True,
            "access_expires_at": None,
        }

        monkeypatch.setattr(
            "src.services.process_service.get_tenant_workspace_status_sync",
            lambda tenant_id: dict(status_holder),
        )

        async def fake_create_subprocess_exec(*_args, **_kwargs):
            return fake_process

        notifications = []

        async def fake_send_product_notification(_payload, message, tenant_id):
            notifications.append((tenant_id, message))

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
        monkeypatch.setattr(
            "src.services.process_service.send_product_notification",
            fake_send_product_notification,
        )
        async def fake_terminate_process(process, _task_id):
            process.terminate()
            await process.wait()

        monkeypatch.setattr(service, "_terminate_process", fake_terminate_process)

        started = await service.start_task(0, "tenant-task")
        assert started is True
        assert service.is_running(0) is True

        status_holder.update(
            {
                "access_expired": True,
                "workspace_enabled": False,
                "access_expires_at": "2026-01-01T00:00:00",
            }
        )
        await service._enforce_tenant_workspace_once()

        assert service.is_running(0) is False
        assert notifications
        assert notifications[0][0] == 4
        assert "租户卡密已到期" in notifications[0][1]

    asyncio.run(run_scenario())


def test_process_service_tracks_manual_tasks_for_restart(monkeypatch, tmp_path):
    fake_process = FakeProcess(pid=2468)
    metadata_store: dict[str, list[int]] = {}

    async def run_scenario():
        service = _build_service(monkeypatch)

        monkeypatch.setattr(
            service,
            "_load_manual_running_task_ids",
            lambda: set(),
        )
        service._manual_task_ids = set()
        monkeypatch.setattr(
            service,
            "_write_task_id_list_metadata",
            lambda key, task_ids: metadata_store.__setitem__(key, list(task_ids)),
        )
        monkeypatch.setattr(
            "src.services.process_service.build_task_log_path",
            lambda task_id, _task_name: str(tmp_path / f"task-{task_id}.log"),
        )
        monkeypatch.setattr(
            "src.services.process_service.materialize_runtime_account_states_sync",
            lambda **_kwargs: {
                "runtime_state_dir": str(tmp_path / "runtime_state"),
                "runtime_default_state_file": str(tmp_path / "xianyu_state.json"),
            },
        )

        async def fake_create_subprocess_exec(*_args, **_kwargs):
            return fake_process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        started = await service.start_task(7, "manual-task", start_source="manual")
        assert started is True
        assert metadata_store["runtime:manual_running_task_ids"] == [7]

        service.snapshot_manual_tasks_for_restart()
        assert metadata_store["runtime:manual_restart_task_ids"] == [7]

        fake_process.finish(0)
        await asyncio.wait_for(service.exit_watchers[7], timeout=1)

        assert metadata_store["runtime:manual_running_task_ids"] == []

    asyncio.run(run_scenario())


def test_process_service_restore_manual_tasks_only_restores_enabled(monkeypatch):
    async def run_scenario():
        service = _build_service(monkeypatch)
        service._manual_task_ids = set()

        task_lookup = {
            3: SimpleNamespace(id=3, task_name="task-3", enabled=True),
            4: SimpleNamespace(id=4, task_name="task-4", enabled=False),
        }
        monkeypatch.setattr(
            "src.services.process_service.find_task_by_id_sync",
            lambda task_id: task_lookup.get(task_id),
        )

        started_calls = []

        async def fake_start_task(task_id, task_name, *, start_source="manual"):
            started_calls.append((task_id, task_name, start_source))
            return True

        monkeypatch.setattr(service, "start_task", fake_start_task)
        persisted = []
        monkeypatch.setattr(service, "_persist_manual_running_task_ids", lambda: persisted.append(sorted(service._manual_task_ids)))

        restored = await service.restore_manual_tasks([3, 4, 9])

        assert restored == [3]
        assert started_calls == [(3, "task-3", "restore")]
        assert persisted[-1] == []

    asyncio.run(run_scenario())
