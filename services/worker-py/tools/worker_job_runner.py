from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import contextlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infrastructure.persistence.mysql_bootstrap import bootstrap_mysql_storage
from src.infrastructure.persistence.mysql_connection import mysql_connection
from src.infrastructure.persistence.mysql_task_repository import find_task_by_id_sync
from src.services.account_state_service import (
    get_runtime_account_state_dir,
    get_runtime_default_state_file,
    materialize_runtime_account_states_sync,
)

try:
    import redis
except ImportError:  # pragma: no cover - optional in local dev until dependencies are installed
    redis = None


JOB_STATUS_PENDING = "pending"
JOB_STATUS_CLAIMED = "claimed"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"


def now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def poll_seconds() -> float:
    raw = os.environ.get("WORKER_JOB_POLL_SECONDS", "2").strip()
    try:
        value = float(raw)
    except ValueError:
        return 2.0
    return max(0.5, value)


def worker_id() -> str:
    configured = os.environ.get("WORKER_ID", "").strip()
    if configured:
        return configured
    return f"{socket.gethostname()}-worker"


def queue_backend() -> str:
    return os.environ.get("QUEUE_BACKEND", "mysql").strip().lower() or "mysql"


def redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0").strip()


def redis_queue_name() -> str:
    return os.environ.get("REDIS_QUEUE_NAME", "fishradar2:worker_jobs").strip() or "fishradar2:worker_jobs"


def redis_event_channel() -> str:
    return os.environ.get("REDIS_EVENT_CHANNEL", "fishradar2:events").strip() or "fishradar2:events"


@dataclass
class RunningTask:
    task_id: int
    tenant_id: int | None
    process: subprocess.Popen


@lru_cache(maxsize=1)
def get_redis_client():
    if redis is None or queue_backend() != "redis":
        return None
    return redis.Redis.from_url(redis_url(), decode_responses=True)


@lru_cache(maxsize=1)
def get_event_redis_client():
    if redis is None:
        return None
    url = redis_url()
    if not url:
        return None
    return redis.Redis.from_url(url, decode_responses=True)


def publish_event_sync(event_type: str, data: dict, tenant_scope: int | None = None) -> None:
    client = get_event_redis_client()
    if client is None:
        return
    payload = {
        "type": event_type,
        "data": data,
        "tenant_scope": tenant_scope,
    }
    with contextlib.suppress(Exception):
        client.publish(redis_event_channel(), json.dumps(payload, ensure_ascii=False))


def publish_task_events(task_id: int, is_running: bool, tenant_scope: int | None) -> None:
    publish_event_sync(
        "task_status_changed",
        {
            "id": task_id,
            "is_running": is_running,
            "tenant_id": tenant_scope,
        },
        tenant_scope,
    )
    publish_event_sync(
        "tasks_updated",
        {
            "task_id": task_id,
            "is_running": is_running,
            "tenant_id": tenant_scope,
        },
        tenant_scope,
    )


def publish_results_updated(data: dict, tenant_scope: int | None) -> None:
    publish_event_sync("results_updated", data, tenant_scope)


def claim_next_job_sync(worker_name: str) -> dict | None:
    with mysql_connection() as conn:
        row = conn.execute(
            """
            SELECT id, job_key, job_type, task_id, task_name, payload_json, steps_json
            FROM worker_jobs
            WHERE status = %s
            ORDER BY id ASC
            LIMIT 1
            """,
            (JOB_STATUS_PENDING,),
        ).fetchone()
        if not row:
            return None
        claimed_at = now_iso()
        result = conn.execute(
            """
            UPDATE worker_jobs
            SET status = %s, worker_id = %s, claimed_at = %s
            WHERE id = %s AND status = %s
            """,
            (JOB_STATUS_CLAIMED, worker_name, claimed_at, row["id"], JOB_STATUS_PENDING),
        )
        conn.commit()
        if result.rowcount != 1:
            return None
        row["claimed_at"] = claimed_at
        return row


