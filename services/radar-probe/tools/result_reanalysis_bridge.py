from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.ai_service import AIAnalysisService
from src.services.result_reanalysis_service import reanalyze_result_file
from src.services.task_service import TaskService
from src.infrastructure.persistence.mysql_task_repository import MySQLTaskRepository
from src.services.result_storage_service import GLOBAL_TENANT_SCOPE


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def resolve_tenant_scope(raw_scope):
    if raw_scope in (None, "", GLOBAL_TENANT_SCOPE):
        return GLOBAL_TENANT_SCOPE
    return int(raw_scope)


async def main() -> int:
    try:
        raw = json.loads(sys.stdin.read() or "{}")
        filename = str(raw["filename"])
        tenant_scope = resolve_tenant_scope(raw.get("tenant_scope"))
        payload = await reanalyze_result_file(
            filename=filename,
            tenant_scope=tenant_scope,
            task_service=TaskService(MySQLTaskRepository()),
            ai_service=AIAnalysisService(),
        )
        emit({"type": "result", "payload": payload})
        return 0
    except Exception as exc:
        emit({"type": "error", "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
