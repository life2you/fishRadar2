"""
新架构的主应用入口
整合所有路由和服务
"""
from contextlib import asynccontextmanager
import os
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response

LEGACY_ROOT = Path(__file__).resolve().parent
WORKER_ROOT = LEGACY_ROOT.parents[1]
for candidate in (LEGACY_ROOT, WORKER_ROOT):
    text_path = str(candidate)
    if text_path not in sys.path:
        sys.path.insert(0, text_path)

from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.routes import (
    dashboard,
    tasks,
    logs,
    settings,
    announcements,
    tenant_settings,
    prompts,
    results,
    login_state,
    websocket,
    accounts,
)
from api.dependencies import (
    get_current_user,
    require_admin_user,
    set_process_service,
    set_scheduler_service,
    set_task_generation_service,
)
from src.domain.models.auth import AuthenticatedUser
from src.services.task_service import TaskService
from src.services.process_service import ProcessService
from src.services.scheduler_service import SchedulerService
from src.services.task_log_cleanup_service import cleanup_task_logs
from src.services.task_generation_service import TaskGenerationService
from src.services.login_rate_limiter import LoginRateLimiter
from src.services.auth_service import (
    AUTH_SESSION_COOKIE,
    SESSION_TTL_DAYS,
    authenticate_credentials,
    create_session,
    delete_session,
    redeem_activation_code,
    register_tenant_user,
)
from src.infrastructure.persistence.mysql_bootstrap import bootstrap_mysql_storage
from src.infrastructure.persistence.mysql_task_repository import MySQLTaskRepository
from src.infrastructure.config.settings import settings as app_settings


# 全局服务实例
process_service = ProcessService()
scheduler_service = SchedulerService(process_service)
task_generation_service = TaskGenerationService()
login_rate_limiter = LoginRateLimiter(
    max_attempts=app_settings.login_rate_limit_max_attempts,
    window_seconds=app_settings.login_rate_limit_window_seconds,
    block_seconds=app_settings.login_rate_limit_block_seconds,
)


async def _sync_task_runtime_status(task_id: int, is_running: bool) -> None:
    task_service = TaskService(MySQLTaskRepository())
    task = await task_service.get_task(task_id)
    if not task or task.is_running == is_running:
        return
    await task_service.update_task_status(task_id, is_running)
    await websocket.broadcast_message(
        "task_status_changed",
        {"id": task_id, "is_running": is_running},
        tenant_scope=task.tenant_id,
    )


process_service.set_lifecycle_hooks(
    on_started=lambda task_id: _sync_task_runtime_status(task_id, True),
    on_stopped=lambda task_id: _sync_task_runtime_status(task_id, False),
)

