from __future__ import annotations

import os
from typing import Any

from src.domain.models.task import Task
from src.infrastructure.persistence.storage_names import build_result_filename
from src.keyword_rule_engine import build_search_text, evaluate_keyword_rules
from src.services.ai_service import AIAnalysisService
from src.services.image_runtime_service import download_all_images
from src.services.result_storage_service import (
    GLOBAL_TENANT_SCOPE,
    load_all_result_records,
    update_result_analysis,
)
from src.services.task_prompt_service import resolve_runtime_ai_prompt
from src.services.task_service import TaskService


def _matches_tenant_scope(task: Task, tenant_scope) -> bool:
    if tenant_scope in {None, GLOBAL_TENANT_SCOPE}:
        return task.tenant_id is None
    return task.tenant_id == int(tenant_scope)


def _cleanup_images(image_paths: list[str]) -> None:
    for image_path in image_paths:
        try:
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
        except OSError:
            continue


def _build_ai_error_result(reason: str, *, error: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "analysis_source": "ai",
        "is_recommended": False,
        "reason": reason,
        "keyword_hit_count": 0,
    }
    if error:
        payload["error"] = error
    return payload


async def _resolve_task_for_result_file(
    *,
    filename: str,
    tenant_scope,
    records: list[dict],
    task_service: TaskService,
) -> Task:
    tasks = [task for task in await task_service.get_all_tasks() if _matches_tenant_scope(task, tenant_scope)]
    if not tasks:
        raise ValueError("当前结果集未找到对应任务")

    task_name = str((records[0].get("任务名称") if records else "") or "").strip()

    matching_by_name = [task for task in tasks if task_name and task.task_name == task_name]
    matching_by_keyword = [
        task for task in tasks if build_result_filename(task.keyword) == filename
    ]

    exact_matches = [task for task in matching_by_name if task in matching_by_keyword]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(matching_by_name) == 1:
        return matching_by_name[0]
    if len(matching_by_keyword) == 1:
        return matching_by_keyword[0]
    raise ValueError("当前结果集对应多个任务，请先收敛重复关键词后再重试")


async def _reanalyze_record(
    *,
    record: dict,
    task: Task,
    ai_service: AIAnalysisService,
) -> dict[str, Any]:
    if task.decision_mode == "keyword":
        return evaluate_keyword_rules(list(task.keyword_rules or []), build_search_text(record))

    prompt_text = resolve_runtime_ai_prompt(task.model_dump())
    if not prompt_text:
        return _build_ai_error_result("任务未配置 AI Prompt，跳过分析。", error="missing_ai_prompt")

    image_paths: list[str] = []
    try:
        if task.analyze_images:
            item_data = record.get("商品信息", {}) or {}
            image_urls = item_data.get("商品图片列表") or []
            item_id = str(item_data.get("商品ID") or "unknown")
            if image_urls:
                image_paths = await download_all_images(item_id, image_urls, task.task_name)

        ai_result = await ai_service.analyze_product(record, image_paths, prompt_text)
        if not ai_result:
            return _build_ai_error_result(
                "AI 分析未返回有效结果，已自动重试。",
                error="AI analysis returned None after retries.",
            )
        ai_result.setdefault("analysis_source", "ai")
        ai_result.setdefault("keyword_hit_count", 0)
        return ai_result
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        return _build_ai_error_result(f"AI分析异常: {exc}", error=str(exc))
    finally:
        _cleanup_images(image_paths)


async def reanalyze_result_file(
    *,
    filename: str,
    tenant_scope,
    task_service: TaskService,
    ai_service: AIAnalysisService,
) -> dict[str, Any]:
    records = await load_all_result_records(
        filename,
        ai_recommended_only=False,
        keyword_recommended_only=False,
        sort_by="crawl_time",
        sort_order="desc",
        include_hidden=True,
        tenant_scope=tenant_scope,
    )
    if not records:
        raise ValueError("结果集为空，无法重分析")

    task = await _resolve_task_for_result_file(
        filename=filename,
        tenant_scope=tenant_scope,
        records=records,
        task_service=task_service,
    )

    updated_count = 0
    failed_count = 0
    for record in records:
        item = record.get("商品信息", {}) or {}
        item_id = str(item.get("商品ID") or "").strip()
        if not item_id:
            failed_count += 1
            continue
        ai_analysis = await _reanalyze_record(record=record, task=task, ai_service=ai_service)
        updated = await update_result_analysis(
            filename,
            item_id,
            ai_analysis,
            tenant_scope=tenant_scope,
        )
        if updated:
            updated_count += 1
        else:
            failed_count += 1

    return {
        "task_id": task.id,
        "task_name": task.task_name,
        "updated_count": updated_count,
        "failed_count": failed_count,
        "total_count": len(records),
    }
