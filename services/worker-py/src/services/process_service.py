"""
进程管理服务
负责管理爬虫进程的启动和停止
"""

import asyncio
import contextlib
import json
import os
import signal
import sys
from datetime import datetime
from typing import Awaitable, Callable, Dict, Literal, TextIO

from src.failure_guard import FailureGuard
from src.infrastructure.config.settings import scraper_settings
from src.infrastructure.persistence.mysql_bootstrap import bootstrap_mysql_storage
from src.infrastructure.persistence.mysql_connection import mysql_connection
from src.infrastructure.persistence.mysql_task_repository import find_task_by_id_sync
from src.services.auth_service import get_tenant_workspace_status_sync
from src.services.account_state_service import (
    materialize_runtime_account_states_sync,
    get_runtime_account_state_dir,
    get_runtime_default_state_file,
)
from src.services.notification_service import send_product_notification
from src.utils import build_task_log_path

STOP_TIMEOUT_SECONDS = 20
TENANT_WATCHDOG_INTERVAL_SECONDS = 30
SPIDER_DEBUG_LIMIT_ENV = "SPIDER_DEBUG_LIMIT"
MANUAL_RUNNING_TASKS_METADATA_KEY = "runtime:manual_running_task_ids"
MANUAL_RESTART_SNAPSHOT_METADATA_KEY = "runtime:manual_restart_task_ids"
LifecycleHook = Callable[[int], Awaitable[None] | None]


