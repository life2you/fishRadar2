# 架构拆分说明

## 拆分原则

这次重构没有走“一次性全重写”，而是按职责拆分，并已落成当前生产候选架构：

- 抓取与 AI 分析继续留在 Python
- 管理、认证、任务编排、查询接口迁到 Go
- 实时通知与 WebSocket 广播也迁到 Go
- 前端继续保留 Vue 3

这样做的核心收益是：

- Web/API 不再与抓取任务抢 CPU
- Worker 可以独立扩容
- 已引入 Redis 队列与事件总线，不再依赖 Web 进程直接起子进程

## 服务职责

### services/radar-portal

负责：

- 租户端页面
- 管理员端页面
- 页面路由、状态管理、表单交互

技术栈：

- Vue 3
- Vite

### services/radar-control

负责：

- 登录认证
- 多租户与卡密
- 任务管理
- 结果查询
- 公告、通知开关、AI 账号池配置
- 任务投递与 worker 编排
- `/ws` 实时广播与事件订阅

技术栈：

- Go
- 标准库 HTTP（第一版）

### services/radar-probe

负责：

- Playwright 抓取
- 商品图片下载
- AI 分析
- 结果写库
- 任务执行与失败保护
- 任务/结果事件发布

技术栈：

- Python
- 执行链服务与 bridge
- Playwright

## 迁移顺序

### 第一阶段

- 保留 `radar-probe` 基本不动，先保证抓取链可运行
- 把前端物理迁入 `services/radar-portal`
- 创建 `radar-control` 骨架，先提供健康检查和服务元信息接口

### 第二阶段

- 将 `dashboard / settings / announcements / auth / tenant` 等管理类 API 迁入 Go
- 将 `tasks / results / accounts / prompts / activation-codes / login-state` 等前端高频接口迁入 Go
- 补齐平台通知测试、租户通知测试、AI 账号测试、日志读取等工具型接口
- 前端逐步改为优先请求 `radar-control`

### 第三阶段

- 先用数据库任务队列(`worker_jobs`)把 `radar-control` 与 `radar-probe` 解耦
- `radar-control` 改为投递任务
- `radar-probe` 改为消费任务
- 任务启动/停止与 AI 任务生成优先切到 `worker_jobs`
- 现在已补第一版 `Redis` 投递：MySQL 保存元数据，Redis 负责实时分发；worker 仍保留 MySQL 轮询回退
- 同时新增 Redis Pub/Sub 事件总线：`radar-probe` 发布实时事件，`radar-control` 订阅并通过 `/ws` 向前端广播

## 当前边界

当前仓库已经不是骨架，而是可用于生产部署准备的新主仓库；仍保留的边界主要是：

- `radar-probe/legacy/web_api` 仍保留，作为迁移参考与历史测试承载，但不属于默认运行链
- `worker_jobs` 的 MySQL 轮询仍保留为兜底，不影响 Redis 作为首选实时链路
- `deploy/docker-compose.dev.yml` 与 `deploy/docker-compose.prod.yml` 已可支撑开发和生产候选部署

如需了解真实业务链路，请直接看：

- [业务流转说明](/Users/life2you/vibeCodes/github/fishRadar2/docs/business-flow.md)
