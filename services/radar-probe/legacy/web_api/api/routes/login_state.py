"""登录状态管理路由"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.services.account_state_service import (
    delete_default_login_state_sync,
    upsert_default_login_state_sync,
    validate_state_json,
)

router = APIRouter(prefix="/api/login-state", tags=["login-state"])


class LoginStateUpdate(BaseModel):
    """登录状态更新模型"""
    content: str


@router.post("", response_model=dict)
async def update_login_state(
    data: LoginStateUpdate,
):
    """接收前端发送的登录状态JSON字符串，并保存到数据库。"""

    try:
        validate_state_json(data.content)
        upsert_default_login_state_sync(data.content)
        return {"message": "默认登录状态已成功更新。"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入默认登录状态时出错: {e}")


@router.delete("", response_model=dict)
async def delete_login_state():
    """删除默认登录状态。"""
    try:
        deleted = delete_default_login_state_sync()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除默认登录状态时出错: {e}")

    if deleted:
        return {"message": "默认登录状态已成功删除。"}
    return {"message": "默认登录状态不存在，无需删除。"}
