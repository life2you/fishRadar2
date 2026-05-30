from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.models.task import TaskGenerateRequest
from src.infrastructure.persistence.mysql_task_repository import MySQLTaskRepository
from src.services.prompt_document_service import PROMPT_SOURCE_GENERATED, upsert_prompt_document
from src.services.task_generation_runner import build_criteria_filename, build_task_create
from src.services.task_prompt_service import build_criteria_generation_input
from src.services.task_service import TaskService
from src.prompt_utils import generate_criteria


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


async def main() -> int:
    try:
        raw = json.loads(sys.stdin.read() or "{}")
        req = TaskGenerateRequest(**raw)
        task_service = TaskService(MySQLTaskRepository())

        emit({"type": "progress", "step": "prepare", "message": "已接收请求，开始准备分析标准。"})

        if (req.decision_mode or "ai") != "ai":
            task = await task_service.create_task(build_task_create(req, ""))
            emit({"type": "result", "task": task.model_dump(mode="json")})
            return 0

        async def report_progress(step_key: str, message: str) -> None:
            emit({"type": "progress", "step": step_key, "message": message})

        output_filename = build_criteria_filename(req.keyword)
        generated_criteria = await generate_criteria(
            user_description=build_criteria_generation_input(
                task_name=req.task_name,
                keyword=req.keyword,
                description=req.description,
            ),
            reference_file_path="prompts/macbook_criteria.txt",
            progress_callback=report_progress,
        )

        emit({"type": "progress", "step": "persist", "message": f"正在保存分析标准到 {output_filename}。"})
        upsert_prompt_document(
            output_filename,
            generated_criteria.strip(),
            source=PROMPT_SOURCE_GENERATED,
        )

        emit({"type": "progress", "step": "task", "message": "分析标准已生成，正在创建任务记录。"})
        task = await task_service.create_task(
            build_task_create(req, output_filename, criteria_text=generated_criteria),
        )
        emit({"type": "result", "task": task.model_dump(mode="json")})
        return 0
    except Exception as exc:
        emit({"type": "error", "error": f"AI 任务生成失败: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