def claim_job_by_id_sync(worker_name: str, job_id: int) -> dict | None:
    with mysql_connection() as conn:
        row = conn.execute(
            """
            SELECT id, job_key, job_type, task_id, task_name, status, payload_json, steps_json
            FROM worker_jobs
            WHERE id = %s
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if not row or row["status"] != JOB_STATUS_PENDING:
            return None
        claimed_at = now_iso()
        result = conn.execute(
            """
            UPDATE worker_jobs
            SET status = %s, worker_id = %s, claimed_at = %s
            WHERE id = %s AND status = %s
            """,
            (JOB_STATUS_CLAIMED, worker_name, claimed_at, job_id, JOB_STATUS_PENDING),
        )
        conn.commit()
        if result.rowcount != 1:
            return None
        row["claimed_at"] = claimed_at
        return row


def claim_job_by_key_sync(worker_name: str, job_key: str) -> dict | None:
    with mysql_connection() as conn:
        row = conn.execute(
            """
            SELECT id, job_key, job_type, task_id, task_name, status, payload_json, steps_json
            FROM worker_jobs
            WHERE job_key = %s
            LIMIT 1
            """,
            (job_key,),
        ).fetchone()
        if not row or row["status"] != JOB_STATUS_PENDING:
            return None
        claimed_at = now_iso()
        result = conn.execute(
            """
            UPDATE worker_jobs
            SET status = %s, worker_id = %s, claimed_at = %s
            WHERE id = %s AND status = %s
            """,
            (JOB_STATUS_CLAIMED, worker_name, claimed_at, row["id"], JOB_STATUS_PENDING),
        )
        conn.commit()
        if result.rowcount != 1:
            return None
        row["claimed_at"] = claimed_at
        return row


def finish_job_sync(job_id: int, *, status: str, process_id: int | None = None, error_message: str | None = None) -> None:
    with mysql_connection() as conn:
        conn.execute(
            """
            UPDATE worker_jobs
            SET status = %s,
                process_id = %s,
                finished_at = %s,
                error_message = %s
            WHERE id = %s
            """,
            (status, process_id, now_iso(), error_message, job_id),
        )
        conn.commit()


def update_job_progress_sync(job_id: int, *, step: str | None, message: str, steps_json: str | None = None) -> None:
    with mysql_connection() as conn:
        conn.execute(
            """
            UPDATE worker_jobs
            SET status = %s,
                current_step = %s,
                message = %s,
                steps_json = COALESCE(%s, steps_json)
            WHERE id = %s
            """,
            ("running", step, message, steps_json, job_id),
        )
        conn.commit()


def complete_generate_job_sync(job_id: int, *, task_id: int, result_json: str, message: str, steps_json: str | None = None) -> None:
    with mysql_connection() as conn:
        conn.execute(
            """
            UPDATE worker_jobs
            SET task_id = %s,
                status = %s,
                current_step = NULL,
                message = %s,
                steps_json = COALESCE(%s, steps_json),
                result_json = %s,
                finished_at = %s,
                error_message = NULL
            WHERE id = %s
            """,
            (task_id, JOB_STATUS_COMPLETED, message, steps_json, result_json, now_iso(), job_id),
        )
        conn.commit()


def fail_generate_job_sync(job_id: int, *, error_message: str, step: str | None = None, steps_json: str | None = None) -> None:
    with mysql_connection() as conn:
        conn.execute(
            """
            UPDATE worker_jobs
            SET status = %s,
                current_step = %s,
                message = %s,
                steps_json = COALESCE(%s, steps_json),
                finished_at = %s,
                error_message = %s
            WHERE id = %s
            """,
            (JOB_STATUS_FAILED, step, error_message, steps_json, now_iso(), error_message, job_id),
        )
        conn.commit()


def update_job_process_sync(job_id: int, process_id: int) -> None:
    with mysql_connection() as conn:
        conn.execute(
            "UPDATE worker_jobs SET process_id = %s WHERE id = %s",
            (process_id, job_id),
        )
        conn.commit()


def set_task_running_sync(task_id: int, is_running: bool) -> None:
    with mysql_connection() as conn:
        conn.execute(
            "UPDATE tasks SET is_running = %s WHERE id = %s",
            (1 if is_running else 0, task_id),
        )
        conn.commit()


def clear_stale_claimed_jobs_sync(worker_name: str) -> None:
    with mysql_connection() as conn:
        conn.execute(
            """
            UPDATE worker_jobs
            SET status = %s,
                worker_id = NULL,
                claimed_at = NULL,
                error_message = %s
            WHERE status = %s AND worker_id = %s
            """,
            (JOB_STATUS_PENDING, "worker restarted before finishing job", JOB_STATUS_CLAIMED, worker_name),
        )
        conn.commit()


def claim_next_job_from_redis_sync(worker_name: str, timeout_seconds: float) -> dict | None:
    client = get_redis_client()
    if client is None:
        return None
    timeout = max(1, int(round(timeout_seconds)))
    raw = client.brpop(redis_queue_name(), timeout=timeout)
    if not raw:
        return None
    _, payload_raw = raw
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return None
    job_id = int(payload.get("job_id") or 0)
    job_key = str(payload.get("job_key") or "").strip()
    if job_id > 0:
        claimed = claim_job_by_id_sync(worker_name, job_id)
        if claimed is not None:
            return claimed
    if job_key:
        return claim_job_by_key_sync(worker_name, job_key)
    return None


def next_job_sync(worker_name: str, interval: float) -> dict | None:
    if queue_backend() == "redis":
        claimed = claim_next_job_from_redis_sync(worker_name, interval)
        if claimed is not None:
            return claimed
    return claim_next_job_sync(worker_name)


def parse_json_field(raw: str | None, fallback: object) -> object:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def apply_step_progress(steps: list[dict], step_key: str | None, message: str) -> list[dict]:
    updated = [dict(step) for step in steps]
    target_index = -1
    for index, step in enumerate(updated):
        if step.get("key") == step_key:
            target_index = index
            break
    for index, step in enumerate(updated):
        current_status = str(step.get("status") or "pending")
        if target_index >= 0 and index < target_index and current_status != "failed":
            step["status"] = "completed"
        elif index == target_index:
            step["status"] = "running"
            step["message"] = message
        elif current_status != "failed":
            step["status"] = "pending"
            step["message"] = ""
    return updated


def finalize_steps(steps: list[dict], final_status: str, message: str, step_key: str | None = None) -> list[dict]:
    updated = [dict(step) for step in steps]
    if final_status == "completed":
        for step in updated:
            if str(step.get("status") or "") != "failed":
                step["status"] = "completed"
    elif final_status == "failed" and step_key:
        for step in updated:
            if step.get("key") == step_key:
                step["status"] = "failed"
                step["message"] = message
                break
    return updated


def launch_task_process(task_id: int) -> subprocess.Popen:
    runtime_state = materialize_runtime_account_states_sync(
        runtime_state_dir=get_runtime_account_state_dir(),
        runtime_default_state_file=get_runtime_default_state_file(),
    )
    command = [
        sys.executable,
        "-u",
        "spider_v2.py",
        "--task-id",
        str(task_id),
    ]
    return subprocess.Popen(
        command,
        cwd=str(ROOT),
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "ACCOUNT_STATE_DIR": runtime_state["runtime_state_dir"],
            "STATE_FILE": runtime_state["runtime_default_state_file"],
            "RUNNING_IN_DOCKER": "true",
            "LOGIN_IS_EDGE": "false",
        },
        preexec_fn=os.setsid,
    )


def launch_generation_process(payload: dict) -> subprocess.Popen:
    command = [
        sys.executable,
        "-u",
        "tools/task_generation_bridge.py",
    ]
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
        },
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if process.stdin is None:
        raise RuntimeError("生成任务进程未提供标准输入")
    process.stdin.write(json.dumps(payload, ensure_ascii=False))
    process.stdin.close()
    return process


def monitor_finished_processes(running_tasks: dict[int, RunningTask]) -> None:
    finished_task_ids: list[int] = []
    for task_id, running in running_tasks.items():
        return_code = running.process.poll()
        if return_code is None:
            continue
        set_task_running_sync(task_id, False)
        publish_task_events(task_id, False, running.tenant_id)
        publish_results_updated(
            {
                "task_id": task_id,
                "tenant_id": running.tenant_id,
                "reason": "task_finished",
                "exit_code": return_code,
            },
            running.tenant_id,
        )
        finished_task_ids.append(task_id)
    for task_id in finished_task_ids:
        running_tasks.pop(task_id, None)


def handle_start_job(job: dict, running_tasks: dict[int, RunningTask]) -> None:
    task_id = int(job["task_id"])
    task = find_task_by_id_sync(task_id)
    if task is None:
        finish_job_sync(job["id"], status=JOB_STATUS_FAILED, error_message="任务不存在")
        return
    if not task.enabled:
        finish_job_sync(job["id"], status=JOB_STATUS_FAILED, error_message="任务已禁用")
        return
    current = running_tasks.get(task_id)
    if current and current.process.poll() is None:
        finish_job_sync(job["id"], status=JOB_STATUS_COMPLETED, process_id=current.process.pid)
        return

    process = launch_task_process(task_id)
    running_tasks[task_id] = RunningTask(task_id=task_id, tenant_id=task.tenant_id, process=process)
    set_task_running_sync(task_id, True)
    update_job_process_sync(job["id"], process.pid)
    finish_job_sync(job["id"], status=JOB_STATUS_COMPLETED, process_id=process.pid)
    publish_task_events(task_id, True, task.tenant_id)


def handle_stop_job(job: dict, running_tasks: dict[int, RunningTask]) -> None:
    task_id = int(job["task_id"])
    task = find_task_by_id_sync(task_id)
    tenant_scope = task.tenant_id if task is not None else None
    current = running_tasks.get(task_id)
    if current and current.process.poll() is None:
        os.killpg(os.getpgid(current.process.pid), signal.SIGTERM)
        try:
            current.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(current.process.pid), signal.SIGKILL)
            current.process.wait(timeout=5)
        running_tasks.pop(task_id, None)
    set_task_running_sync(task_id, False)
    finish_job_sync(job["id"], status=JOB_STATUS_COMPLETED)
    publish_task_events(task_id, False, tenant_scope)


def handle_generate_job(job: dict) -> None:
    payload = parse_json_field(job.get("payload_json"), {})
    if not isinstance(payload, dict):
        fail_generate_job_sync(job["id"], error_message="生成任务载荷无效", step="prepare")
        return

    steps = parse_json_field(job.get("steps_json"), [])
    if not isinstance(steps, list):
        steps = []

    process = launch_generation_process(payload)
    if process.stdout is None:
        fail_generate_job_sync(job["id"], error_message="生成任务进程未提供标准输出", step="prepare")
        return

    last_step: str | None = None
    last_message = "任务已排队，等待开始。"
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = str(event.get("type") or "").strip()
        if event_type == "progress":
            last_step = str(event.get("step") or "").strip() or None
            last_message = str(event.get("message") or "").strip() or last_message
            steps = apply_step_progress(steps, last_step, last_message)
            update_job_progress_sync(
                job["id"],
                step=last_step,
                message=last_message,
                steps_json=json.dumps(steps, ensure_ascii=False),
            )
        elif event_type == "result":
            raw_task = event.get("task")
            if not isinstance(raw_task, dict):
                fail_generate_job_sync(job["id"], error_message="生成任务未返回有效结果", step=last_step, steps_json=json.dumps(steps, ensure_ascii=False))
                process.wait(timeout=5)
                return
            task_id = int(raw_task.get("id") or 0)
            task_name = str(raw_task.get("task_name") or payload.get("task_name") or "任务")
            steps = finalize_steps(steps, "completed", f"任务“{task_name}”创建完成。")
            complete_generate_job_sync(
                job["id"],
                task_id=task_id,
                result_json=json.dumps(raw_task, ensure_ascii=False),
                message=f"任务“{task_name}”创建完成。",
                steps_json=json.dumps(steps, ensure_ascii=False),
            )
            tenant_scope = raw_task.get("tenant_id")
            if isinstance(tenant_scope, bool) or not isinstance(tenant_scope, int):
                tenant_scope = None
            publish_event_sync(
                "tasks_updated",
                {
                    "task_id": task_id,
                    "task_name": task_name,
                    "tenant_id": tenant_scope,
                    "source": "generate_task",
                },
                tenant_scope,
            )
            process.wait(timeout=5)
            return
        elif event_type == "error":
            error_message = str(event.get("error") or "AI 任务生成失败").strip()
            steps = finalize_steps(steps, "failed", error_message, last_step)
            fail_generate_job_sync(
                job["id"],
                error_message=error_message,
                step=last_step,
                steps_json=json.dumps(steps, ensure_ascii=False),
            )
            process.wait(timeout=5)
            return

    return_code = process.wait()
    if return_code != 0:
        error_message = last_message if last_message and last_message != "任务已排队，等待开始。" else f"AI 任务生成失败，退出码 {return_code}"
        steps = finalize_steps(steps, "failed", error_message, last_step)
        fail_generate_job_sync(
            job["id"],
            error_message=error_message,
            step=last_step,
            steps_json=json.dumps(steps, ensure_ascii=False),
        )
        return

    fail_generate_job_sync(
        job["id"],
        error_message="AI 任务生成未返回结果",
        step=last_step,
        steps_json=json.dumps(steps, ensure_ascii=False),
    )


def handle_reanalyze_job(job: dict) -> None:
    payload = parse_json_field(job.get("payload_json"), {})
    if not isinstance(payload, dict):
        fail_generate_job_sync(job["id"], error_message="重分析任务载荷无效", step="reanalyze")
        return

    update_job_progress_sync(
        job["id"],
        step="reanalyze",
        message="正在重新分析结果集。",
    )

    command = [
        sys.executable,
        "-u",
        "tools/result_reanalysis_bridge.py",
    ]
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
        },
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if process.stdin is None or process.stdout is None:
        fail_generate_job_sync(job["id"], error_message="重分析进程未正确初始化", step="reanalyze")
        return

    process.stdin.write(json.dumps(payload, ensure_ascii=False))
    process.stdin.close()

    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = str(event.get("type") or "").strip()
        if event_type == "result":
            raw_payload = event.get("payload")
            if not isinstance(raw_payload, dict):
                fail_generate_job_sync(job["id"], error_message="重分析未返回有效结果", step="reanalyze")
                process.wait(timeout=5)
                return
            result_json = json.dumps(raw_payload, ensure_ascii=False)
            message = str(raw_payload.get("message") or "结果集已完成重新分析").strip()
            complete_generate_job_sync(
                job["id"],
                task_id=int(raw_payload.get("task_id") or 0),
                result_json=result_json,
                message=message,
            )
            tenant_scope = payload.get("tenant_scope")
            if isinstance(tenant_scope, bool) or not isinstance(tenant_scope, int):
                tenant_scope = None
            publish_results_updated(
                {
                    "filename": payload.get("filename"),
                    "tenant_id": tenant_scope,
                    "source": "reanalyze_result",
                },
                tenant_scope,
            )
            process.wait(timeout=5)
            return
        if event_type == "error":
            error_message = str(event.get("error") or "结果重分析失败").strip()
            fail_generate_job_sync(job["id"], error_message=error_message, step="reanalyze")
            process.wait(timeout=5)
            return

    return_code = process.wait()
    if return_code != 0:
        fail_generate_job_sync(job["id"], error_message=f"结果重分析失败，退出码 {return_code}", step="reanalyze")
        return
    fail_generate_job_sync(job["id"], error_message="结果重分析未返回结果", step="reanalyze")


def main() -> int:
    bootstrap_mysql_storage()
    worker_name = worker_id()
    clear_stale_claimed_jobs_sync(worker_name)

    running_tasks: dict[int, RunningTask] = {}
    interval = poll_seconds()

    try:
        while True:
            monitor_finished_processes(running_tasks)
            job = next_job_sync(worker_name, interval)
            if not job:
                time.sleep(interval)
                continue
            job_type = str(job.get("job_type") or "").strip()
            try:
                if job_type == "start_task":
                    handle_start_job(job, running_tasks)
                elif job_type == "stop_task":
                    handle_stop_job(job, running_tasks)
                elif job_type == "generate_task":
                    handle_generate_job(job)
                elif job_type == "reanalyze_result":
                    handle_reanalyze_job(job)
                else:
                    finish_job_sync(job["id"], status=JOB_STATUS_FAILED, error_message=f"未知任务类型: {job_type}")
            except Exception as exc:  # pragma: no cover - daemon path
                finish_job_sync(job["id"], status=JOB_STATUS_FAILED, error_message=str(exc))
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        for running in list(running_tasks.values()):
            if running.process.poll() is None:
                with contextlib.suppress(Exception):
                    os.killpg(os.getpgid(running.process.pid), signal.SIGTERM)
        for task_id in list(running_tasks):
            with contextlib.suppress(Exception):
                set_task_running_sync(task_id, False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
