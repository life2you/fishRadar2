# deploy

这里存放 `fishRadar2` 新架构的部署骨架。

## 当前已提供

- `docker-compose.dev.yml`
  - `mysql`
  - `redis`
  - `api-go`
  - `worker-py`
  - `web-ui`
- `.env.example`
  - 本地开发/联调用的最小环境变量示例

## 快速启动

```bash
cd deploy
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build -d
```

启动后默认访问：

- 前端：`http://127.0.0.1:8088`
- Go API：`http://127.0.0.1:8080`
- MySQL：`127.0.0.1:3307`
- Redis：`127.0.0.1:6379`

## 当前运行模型

- `api-go` 把任务写入 `worker_jobs`
- 当 `QUEUE_BACKEND=redis` 时：
  - MySQL 仍保存作业元数据
  - Redis 负责实时投递
- `REDIS_EVENT_CHANNEL` 用于：
  - `worker-py` 发布 `tasks_updated / task_status_changed / results_updated`
  - `api-go` 订阅后通过 `/ws` 广播给前端
- `worker-py` 的 `tools/worker_job_runner.py` 会优先消费 Redis 队列，取不到再回退到 MySQL 轮询

## 复用本机已有 mysql8 容器

如果本机已经有名为 `mysql8` 的 MySQL 容器，希望保留数据并直接复用：

```bash
docker network create mysql8-shared || true
docker network connect mysql8-shared mysql8 || true

cd deploy
cp .env.local-mysql.example .env
docker compose -f docker-compose.local-mysql.yml up --build -d
```

本地复用模式说明：

- 不再启动 `fishradar2-mysql`
- `api-go` / `worker-py` 直接连现有 `mysql8`
- 仍然启动：
  - `fishradar2-redis`
  - `fishradar2-api-go`
  - `fishradar2-worker-py`
  - `fishradar2-web-ui`

## 生产骨架

已提供：

- `docker-compose.prod.yml`
- `.env.prod.example`

典型步骤：

```bash
cd deploy
cp .env.prod.example .env
docker compose -f docker-compose.prod.yml up -d
```

生产 compose 约定：

- MySQL / Redis 由外部提供
- `.env.prod.example` 中的 `your-mysql-host` / `your-redis-host` 需要替换成真实地址
- `api-go` / `worker-py` / `web-ui` 使用预构建镜像
- `web-ui` 对外暴露 `80`
- `api-go` 仍保留 `8080`，便于内网调试与反代

## 需要提前准备的镜像变量

- `API_GO_IMAGE`
- `WORKER_PY_IMAGE`
- `WEB_UI_IMAGE`

## 后续还会补的

- 更正式的生产 compose
- 独立 Nginx/Ingress 方案
- Web UI / API / Worker 的发布标签策略
