"""
任务管理路由
"""
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from api.dependencies import (
    require_authenticated_user,
    require_workspace_user,
    get_process_service,
    get_scheduler_service,
    get_task_generation_service,
    get_task_service,
)
from src.domain.models.auth import AuthenticatedUser
from src.services.task_service import TaskService
from src.services.process_service import ProcessService
from src.services.scheduler_service import SchedulerService
from src.services.task_generation_service import TaskGenerationService
from src.services.task_generation_runner import (
    build_task_create,
    run_ai_generation_job,
)
from src.services.task_payloads import serialize_task, serialize_tasks
from src.domain.models.task import TaskCreate, TaskUpdate, TaskGenerateRequest
from src.services.auth_service import get_tenant_workspace_status
from src.prompt_utils import generate_criteria
from src.utils import resolve_task_log_path
from src.services.account_strategy_service import normalize_account_strategy
from src.services.task_prompt_service import (
    build_criteria_generation_input,
    build_task_prompt_payload,
)
from src.services.prompt_document_service import (
    PROMPT_SOURCE_GENERATED,
    upsert_prompt_document,
)
from src.infrastructure.persistence.storage_names import build_result_filename
from src.services.price_history_service import delete_price_snapshots
from src.services.result_storage_service import GLOBAL_TENANT_SCOPE
from src.services.result_storage_service import delete_result_file_records
router = APIRouter(prefix="/api/tasks", tags=["tasks"])

async def _reload_scheduler_if_needed(
    task_service: TaskService,
    scheduler_service: SchedulerService,
):
    tasks = await task_service.get_all_tasks()
    await scheduler_service.reload_jobs(tasks)


def _has_keyword_rules(rules) -> bool:
    return bool(rules and len(rules) > 0)


def _validate_final_account_strategy(existing_task, task_update: TaskUpdate) -> None:
    account_state_file = (
        task_update.account_state_file
        if task_update.account_state_file is not None
        else existing_task.account_state_file
    )
    account_strategy = normalize_account_strategy(
        task_update.account_strategy,
        account_state_file,
    )
    task_update.account_strategy = account_strategy
    if account_strategy == "fixed" and not account_state_file:
        raise HTTPException(status_code=400, detail="固定账号模式下必须选择账号。")


def _is_task_accessible(task, current_user: AuthenticatedUser) -> bool:
    if current_user.role == "admin":
        return True
    return (
        current_user.tenant_id is not None
        and task.tenant_id == current_user.tenant_id
    )


def _require_task_access(task, current_user: AuthenticatedUser) -> None:
    if not _is_task_accessible(task, current_user):
        raise HTTPException(status_code=404, detail="任务未找到")


def _filter_tasks_for_user(tasks: list, current_user: AuthenticatedUser) -> list:
    if current_user.role == "admin":
        return tasks
    return [task for task in tasks if _is_task_accessible(task, current_user)]


def _ensure_can_use_ai(current_user: AuthenticatedUser) -> None:
    if current_user.role == "tenant" and not current_user.can_use_ai:
        raise HTTPException(status_code=403, detail="当前租户未开通 AI 分析能力")


