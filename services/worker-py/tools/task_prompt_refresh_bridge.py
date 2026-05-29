from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prompt_utils import generate_criteria
from src.services.prompt_document_service import PROMPT_SOURCE_GENERATED, upsert_prompt_document
from src.services.task_generation_runner import build_criteria_filename
from src.services.task_prompt_service import (
    build_criteria_generation_input,
    build_task_prompt_payload,
)


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


async def main() -> int:
    try:
        raw = json.loads(sys.stdin.read() or "{}")
        task_name = str(raw.get("task_name") or "").strip()
        keyword = str(raw.get("keyword") or "").strip()
        description = str(raw.get("description") or "").strip()
        base_prompt_file = str(raw.get("base_prompt_file") or "prompts/base_prompt.txt").strip() or "prompts/base_prompt.txt"

        if not task_name:
            raise ValueError("任务名称不能为空")
        if not keyword:
            raise ValueError("搜索关键词不能为空")
        if not description:
            raise ValueError("AI 模式下详细需求不能为空")

        emit({"type": "progress", "step": "reference", "message": "正在读取参考标准。"})
        generated_criteria = await generate_criteria(
            user_description=build_criteria_generation_input(
                task_name=task_name,
                keyword=keyword,
                description=description,
            ),
            reference_file_path="prompts/macbook_criteria.txt",
        )
        if not generated_criteria or not generated_criteria.strip():
            raise RuntimeError("AI 未能生成分析标准，返回内容为空。")

        output_filename = build_criteria_filename(keyword)
        upsert_prompt_document(
            output_filename,
            generated_criteria.strip(),
            source=PROMPT_SOURCE_GENERATED,
        )
        payload = build_task_prompt_payload(
            base_prompt_file=base_prompt_file,
            criteria_file=output_filename,
            criteria_text=generated_criteria,
        )
        emit(
            {
                "type": "result",
                "payload": {
                    "ai_prompt_base_file": payload["ai_prompt_base_file"],
                    "ai_prompt_criteria_file": payload["ai_prompt_criteria_file"],
                    "ai_prompt_base_text": payload["ai_prompt_base_text"],
                    "ai_prompt_criteria_text": payload["ai_prompt_criteria_text"],
                    "ai_prompt_text": payload["ai_prompt_text"],
                },
            }
        )
        return 0
    except Exception as exc:
        emit({"type": "error", "error": f"AI 标准刷新失败: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
