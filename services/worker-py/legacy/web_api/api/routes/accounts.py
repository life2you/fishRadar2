"""闲鱼账号管理路由"""
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from src.services.account_state_service import (
    get_account_state_sync,
    list_account_states_sync,
    upsert_account_state_sync,
    delete_account_state_sync,
    validate_state_json,
)


router = APIRouter(prefix="/api/accounts", tags=["accounts"])

ACCOUNT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,50}$")


class AccountCreate(BaseModel):
    name: str
    content: str


class AccountUpdate(BaseModel):
    content: str


def _validate_name(name: str) -> str:
    trimmed = name.strip()
    if not trimmed or not ACCOUNT_NAME_RE.match(trimmed):
        raise HTTPException(status_code=400, detail="账号名称只能包含字母、数字、下划线或短横线。")
    return trimmed

def _validate_json(content: str) -> None:
    try:
        validate_state_json(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=List[dict])
async def list_accounts():
    return list_account_states_sync()


@router.get("/{name}", response_model=dict)
async def get_account(name: str):
    account_name = _validate_name(name)
    detail = get_account_state_sync(account_name)
    if detail is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    return detail


@router.post("", response_model=dict)
async def create_account(data: AccountCreate):
    account_name = _validate_name(data.name)
    _validate_json(data.content)
    if get_account_state_sync(account_name) is not None:
        raise HTTPException(status_code=409, detail="账号已存在")
    detail = upsert_account_state_sync(account_name, data.content)
    return {"message": "账号已添加", **detail}


@router.put("/{name}", response_model=dict)
async def update_account(name: str, data: AccountUpdate):
    account_name = _validate_name(name)
    _validate_json(data.content)
    if get_account_state_sync(account_name) is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    detail = upsert_account_state_sync(account_name, data.content)
    return {"message": "账号已更新", **detail}


@router.delete("/{name}", response_model=dict)
async def delete_account(name: str):
    account_name = _validate_name(name)
    if not delete_account_state_sync(account_name):
        raise HTTPException(status_code=404, detail="账号不存在")
    return {"message": "账号已删除"}
