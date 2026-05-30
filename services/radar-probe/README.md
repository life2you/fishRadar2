# worker-py

`worker-py` 是 `fishRadar2` 中负责抓取与 AI 执行的 Python 服务。

## 职责

- 闲鱼页面抓取
- 商品图片下载
- AI 文本/图片分析
- 结果写库
- 任务执行与失败保护

## 当前状态

当前目录已经被收口为执行服务主仓，不再承担默认控制面职责。

当前默认入口已经调整为执行服务模式：

- `tools/worker_job_runner.py`：数据库任务队列消费者
- `src/app.py`：最小健康检查壳，不再挂管理员/租户 API
- `legacy/web_api/`：迁移过渡期保留的旧 Python Web/API 实现与历史测试
- `Dockerfile`：新的 worker 容器入口，默认直接运行 `worker_job_runner.py`
- `start.sh`：本地 worker 启动脚本，默认直接启动 `worker_job_runner.py`

当前队列运行模式：

- `QUEUE_BACKEND=mysql`：纯数据库轮询
- `QUEUE_BACKEND=redis`：MySQL 保留元数据，Redis 负责实时投递；worker 取不到 Redis 消息时会回退到 MySQL 轮询

## 当前建议

生产部署时：

1. 不使用 `legacy/web_api`
2. 只运行 `worker_job_runner.py`
3. 通过 `api-go + Redis + MySQL` 协调任务与实时事件