@router.get("", response_model=List[dict])
async def get_tasks(
    tenant_id: int | None = Query(default=None),
    service: TaskService = Depends(get_task_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    """获取所有任务"""
    tasks = _filter_tasks_for_user(await service.get_all_tasks(), current_user)
    if tenant_id is not None:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="当前账号无权按租户筛选任务")
        tasks = [task for task in tasks if task.tenant_id == tenant_id]
    return serialize_tasks(tasks, scheduler_service)
@router.get("/{task_id}", response_model=dict)
async def get_task(
    task_id: int,
    service: TaskService = Depends(get_task_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    """获取单个任务"""
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")
    _require_task_access(task, current_user)
    return serialize_task(task, scheduler_service)
@router.post("/", response_model=dict)
async def create_task(
    task_create: TaskCreate,
    service: TaskService = Depends(get_task_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    """创建新任务"""
    if task_create.decision_mode == "ai":
        _ensure_can_use_ai(current_user)
    if current_user.role == "tenant":
        task_create = task_create.model_copy(update={"tenant_id": current_user.tenant_id})
    task = await service.create_task(task_create)
    await _reload_scheduler_if_needed(service, scheduler_service)
    return {"message": "任务创建成功", "task": serialize_task(task, scheduler_service)}
@router.post("/generate", response_model=dict)
async def generate_task(
    req: TaskGenerateRequest,
    service: TaskService = Depends(get_task_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    generation_service: TaskGenerationService = Depends(get_task_generation_service),
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    """创建任务。AI模式会生成分析标准，关键词模式直接保存规则。"""
    print(f"收到任务生成请求: {req.task_name}，模式: {req.decision_mode}")
    if current_user.role == "tenant":
        req = req.model_copy(update={"tenant_id": current_user.tenant_id})

    try:
        mode = req.decision_mode or "ai"
        if mode == "ai":
            _ensure_can_use_ai(current_user)
            job = await generation_service.create_job(req.task_name)
            generation_service.track(
                run_ai_generation_job(
                    job_id=job.job_id,
                    req=req,
                    task_service=service,
                    scheduler_service=scheduler_service,
                    generation_service=generation_service,
                )
            )
            return JSONResponse(
                status_code=202,
                content={
                    "message": "AI 任务生成已开始。",
                    "job": job.model_dump(mode="json"),
                },
            )

        task = await service.create_task(build_task_create(req, ""))
        await _reload_scheduler_if_needed(service, scheduler_service)
        return {"message": "任务创建成功。", "task": serialize_task(task, scheduler_service)}

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"AI任务生成API发生未知错误: {str(e)}"
        print(error_msg)
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)
@router.get("/generate-jobs/{job_id}", response_model=dict)
async def get_task_generation_job(
    job_id: str,
    generation_service: TaskGenerationService = Depends(get_task_generation_service),
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    """获取任务生成作业状态"""
    job = await generation_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务生成作业未找到")
    return {"job": job.model_dump(mode="json")}
@router.patch("/{task_id}", response_model=dict)
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    service: TaskService = Depends(get_task_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    """更新任务"""
    try:
        existing_task = await service.get_task(task_id)
        if not existing_task:
            raise HTTPException(status_code=404, detail="任务未找到")
        _require_task_access(existing_task, current_user)
        if current_user.role == "tenant":
            task_update.tenant_id = existing_task.tenant_id
        target_mode = task_update.decision_mode or getattr(existing_task, "decision_mode", "ai") or "ai"
        if target_mode == "ai":
            _ensure_can_use_ai(current_user)
        _validate_final_account_strategy(existing_task, task_update)

        current_mode = getattr(existing_task, "decision_mode", "ai") or "ai"
        description_changed = (
            task_update.description is not None
            and task_update.description != existing_task.description
        )
        switched_to_ai = current_mode != "ai" and target_mode == "ai"

        if target_mode == "keyword":
            final_rules = (
                task_update.keyword_rules
                if task_update.keyword_rules is not None
                else getattr(existing_task, "keyword_rules", [])
            )
            if not _has_keyword_rules(final_rules):
                raise HTTPException(status_code=400, detail="关键词模式下至少需要一个关键词。")
        if target_mode == "ai" and (description_changed or switched_to_ai):
            print(f"检测到任务 {task_id} 需要刷新 AI 标准文件，开始重新生成...")
            try:
                description_for_ai = (
                    task_update.description
                    if task_update.description is not None
                    else existing_task.description
                )
                if not str(description_for_ai or "").strip():
                    raise HTTPException(status_code=400, detail="AI 模式下详细需求不能为空。")
                safe_keyword = "".join(
                    c for c in existing_task.keyword.lower().replace(' ', '_')
                    if c.isalnum() or c in "_-"
                ).rstrip()
                output_filename = f"prompts/{safe_keyword}_criteria.txt"
                print(f"目标文件路径: {output_filename}")
                print("开始调用 AI 生成新的分析标准...")
                generated_criteria = await generate_criteria(
                    user_description=build_criteria_generation_input(
                        task_name=existing_task.task_name,
                        keyword=existing_task.keyword,
                        description=description_for_ai,
                    ),
                    reference_file_path="prompts/macbook_criteria.txt"
                )
                if not generated_criteria or len(generated_criteria.strip()) == 0:
                    print("AI 返回的内容为空")
                    raise HTTPException(status_code=500, detail="AI 未能生成分析标准，返回内容为空。")
                print(f"保存新的分析标准到: {output_filename}")
                upsert_prompt_document(
                    output_filename,
                    generated_criteria.strip(),
                    source=PROMPT_SOURCE_GENERATED,
                )
                print(f"新的分析标准已保存")
                prompt_payload = build_task_prompt_payload(
                    base_prompt_file=(
                        existing_task.ai_prompt_base_file or "prompts/base_prompt.txt"
                    ),
                    criteria_file=output_filename,
                    criteria_text=generated_criteria,
                )
                task_update.ai_prompt_base_file = prompt_payload["ai_prompt_base_file"]
                task_update.ai_prompt_criteria_file = prompt_payload["ai_prompt_criteria_file"]
                task_update.ai_prompt_base_text = prompt_payload["ai_prompt_base_text"]
                task_update.ai_prompt_criteria_text = prompt_payload["ai_prompt_criteria_text"]
                task_update.ai_prompt_text = prompt_payload["ai_prompt_text"]
                print(f"已更新 ai_prompt_criteria_file 字段为: {output_filename}")
            except HTTPException:
                raise
            except Exception as e:
                error_msg = f"重新生成 criteria 文件时出错: {str(e)}"
                print(error_msg)
                import traceback
                print(traceback.format_exc())
                raise HTTPException(status_code=500, detail=error_msg)
        task = await service.update_task(task_id, task_update)
        await _reload_scheduler_if_needed(service, scheduler_service)
        return {"message": "任务更新成功", "task": serialize_task(task, scheduler_service)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
@router.delete("/{task_id}", response_model=dict)
async def delete_task(
    task_id: int,
    service: TaskService = Depends(get_task_service),
    process_service: ProcessService = Depends(get_process_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    """删除任务"""
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")
    _require_task_access(task, current_user)

    await process_service.stop_task(task_id)
    success = await service.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="任务未找到")
    await _reload_scheduler_if_needed(service, scheduler_service)
    try:
        keyword = (task.keyword or "").strip()
        if keyword:
            remaining_tasks = await service.get_all_tasks()
            if task.tenant_id is None:
                remaining_tasks = [
                    remaining_task for remaining_task in remaining_tasks
                    if remaining_task.tenant_id is None
                ]
                tenant_scope = GLOBAL_TENANT_SCOPE
            else:
                remaining_tasks = [
                    remaining_task for remaining_task in remaining_tasks
                    if remaining_task.tenant_id == task.tenant_id
                ]
                tenant_scope = task.tenant_id
            keyword_still_in_use = any(
                (remaining_task.keyword or "").strip() == keyword
                for remaining_task in remaining_tasks
            )
            if not keyword_still_in_use:
                await delete_result_file_records(
                    build_result_filename(keyword),
                    tenant_scope=tenant_scope,
                )
                delete_price_snapshots(keyword, tenant_scope=tenant_scope)
    except Exception as e:
        print(f"删除任务结果文件时出错: {e}")

    try:
        log_file_path = resolve_task_log_path(task_id, task.task_name)
        if os.path.exists(log_file_path):
            os.remove(log_file_path)
    except Exception as e:
        print(f"删除任务日志文件时出错: {e}")
    return {"message": "任务删除成功"}
@router.post("/start/{task_id}", response_model=dict)
async def start_task(
    task_id: int,
    task_service: TaskService = Depends(get_task_service),
    process_service: ProcessService = Depends(get_process_service),
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    """启动单个任务"""
    task = await task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")
    _require_task_access(task, current_user)
    if not task.enabled:
        raise HTTPException(status_code=400, detail="任务已被禁用，无法启动")
    if task.is_running:
        raise HTTPException(status_code=400, detail="任务已在运行中")
    if task.tenant_id is not None:
        workspace_status = await get_tenant_workspace_status(task.tenant_id)
        if not workspace_status.get("workspace_enabled", True):
            raise HTTPException(status_code=400, detail="租户工作台已过期或已停用，无法启动任务")
    success = await process_service.start_task(task_id, task.task_name, start_source="manual")
    if not success:
        raise HTTPException(status_code=500, detail="启动任务失败")
    return {"message": f"任务 '{task.task_name}' 已启动"}
@router.post("/stop/{task_id}", response_model=dict)
async def stop_task(
    task_id: int,
    task_service: TaskService = Depends(get_task_service),
    process_service: ProcessService = Depends(get_process_service),
    current_user: AuthenticatedUser = Depends(require_workspace_user),
):
    """停止单个任务"""
    task = await task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")
    _require_task_access(task, current_user)
    await process_service.stop_task(task_id)
    return {"message": f"任务ID {task_id} 已发送停止信号"}
