"""
radar-probe 默认应用入口。

在 fishRadar2 中，控制面 API 已迁往 services/radar-control。
这里保留一个最小 FastAPI 应用，仅用于：
- 健康检查
- 明确告知 Python 侧的旧 Web/API 已退役

历史的 Python Web 实现已保存在 legacy/web_api/app.py 中，作为迁移过渡参考，
不再作为默认运行入口。
"""
from fastapi import FastAPI

from src.infrastructure.persistence.mysql_bootstrap import bootstrap_mysql_storage


app = FastAPI(
    title="fishRadar2 radar-probe",
    description="执行服务最小入口，管理/API 控制面已迁移到 services/radar-control。",
    version="0.1.0",
)


@app.on_event("startup")
async def startup_event() -> None:
    bootstrap_mysql_storage()


@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "healthy",
        "service": "radar-probe",
        "mode": "execution-only",
        "message": "radar-probe 仅保留执行链；控制面 API 请使用 services/radar-control。历史控制面位于 legacy/web_api。",
    }


@app.get("/")
async def root() -> dict:
    return {
        "service": "radar-probe",
        "mode": "execution-only",
        "detail": "控制面 API 已迁移到 services/radar-control。历史 Python Web 实现已隔离到 legacy/web_api/app.py。",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