class ProcessService:
    """进程管理服务"""

    def __init__(self):
        self.processes: Dict[int, asyncio.subprocess.Process] = {}
        self.log_paths: Dict[int, str] = {}
        self.log_handles: Dict[int, TextIO] = {}
        self.task_names: Dict[int, str] = {}
        self.exit_watchers: Dict[int, asyncio.Task] = {}
        self.failure_guard = FailureGuard()
        self._on_started: LifecycleHook | None = None
        self._on_stopped: LifecycleHook | None = None
        self._tenant_watchdog_task: asyncio.Task | None = None
        self._tenant_watchdog_stop_event: asyncio.Event | None = None
        self._manual_task_ids: set[int] = self._load_manual_running_task_ids()

    def set_lifecycle_hooks(
        self,
        *,
        on_started: LifecycleHook | None = None,
        on_stopped: LifecycleHook | None = None,
    ) -> None:
        self._on_started = on_started
        self._on_stopped = on_stopped

    async def _invoke_hook(self, hook: LifecycleHook | None, task_id: int) -> None:
        if hook is None:
            return
        result = hook(task_id)
        if asyncio.iscoroutine(result):
            await result

    def _load_task_id_list_metadata(self, key: str) -> list[int]:
        bootstrap_mysql_storage()
        with mysql_connection() as conn:
            row = conn.execute(
                "SELECT value FROM app_metadata WHERE `key` = ?",
                (key,),
            ).fetchone()
        if row is None or not row.get("value"):
            return []
        try:
            parsed = json.loads(str(row["value"]))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        normalized: list[int] = []
        seen: set[int] = set()
        for item in parsed:
            try:
                task_id = int(item)
            except (TypeError, ValueError):
                continue
            if task_id < 0 or task_id in seen:
                continue
            seen.add(task_id)
            normalized.append(task_id)
        return normalized

    def _write_task_id_list_metadata(self, key: str, task_ids: list[int]) -> None:
        bootstrap_mysql_storage()
        payload = json.dumps(task_ids, ensure_ascii=False, separators=(",", ":"))
        with mysql_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_metadata(`key`, value) VALUES (?, ?)",
                (key, payload),
            )
            conn.commit()

    def _load_manual_running_task_ids(self) -> set[int]:
        return set(self._load_task_id_list_metadata(MANUAL_RUNNING_TASKS_METADATA_KEY))

    def _persist_manual_running_task_ids(self) -> None:
        self._write_task_id_list_metadata(
            MANUAL_RUNNING_TASKS_METADATA_KEY,
            sorted(self._manual_task_ids),
        )

    def snapshot_manual_tasks_for_restart(self) -> list[int]:
        snapshot = sorted(self._manual_task_ids)
        self._write_task_id_list_metadata(MANUAL_RESTART_SNAPSHOT_METADATA_KEY, snapshot)
        return snapshot

    def consume_manual_restart_task_ids(self) -> list[int]:
        snapshot = self._load_task_id_list_metadata(MANUAL_RESTART_SNAPSHOT_METADATA_KEY)
        if snapshot:
            self._write_task_id_list_metadata(MANUAL_RESTART_SNAPSHOT_METADATA_KEY, [])
            return snapshot
        return sorted(self._manual_task_ids)

    async def restore_manual_tasks(self, task_ids: list[int]) -> list[int]:
        restored: list[int] = []
        for task_id in task_ids:
            task = await asyncio.to_thread(find_task_by_id_sync, task_id)
            if task is None or not task.enabled:
                self._manual_task_ids.discard(task_id)
                continue
            started = await self.start_task(task_id, task.task_name, start_source="restore")
            if started:
                restored.append(task_id)
            else:
                self._manual_task_ids.discard(task_id)
        self._persist_manual_running_task_ids()
        return restored

    def _resolve_cookie_path(self, task_id: int) -> str | None:
        """Best-effort cookie/state path for a task."""
        try:
            task = find_task_by_id_sync(task_id)
            if task and isinstance(task.account_state_file, str) and task.account_state_file.strip():
                return task.account_state_file.strip()
        except Exception:
            pass

        state_file = scraper_settings.state_file
        return state_file if os.path.exists(state_file) else None

    def _resolve_tenant_id(self, task_id: int) -> int | None:
        try:
            task = find_task_by_id_sync(task_id)
        except Exception:
            return None
        return task.tenant_id if task else None

    async def _get_tenant_workspace_status(self, task_id: int) -> dict:
        tenant_id = self._resolve_tenant_id(task_id)
        if tenant_id is None:
            return {
                "tenant_id": None,
                "exists": True,
                "status": "active",
                "access_expired": False,
                "workspace_enabled": True,
                "access_expires_at": None,
            }
        status = await asyncio.to_thread(get_tenant_workspace_status_sync, tenant_id)
        status["tenant_id"] = tenant_id
        return status

    def _build_workspace_denied_reason(self, workspace_status: dict) -> str:
        if not workspace_status.get("exists", True):
            return "租户不存在"
        if workspace_status.get("status") != "active":
            return "租户已被停用"
        if workspace_status.get("access_expired"):
            return "租户卡密已到期"
        return "租户工作台尚未开通"

    async def _notify_workspace_stopped(
        self,
        task_id: int,
        task_name: str,
        workspace_status: dict,
    ) -> None:
        tenant_id = workspace_status.get("tenant_id")
        if tenant_id is None:
            return
        reason = self._build_workspace_denied_reason(workspace_status)
        try:
            await send_product_notification(
                {
                    "商品标题": f"[任务停止] {task_name}",
                    "当前售价": "N/A",
                    "商品链接": "#",
                },
                "租户工作台当前不可用，系统已自动停止该任务。\n"
                f"原因: {reason}\n"
                "如需恢复，请先续期或重新开通后再启动任务。",
                tenant_id,
            )
        except Exception as exc:
            print(f"发送租户任务停止通知失败: {exc}")

    async def _enforce_tenant_workspace_once(self) -> None:
        running_task_ids = list(self.processes.keys())
        for task_id in running_task_ids:
            await self._drain_finished_process(task_id)
            if not self.is_running(task_id):
                continue
            workspace_status = await self._get_tenant_workspace_status(task_id)
            if workspace_status.get("workspace_enabled", True):
                continue
            task_name = self.task_names.get(task_id, f"任务 {task_id}")
            print(
                f"任务 '{task_name}' (ID: {task_id}) 所属租户工作台不可用，准备自动停止。"
            )
            await self._notify_workspace_stopped(task_id, task_name, workspace_status)
            await self.stop_task(task_id)

    async def _tenant_workspace_watchdog_loop(self) -> None:
        assert self._tenant_watchdog_stop_event is not None
        while True:
            try:
                await asyncio.wait_for(
                    self._tenant_watchdog_stop_event.wait(),
                    timeout=TENANT_WATCHDOG_INTERVAL_SECONDS,
                )
                return
            except asyncio.TimeoutError:
                pass
            try:
                await self._enforce_tenant_workspace_once()
            except Exception as exc:
                print(f"租户任务巡检失败: {exc}")

    def start_background_tasks(self) -> None:
        if self._tenant_watchdog_task is not None and not self._tenant_watchdog_task.done():
            return
        self._tenant_watchdog_stop_event = asyncio.Event()
        self._tenant_watchdog_task = asyncio.create_task(self._tenant_workspace_watchdog_loop())

    async def stop_background_tasks(self) -> None:
        if self._tenant_watchdog_stop_event is not None:
            self._tenant_watchdog_stop_event.set()
        if self._tenant_watchdog_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(self._tenant_watchdog_task)
        self._tenant_watchdog_task = None
        self._tenant_watchdog_stop_event = None

    async def stop_tasks_for_tenant(self, tenant_id: int) -> list[int]:
        stopped_task_ids: list[int] = []
        for task_id in list(self.processes.keys()):
            if self._resolve_tenant_id(task_id) != tenant_id:
                continue
            await self._drain_finished_process(task_id)
            if not self.is_running(task_id):
                continue
            await self.stop_task(task_id)
            stopped_task_ids.append(task_id)
        return stopped_task_ids

    def is_running(self, task_id: int) -> bool:
        """检查任务是否正在运行"""
        process = self.processes.get(task_id)
        return process is not None and process.returncode is None

    async def _drain_finished_process(self, task_id: int) -> None:
        process = self.processes.get(task_id)
        if process is None or process.returncode is None:
            return

        watcher = self.exit_watchers.get(task_id)
        if watcher is not None:
            await asyncio.shield(watcher)
            return

        self._cleanup_runtime(task_id, process)
        await self._invoke_hook(self._on_stopped, task_id)

    def _open_log_file(self, task_id: int, task_name: str) -> tuple[str, TextIO]:
        os.makedirs("logs", exist_ok=True)
        log_file_path = build_task_log_path(task_id, task_name)
        log_file_handle = open(log_file_path, "a", encoding="utf-8")
        return log_file_path, log_file_handle

    def _build_spawn_command(self, task_id: int, task_name: str) -> list[str]:
        command = [
            sys.executable,
            "-u",
            "spider_v2.py",
            "--task-id",
            str(task_id),
        ]
        debug_limit = str(os.getenv(SPIDER_DEBUG_LIMIT_ENV, "")).strip()
        if debug_limit.isdigit() and int(debug_limit) > 0:
            command.extend(["--debug-limit", debug_limit])
        return command

    async def _spawn_process(
        self,
        task_id: int,
        task_name: str,
        log_file_handle: TextIO,
    ) -> asyncio.subprocess.Process:
        preexec_fn = os.setsid if sys.platform != "win32" else None
        runtime_state = materialize_runtime_account_states_sync(
            runtime_state_dir=get_runtime_account_state_dir(),
            runtime_default_state_file=get_runtime_default_state_file(),
        )
        child_env = os.environ.copy()
        child_env["PYTHONIOENCODING"] = "utf-8"
        child_env["PYTHONUTF8"] = "1"
        child_env["ACCOUNT_STATE_DIR"] = runtime_state["runtime_state_dir"]
        child_env["STATE_FILE"] = runtime_state["runtime_default_state_file"]
        return await asyncio.create_subprocess_exec(
            *self._build_spawn_command(task_id, task_name),
            stdout=log_file_handle,
            stderr=log_file_handle,
            preexec_fn=preexec_fn,
            env=child_env,
        )

    def _register_runtime(
        self,
        task_id: int,
        task_name: str,
        process: asyncio.subprocess.Process,
        log_file_path: str,
        log_file_handle: TextIO,
        *,
        start_source: Literal["manual", "scheduled", "restore"],
    ) -> None:
        self.processes[task_id] = process
        self.log_paths[task_id] = log_file_path
        self.log_handles[task_id] = log_file_handle
        self.task_names[task_id] = task_name
        self.exit_watchers[task_id] = asyncio.create_task(self._watch_process_exit(process))
        if start_source in {"manual", "restore"}:
            self._manual_task_ids.add(task_id)
            self._persist_manual_running_task_ids()

    async def start_task(
        self,
        task_id: int,
        task_name: str,
        *,
        start_source: Literal["manual", "scheduled", "restore"] = "manual",
    ) -> bool:
        """启动任务进程"""
        await self._drain_finished_process(task_id)
        if self.is_running(task_id):
            print(f"任务 '{task_name}' (ID: {task_id}) 已在运行中")
            return False

        workspace_status = await self._get_tenant_workspace_status(task_id)
        if not workspace_status.get("workspace_enabled", True):
            reason = self._build_workspace_denied_reason(workspace_status)
            print(f"任务 '{task_name}' (ID: {task_id}) 启动被拒绝: {reason}")
            return False

        decision = self.failure_guard.should_skip_start(
            task_name,
            cookie_path=self._resolve_cookie_path(task_id),
        )
        if decision.skip:
            await self._notify_skip(task_id, task_name, decision)
            return False

        log_file_path = ""
        log_file_handle = None
        try:
            log_file_path, log_file_handle = self._open_log_file(task_id, task_name)
            process = await self._spawn_process(task_id, task_name, log_file_handle)
        except Exception as exc:
            self._close_log_handle(log_file_handle)
            print(f"启动任务 '{task_name}' 失败: {exc}")
            return False

        self._register_runtime(
            task_id,
            task_name,
            process,
            log_file_path,
            log_file_handle,
            start_source=start_source,
        )
        print(f"启动任务 '{task_name}' (PID: {process.pid})")
        await self._invoke_hook(self._on_started, task_id)
        return True

    async def _notify_skip(self, task_id: int, task_name: str, decision) -> None:
        print(
            f"[FailureGuard] 跳过启动任务 '{task_name}'，已暂停重试 "
            f"(连续失败 {decision.consecutive_failures}/{self.failure_guard.threshold})"
        )
        if not decision.should_notify:
            return
        tenant_id = self._resolve_tenant_id(task_id)
        try:
            await send_product_notification(
                {
                    "商品标题": f"[任务暂停] {task_name}",
                    "当前售价": "N/A",
                    "商品链接": "#",
                },
                "任务处于暂停状态，将跳过执行。\n"
                f"原因: {decision.reason}\n"
                f"连续失败: {decision.consecutive_failures}/{self.failure_guard.threshold}\n"
                f"暂停到: {decision.paused_until.strftime('%Y-%m-%d %H:%M:%S') if decision.paused_until else 'N/A'}\n"
                "修复方法: 更新登录态/cookies文件后会自动恢复。",
                tenant_id,
            )
        except Exception as exc:
            print(f"发送任务暂停通知失败: {exc}")

    async def _watch_process_exit(self, process: asyncio.subprocess.Process) -> None:
        await process.wait()
        task_id = self._find_task_id_by_process(process)
        if task_id is None:
            return
        self._cleanup_runtime(task_id, process)
        await self._invoke_hook(self._on_stopped, task_id)

    def _find_task_id_by_process(self, process: asyncio.subprocess.Process) -> int | None:
        for task_id, current_process in self.processes.items():
            if current_process is process:
                return task_id
        return None

    def _cleanup_runtime(
        self,
        task_id: int,
        process: asyncio.subprocess.Process,
    ) -> None:
        if self.processes.get(task_id) is not process:
            return
        self.processes.pop(task_id, None)
        self.log_paths.pop(task_id, None)
        self.task_names.pop(task_id, None)
        self._close_log_handle(self.log_handles.pop(task_id, None))
        self.exit_watchers.pop(task_id, None)
        if task_id in self._manual_task_ids:
            self._manual_task_ids.discard(task_id)
            self._persist_manual_running_task_ids()

    def _close_log_handle(self, log_handle: TextIO | None) -> None:
        if log_handle is None:
            return
        with contextlib.suppress(Exception):
            log_handle.close()

    def _append_stop_marker(self, log_path: str | None) -> None:
        if not log_path:
            return
        try:
            timestamp = datetime.now().strftime(" %Y-%m-%d %H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"[{timestamp}] !!! 任务已被终止 !!!\n")
        except Exception as exc:
            print(f"写入任务终止标记失败: {exc}")

    async def stop_task(self, task_id: int) -> bool:
        """停止任务进程"""
        await self._drain_finished_process(task_id)
        process = self.processes.get(task_id)
        if process is None:
            print(f"任务 ID {task_id} 没有正在运行的进程")
            return False
        if process.returncode is not None:
            await self._await_exit_watcher(task_id)
            print(f"任务进程 {process.pid} (ID: {task_id}) 已退出，略过停止")
            return False

        try:
            await self._terminate_process(process, task_id)
            self._append_stop_marker(self.log_paths.get(task_id))
            await self._await_exit_watcher(task_id)
            print(f"任务进程 {process.pid} (ID: {task_id}) 已终止")
            return True
        except ProcessLookupError:
            print(f"进程 (ID: {task_id}) 已不存在")
            return False
        except Exception as exc:
            print(f"停止任务进程 (ID: {task_id}) 时出错: {exc}")
            return False

    async def _terminate_process(
        self,
        process: asyncio.subprocess.Process,
        task_id: int,
    ) -> None:
        if sys.platform != "win32":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()

        try:
            await asyncio.wait_for(process.wait(), timeout=STOP_TIMEOUT_SECONDS)
            return
        except asyncio.TimeoutError:
            print(
                f"任务进程 {process.pid} (ID: {task_id}) 未在 "
                f"{STOP_TIMEOUT_SECONDS} 秒内退出，准备强制终止..."
            )

        if sys.platform != "win32":
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            process.kill()
        await process.wait()

    async def _await_exit_watcher(self, task_id: int) -> None:
        watcher = self.exit_watchers.get(task_id)
        if watcher is None:
            return
        await asyncio.shield(watcher)

    def reindex_after_delete(self, deleted_task_id: int) -> None:
        """删除任务后同步重排运行时索引，避免任务下标漂移。"""
        self.processes = self._reindex_mapping(self.processes, deleted_task_id)
        self.log_paths = self._reindex_mapping(self.log_paths, deleted_task_id)
        self.log_handles = self._reindex_mapping(self.log_handles, deleted_task_id)
        self.task_names = self._reindex_mapping(self.task_names, deleted_task_id)
        self.exit_watchers = self._reindex_mapping(self.exit_watchers, deleted_task_id)

    def _reindex_mapping(self, mapping: Dict[int, object], deleted_task_id: int) -> Dict[int, object]:
        reindexed: Dict[int, object] = {}
        for task_id, value in mapping.items():
            if task_id == deleted_task_id:
                continue
            next_task_id = task_id - 1 if task_id > deleted_task_id else task_id
            reindexed[next_task_id] = value
        return reindexed

    async def stop_all(self) -> None:
        """停止所有任务进程"""
        task_ids = list(self.processes.keys())
        for task_id in task_ids:
            await self.stop_task(task_id)
