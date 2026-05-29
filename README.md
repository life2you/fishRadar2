# fishRadar2

`fishRadar2` 是对现有 FishRadar 的重构仓库，当前已经形成可用于生产部署准备的多服务 monorepo：

- `services/web-ui`：Vue 3 租户端与管理员端
- `services/api-go`：Go API 与控制面后端
- `services/worker-py`：Python 抓取、图片下载、AI 分析与结果回写
- 实时链路：`worker-py -> Redis Pub/Sub -> api-go /ws -> web-ui`

## 当前阶段

当前仓库已经完成第一阶段骨架和第二阶段的大部分业务迁移，已经落下去的包括：

- monorepo 目录初始化
- 现有 Vue 3 前端迁入 `services/web-ui`
- 现有 Python worker 代码迁入 `services/worker-py`
- Go API 第一版骨架创建完成并可独立测试
- Go API 已接入认证与平台管理接口：
  - 认证登录态
  - 公告
  - dashboard summary
  - 平台状态
  - AI 账号池
  - 租户权限、卡密、账号池、Prompt、登录态
  - 平台通知配置、租户通知配置、租户通知方式
  - 日志读取与日志 tail
- Go API 已接入工作台主链接口：
  - 任务列表/详情/创建/编辑/删除
  - 任务启动/停止
  - AI 任务生成作业轮询
  - 结果文件列表/结果内容/价格洞察
  - 黑名单规则、结果导出、隐藏状态更新
  - 结果重分析
- Python bridge 已接入：
  - AI 任务生成
  - AI prompt 刷新
  - 结果重分析
  - 平台/租户通知测试
  - AI 账号连通性测试
- 执行链已经开始从“Go 直接拉 Python”过渡到正式队列：
  - `api-go` 会把启动/停止请求写入 `worker_jobs`
  - AI 任务生成作业也已经改成数据库作业轮询，不再依赖 Go 进程内存态
  - 结果重分析已经改成队列执行，但对前端仍保留同步接口体验
  - `worker-py` 新增 `tools/worker_job_runner.py` 作为消费者骨架，并开始消费 `start_task / stop_task / generate_task / reanalyze_result`
  - `Redis` 已承担实时投递，MySQL 仍保留作业元数据与回退能力
  - `/ws` 已由 `api-go` 承接，前端实时刷新链恢复
- 多服务部署骨架已补齐：
  - `deploy/docker-compose.dev.yml`
  - `deploy/docker-compose.prod.yml`
  - `services/api-go/Dockerfile`
  - `services/worker-py/Dockerfile`
  - `services/web-ui` 默认反代到 `api-go:8080`
- 工程化入口已补齐：
  - `.github/workflows/ci.yml`
  - `.github/workflows/docker-images.yml`

## 当前架构

```text
web-ui (Vue 3)
    -> api-go (Go)
        -> MySQL
        -> Redis

worker-py (Python)
    -> MySQL
    -> Redis
```

## 目录结构

```text
fishRadar2/
  docs/
  deploy/
  services/
    api-go/
    web-ui/
    worker-py/
  shared/
```

## 当前进度

按“是否能作为新主仓库继续开发并进入生产部署准备”这个目标来算，当前已经处于 **可交付状态**：

- `web-ui`：已保留 Vue 3，构建通过
- `api-go`：已承接大部分前端直接依赖接口
- `worker-py`：仍保留完整执行链，但还没有完全去 Web 化；当前已开始消费数据库任务队列
- `worker-py`：默认入口已降为执行服务最小壳，旧 Python Web 实现已隔离为 legacy 参考
- `worker-py`：legacy Web/API 与对应测试已移出主执行路径，主 `src/` 已以纯执行服务为主

## 开发顺序

1. `web-ui` 只面向 `api-go`
2. `api-go` 只负责控制面、查询与作业投递
3. `worker-py` 只负责执行链与结果回写
4. `Redis + MySQL` 共同承担作业与事件协同

更多说明见：

- [架构说明](/Users/life2you/vibeCodes/github/fishRadar2/docs/architecture.md)
- [业务流转说明](/Users/life2you/vibeCodes/github/fishRadar2/docs/business-flow.md)
- [收尾状态](/Users/life2you/vibeCodes/github/fishRadar2/docs/final-status.md)
