# 收尾状态

`fishRadar2` 当前已经达到可以直接进入生产部署准备的状态。

## 已完成

- Vue 3 前端保留并对接 `api-go`
- Go 控制面承接绝大多数前端直连 API
- Python 执行链独立为 `worker-py`
- 任务启动、停止、AI 任务生成、结果重分析均已进入统一作业队列
- Redis 已承担：
  - 作业实时投递
  - 实时事件总线
- `/ws` 已在 `api-go` 实现，前端实时刷新链恢复
- 开发 / 生产 compose 骨架齐全
- CI / 镜像工作流已补齐

## 仍保留但不影响生产的部分

- `services/worker-py/legacy/web_api`
  - 仅作迁移参考和历史测试承载
  - 不属于默认运行链
  - 生产部署不依赖它

- `worker_jobs` 的 MySQL 轮询回退
  - 当前是安全兜底
  - 不阻碍生产使用
  - Redis 仍是首选实时链路

## 当前建议

如果要直接上生产，优先做：

1. 生成并固定三套镜像：
   - `api-go`
   - `worker-py`
   - `web-ui`
2. 按 `deploy/.env.prod.example` 配好：
   - `APP_DATABASE_URL`
   - `REDIS_URL`
   - 镜像地址
3. 使用：
   - `deploy/docker-compose.prod.yml`
4. 上线前做一轮 smoke：
   - 登录
   - 创建任务
   - 启动任务
   - 停止任务
   - AI 任务生成
   - 结果重分析
   - WebSocket 实时刷新

按这个标准，当前仓库已经不是“重构草稿”，而是“可部署的新主仓库”。
