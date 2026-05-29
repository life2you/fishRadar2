"""
FastAPI 依赖注入
提供服务实例的创建和管理
"""
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from src.domain.models.auth import AuthenticatedUser
from src.services.task_service import TaskService
from src.services.notification_service import NotificationService, build_notification_service
from src.services.ai_service import AIAnalysisService
from src.services.process_service import ProcessService
from src.services.scheduler_service import SchedulerService
from src.services.task_generation_service import TaskGenerationService
from src.services.auth_service import AUTH_SESSION_COOKIE, get_user_by_session
from src.infrastructure.persistence.mysql_task_repository import MySQLTaskRepository


# 全局 ProcessService 实例（将在 app.py 中设置）
_process_service_instance = None
_scheduler_service_instance = None
_task_generation_service_instance = None


def set_process_service(service: ProcessService):
    """设置全局 ProcessService 实例"""
    global _process_service_instance
    _process_service_instance = service


def set_scheduler_service(service: SchedulerService):
    """设置全局 SchedulerService 实例"""
    global _scheduler_service_instance
    _scheduler_service_instance = service


def set_task_generation_service(service: TaskGenerationService):
    """设置全局 TaskGenerationService 实例"""
    global _task_generation_service_instance
    _task_generation_service_instance = service


# 服务依赖注入
def get_task_service() -> TaskService:
    """获取任务管理服务实例"""
    repository = MySQLTaskRepository()
    return TaskService(repository)


def get_notification_service() -> NotificationService:
    """获取通知服务实例"""
    return build_notification_service()


def get_ai_service() -> AIAnalysisService:
    """获取AI分析服务实例"""
    return AIAnalysisService()


def get_process_service() -> ProcessService:
    """获取进程管理服务实例"""
    if _process_service_instance is None:
        raise RuntimeError("ProcessService 未初始化")
    return _process_service_instance


def get_scheduler_service() -> SchedulerService:
    """获取调度服务实例"""
    if _scheduler_service_instance is None:
        raise RuntimeError("SchedulerService 未初始化")
    return _scheduler_service_instance


def get_task_generation_service() -> TaskGenerationService:
    """获取任务生成作业服务实例"""
    if _task_generation_service_instance is None:
        raise RuntimeError("TaskGenerationService 未初始化")
    return _task_generation_service_instance


async def get_current_user(
    session_token: Annotated[str | None, Cookie(alias=AUTH_SESSION_COOKIE)] = None,
) -> AuthenticatedUser | None:
    """获取当前会话用户。"""
    if not session_token:
        return None
    return await get_user_by_session(session_token)


async def require_authenticated_user(
    current_user: AuthenticatedUser | None = Depends(get_current_user),
) -> AuthenticatedUser:
    """要求当前请求已登录。"""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已过期",
        )
    return current_user


async def require_admin_user(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AuthenticatedUser:
    """要求当前用户为管理员。"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号无权访问该资源",
        )
    return current_user


async def require_workspace_user(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AuthenticatedUser:
    """要求当前用户已具备租户工作台访问权限。"""
    if current_user.role == "tenant" and not current_user.workspace_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="租户工作台尚未开通或已过期，请先使用卡密激活",
        )
    return current_user
