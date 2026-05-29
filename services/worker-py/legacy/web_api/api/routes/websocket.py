"""
WebSocket 路由
提供实时通信功能
"""
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from src.domain.models.auth import AuthenticatedUser
from src.services.auth_service import AUTH_SESSION_COOKIE, get_user_by_session_sync


router = APIRouter()
GLOBAL_TENANT_SCOPE = "__global__"

# 全局 WebSocket 连接管理
active_connections: Dict[WebSocket, AuthenticatedUser] = {}


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
):
    """WebSocket 端点"""
    session_token = websocket.cookies.get(AUTH_SESSION_COOKIE)
    current_user = (
        get_user_by_session_sync(session_token)
        if session_token
        else None
    )
    if current_user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    if current_user.role == "tenant" and not current_user.workspace_enabled:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 接受连接
    await websocket.accept()
    active_connections[websocket] = current_user

    try:
        # 保持连接并接收消息
        while True:
            # 接收客户端消息（如果有的话）
            data = await websocket.receive_text()
            # 这里可以处理客户端发送的消息
            # 目前我们主要用于服务端推送，所以暂时不处理
    except WebSocketDisconnect:
        active_connections.pop(websocket, None)
    except Exception as e:
        print(f"WebSocket 错误: {e}")
        active_connections.pop(websocket, None)


def _should_deliver_to_user(user: AuthenticatedUser, tenant_scope) -> bool:
    if user.role == "admin":
        return True
    if tenant_scope is None or tenant_scope == GLOBAL_TENANT_SCOPE:
        return False
    return user.tenant_id == tenant_scope


async def broadcast_message(message_type: str, data: dict, tenant_scope=None):
    """向所有连接的客户端广播消息"""
    message = {
        "type": message_type,
        "data": data
    }

    # 移除已断开的连接
    disconnected = set()

    for connection, user in tuple(active_connections.items()):
        if not _should_deliver_to_user(user, tenant_scope):
            continue
        try:
            await connection.send_json(message)
        except Exception:
            disconnected.add(connection)

    # 清理断开的连接
    for connection in disconnected:
        active_connections.pop(connection, None)
