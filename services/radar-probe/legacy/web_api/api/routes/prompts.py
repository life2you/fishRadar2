"""Prompt 管理路由"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.infrastructure.persistence.mysql_bootstrap import bootstrap_mysql_storage
from src.services.prompt_document_service import (
    PROMPT_SOURCE_MANUAL,
    get_prompt_document,
    list_prompt_documents,
    normalize_prompt_filename,
    upsert_prompt_document,
)

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


def _safe_prompt_key(filename: str) -> str:
    normalized = str(filename or "").strip().replace("\\", "/")
    if not normalized or ".." in normalized or normalized.startswith("/"):
        raise HTTPException(status_code=400, detail="无效的文件名")
    return normalize_prompt_filename(normalized)


class PromptUpdate(BaseModel):
    """Prompt 更新模型"""
    content: str


@router.get("")
async def list_prompts():
    """列出所有 prompt 文档"""
    bootstrap_mysql_storage()
    filenames = list_prompt_documents()
    return [name.rsplit("/", 1)[-1] for name in filenames]


@router.get("/{filename}")
async def get_prompt(filename: str):
    """获取 prompt 文档内容"""
    bootstrap_mysql_storage()
    prompt_key = _safe_prompt_key(filename)
    document = get_prompt_document(prompt_key)
    if document is None:
        raise HTTPException(status_code=404, detail="Prompt 文件未找到")
    return {"filename": document["filename"].rsplit("/", 1)[-1], "content": document["content"]}


@router.put("/{filename}")
async def update_prompt(
    filename: str,
    prompt_update: PromptUpdate,
):
    """更新 prompt 文档内容"""
    bootstrap_mysql_storage()
    prompt_key = _safe_prompt_key(filename)
    try:
        existing = get_prompt_document(prompt_key)
        if existing is None:
            raise HTTPException(status_code=404, detail="Prompt 文件未找到")
        document = upsert_prompt_document(
            prompt_key,
            prompt_update.content,
            source=PROMPT_SOURCE_MANUAL,
        )
        return {"message": f"Prompt 文件 '{filename}' 更新成功", "updated_at": document["updated_at"]}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"写入文件时出错: {e}")
