# api-go

这是 `fishRadar2` 的 Go API 服务。

第一阶段目标：

- 提供基础健康检查
- 提供服务元信息接口
- 搭建后续迁移的目录结构
- 接入第一批管理类业务接口

当前运行定位：

- 控制面与查询面主服务
- 默认监听 `8080`
- 通过 `worker_jobs` + `Redis` 向 `worker-py` 投递执行请求

## 当前已实现接口

- `GET /health`
- `GET /api/v1/health`
- `GET /api/v1/meta/services`
- `POST /auth/login`
- `POST /auth/status`
- `GET /auth/me`
- `POST /auth/logout`
- `GET /api/announcements`
- `GET /api/announcements/active`
- `POST /api/announcements`
- `PATCH /api/announcements/{id}`
- `DELETE /api/announcements/{id}`
- `GET /api/dashboard/summary`
- `GET /api/settings/status`
- `GET /api/settings/tenant-notification-channels`
- `PUT /api/settings/tenant-notification-channels`
- `GET /api/settings/rotation`
- `PUT /api/settings/rotation`
- `GET /api/settings/ai-runtime`
- `PUT /api/settings/ai-runtime`
- `GET /api/settings/failure-guard`
- `PUT /api/settings/failure-guard`
- `GET /api/settings/ai-accounts`
- `POST /api/settings/ai-accounts`
- `PATCH /api/settings/ai-accounts/{id}`
- `DELETE /api/settings/ai-accounts/{id}`
- `GET /api/settings/tenants`
- `GET /api/settings/tenants/{id}`
- `PATCH /api/settings/tenants/{id}`
- `GET /api/tasks`
- `GET /api/tasks/{id}`
- `GET /api/results/files`
- `GET /api/results/files/{filename}`
- `DELETE /api/results/files/{filename}`
- `GET /api/results/{filename}`
- `GET /api/results/{filename}/insights`
- `GET /api/results/{filename}/export`
- `GET /api/results/{filename}/blacklist-rules`
- `PUT /api/results/{filename}/blacklist-rules`
- `PATCH /api/results/{filename}/items/{itemId}/status`

## 本地运行

```bash
cd services/api-go
APP_DATABASE_URL='mysql://user:pass@127.0.0.1:3306/fishradar?charset=utf8mb4' \
go run ./cmd/server
```

如果要启用 Redis 投递：

```bash
QUEUE_BACKEND=redis \
REDIS_URL='redis://127.0.0.1:6379/0' \
REDIS_QUEUE_NAME='fishradar2:worker_jobs' \
go run ./cmd/server
```