# 设置全局 ProcessService 实例供依赖注入使用
set_process_service(process_service)
set_scheduler_service(scheduler_service)
set_task_generation_service(task_generation_service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("正在启动应用...")
    bootstrap_mysql_storage()
    cleanup_task_logs(keep_days=app_settings.task_log_retention_days)

    # 重置所有任务状态为停止
    task_repo = MySQLTaskRepository()
    task_service = TaskService(task_repo)
    tasks_list = await task_service.get_all_tasks()
    manual_task_ids_to_restore = process_service.consume_manual_restart_task_ids()

    for task in tasks_list:
        if task.is_running:
            await task_service.update_task_status(task.id, False)

    # 加载定时任务
    await scheduler_service.reload_jobs(tasks_list)
    scheduler_service.start()
    process_service.start_background_tasks()
    if manual_task_ids_to_restore:
        restored_task_ids = await process_service.restore_manual_tasks(manual_task_ids_to_restore)
        if restored_task_ids:
            print(f"已恢复手动任务: {restored_task_ids}")

    print("应用启动完成")

    yield

    # 关闭时
    print("正在关闭应用...")
    process_service.snapshot_manual_tasks_for_restart()
    scheduler_service.stop()
    await process_service.stop_background_tasks()
    await process_service.stop_all()
    print("应用已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="闲鱼智能监控机器人",
    description="基于AI的闲鱼商品监控系统",
    version="2.0.0",
    lifespan=lifespan
)

# 注册路由
app.include_router(tasks.router)
app.include_router(
    dashboard.router,
    dependencies=[Depends(require_admin_user)],
)
app.include_router(
    logs.router,
    dependencies=[Depends(require_admin_user)],
)
app.include_router(
    settings.router,
    dependencies=[Depends(require_admin_user)],
)
app.include_router(announcements.router)
app.include_router(tenant_settings.router)
app.include_router(
    prompts.router,
    dependencies=[Depends(require_admin_user)],
)
app.include_router(results.router)
app.include_router(
    login_state.router,
    dependencies=[Depends(require_admin_user)],
)
app.include_router(websocket.router)
app.include_router(
    accounts.router,
    dependencies=[Depends(require_admin_user)],
)

# 挂载静态文件
# 旧的静态文件目录（用于截图等）
app.mount("/static", StaticFiles(directory="static"), name="static")

# 挂载 Vue 3 前端构建产物
# 注意：需要在所有 API 路由之后挂载，以避免覆盖 API 路由
if os.path.exists("dist"):
    app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")


# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查（无需认证）"""
    return {"status": "healthy", "message": "服务正常运行"}


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    tenant_name: str
    display_name: str | None = None


class ActivationRequest(BaseModel):
    code: str


def _auth_payload(user: AuthenticatedUser) -> dict:
    return {
        "authenticated": True,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "tenant_name": user.tenant_name,
        "tenant_status": user.tenant_status,
        "workspace_enabled": user.workspace_enabled,
        "tenant_ai_enabled": user.tenant_ai_enabled,
        "tenant_activation_required": user.tenant_activation_required,
        "tenant_activated": user.activated,
        "tenant_activated_at": user.tenant_activated_at,
        "tenant_access_expires_at": user.tenant_access_expires_at,
        "tenant_access_expired": user.access_expired,
        "can_use_ai": user.can_use_ai,
        "allowed_routes": user.allowed_routes,
    }


def _set_auth_cookie(response: Response, session_token: str) -> None:
    response.set_cookie(
        key=AUTH_SESSION_COOKIE,
        value=session_token,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=app_settings.cookie_secure_enabled,
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_SESSION_COOKIE,
        httponly=True,
        samesite="lax",
        secure=app_settings.cookie_secure_enabled,
    )


def _resolve_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _enforce_login_rate_limit(request: Request) -> str:
    client_ip = _resolve_client_ip(request)
    decision = login_rate_limiter.evaluate(client_ip)
    if decision.blocked:
        raise HTTPException(
            status_code=429,
            detail=f"登录尝试过于频繁，请在 {decision.retry_after_seconds} 秒后重试",
        )
    return client_ip


@app.post("/auth/login")
async def login(request: Request, payload: LoginRequest, response: Response):
    """执行用户名密码登录并写入会话 Cookie。"""
    client_ip = _enforce_login_rate_limit(request)
    user = await authenticate_credentials(payload.username, payload.password)
    if user is None:
        decision = login_rate_limiter.record_failure(client_ip)
        if decision.blocked:
            raise HTTPException(
                status_code=429,
                detail=f"登录尝试过于频繁，请在 {decision.retry_after_seconds} 秒后重试",
            )
        raise HTTPException(status_code=401, detail="认证失败")
    login_rate_limiter.record_success(client_ip)
    session_token = await create_session(user)
    _set_auth_cookie(response, session_token)
    return _auth_payload(user)


@app.post("/auth/status")
async def auth_status(request: Request, payload: LoginRequest, response: Response):
    """兼容旧前端路径，等价于登录接口。"""
    return await login(request, payload, response)


@app.post("/auth/register")
async def register(payload: RegisterRequest, response: Response):
    """注册新的租户账号并自动登录到激活流程。"""
    try:
        user = await register_tenant_user(
            username=payload.username,
            password=payload.password,
            tenant_name=payload.tenant_name,
            display_name=payload.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session_token = await create_session(user)
    _set_auth_cookie(response, session_token)
    return _auth_payload(user)


@app.get("/auth/me")
async def auth_me(
    current_user: AuthenticatedUser | None = Depends(get_current_user),
):
    """返回当前登录会话的用户信息。"""
    if current_user is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return _auth_payload(current_user)


@app.post("/auth/activate")
async def activate_tenant(
    payload: ActivationRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """租户使用卡密激活当前工作台。"""
    if current_user is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    try:
        user = await redeem_activation_code(payload.code, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _auth_payload(user)


@app.post("/auth/logout")
async def logout(request: Request, response: Response):
    """退出当前会话。"""
    session_token = request.cookies.get(AUTH_SESSION_COOKIE)
    if session_token:
        await delete_session(session_token)
    _clear_auth_cookie(response)
    return {"message": "已退出登录"}


# 主页路由 - 服务 Vue 3 SPA
@app.get("/")
async def read_root(request: Request):
    """提供 Vue 3 SPA 的主页面"""
    if os.path.exists("dist/index.html"):
        return FileResponse("dist/index.html")
    else:
        return JSONResponse(
            status_code=500,
            content={"error": "前端构建产物不存在，请先运行 cd web-ui && npm run build"}
        )


# Catch-all 路由 - 处理所有前端路由（必须放在最后）
@app.get("/{full_path:path}")
async def serve_spa(request: Request, full_path: str):
    """
    Catch-all 路由，将所有非 API 请求重定向到 index.html
    这样可以支持 Vue Router 的 HTML5 History 模式
    """
    # 如果请求的是静态资源（如 favicon.ico），返回 404
    if full_path.endswith(('.ico', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.css', '.js', '.json')):
        return JSONResponse(status_code=404, content={"error": "资源未找到"})

    # 其他所有路径都返回 index.html，让前端路由处理
    if os.path.exists("dist/index.html"):
        return FileResponse("dist/index.html")
    else:
        return JSONResponse(
            status_code=500,
            content={"error": "前端构建产物不存在，请先运行 cd web-ui && npm run build"}
        )


if __name__ == "__main__":
    import uvicorn
    from src.infrastructure.config.settings import settings

    print(f"启动新架构应用，端口: {app_settings.server_port}")
    uvicorn.run(app, host="0.0.0.0", port=app_settings.server_port)
