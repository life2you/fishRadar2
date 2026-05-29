# 业务流转说明

这份文档描述 `fishRadar2` 当前可用于生产的主业务流转，重点说明：

- `web-ui`
- `api-go`
- `worker-py`
- `MySQL`
- `Redis`

之间在真实运行时如何协作。

## 1. 登录与会话

```text
浏览器 -> web-ui -> api-go(/auth/login) -> MySQL(users, auth_sessions)
```

流程：

1. 用户在 `web-ui` 提交用户名密码。
2. `api-go` 在 `users` 中校验账号与密码哈希。
3. 登录成功后，`api-go` 在 `auth_sessions` 中创建会话。
4. 浏览器收到会话 Cookie。
5. 后续 API 请求与 `/ws` WebSocket 握手都依赖这个会话 Cookie。

## 2. 页面加载与查询

```text
浏览器 -> web-ui -> api-go -> MySQL
```

适用范围：

- 管理员总览
- 任务列表
- 结果页
- 账号池
- AI 账号池
- 公告
- 通知配置
- 卡密与租户管理

这类请求全部由 `api-go` 承担，不再依赖 Python 控制面。

## 3. 创建普通任务

```text
浏览器 -> web-ui -> api-go(/api/tasks or /api/tasks/generate)
                           -> MySQL(tasks / prompt_documents / worker_jobs)
```

### 关键词模式

1. 前端直接调用 `POST /api/tasks/generate` 或 `POST /api/tasks`。
2. `api-go` 校验租户权限、AI 能力、任务字段。
3. 关键词模式会直接写入 `tasks`。
4. `api-go` 发布 `tasks_updated` 实时事件。

### AI 模式

1. 前端调用 `POST /api/tasks/generate`。
2. `api-go` 不在本进程里直接生成，而是创建 `worker_jobs(generate_task)`。
3. 作业元数据写入 MySQL。
4. 如果 `QUEUE_BACKEND=redis`，同时把作业消息推入 Redis 队列。
5. `worker-py` 消费生成作业，调用 Python bridge：
   - `tools/task_generation_bridge.py`
6. 生成完成后：
   - 新任务写入 `tasks`
   - prompt/criteria 写入数据库
   - `worker_jobs` 状态更新
   - 发布 `tasks_updated`
7. 前端通过轮询 `GET /api/tasks/generate-jobs/{jobId}` 获取步骤进度和结果。

## 4. 启动任务

```text
web-ui -> api-go(/api/tasks/start/{id})
       -> MySQL(worker_jobs)
       -> Redis(list: worker_jobs) [可选]
       -> worker-py -> spider_v2.py
```

流程：

1. 前端点击“启动任务”。
2. `api-go` 校验：
   - 租户是否可用
   - 任务是否启用
   - AI 任务是否允许当前租户使用
3. `api-go` 写入 `worker_jobs(start_task)`。
4. `worker-py/tools/worker_job_runner.py` 领取作业。
5. Worker 启动：
   - `python spider_v2.py --task-id <id>`
6. 启动成功后：
   - `tasks.is_running = 1`
   - 发布 `task_status_changed`
   - 发布 `tasks_updated`

## 5. 停止任务

```text
web-ui -> api-go(/api/tasks/stop/{id})
       -> MySQL(worker_jobs)
       -> Redis(list: worker_jobs) [可选]
       -> worker-py -> 终止 spider_v2.py
```

流程：

1. 前端点击“停止任务”。
2. `api-go` 写入 `worker_jobs(stop_task)`。
3. `worker-py` 领取作业。
4. Worker 终止对应的任务进程组。
5. 更新：
   - `tasks.is_running = 0`
   - 发布 `task_status_changed`
   - 发布 `tasks_updated`

## 6. 抓取与分析执行

```text
worker-py(spider_v2.py / scraper.py)
  -> 闲鱼
  -> 登录态
  -> 图片下载
  -> AI 账号池
  -> MySQL(result_items / price_snapshots ...)
```

执行链说明：

1. `spider_v2.py` 按任务配置读取数据库中的任务快照。
2. 使用运行时登录态文件驱动 Playwright。
3. 抓取商品列表、详情、卖家信息、评价等数据。
4. 如果任务是 AI 模式：
   - 根据 `analyze_images` 和 AI 账号能力池选择账号
   - 进行文本或图文分析
5. 结果写入 MySQL：
   - `result_items`
   - 价格快照相关表
6. 如果进程自然结束：
   - `tasks.is_running = 0`
   - 发布 `task_status_changed`
   - 发布 `tasks_updated`
   - 发布 `results_updated`

## 7. 结果页刷新

```text
worker-py / api-go -> Redis(pubsub: fishradar2:events) -> api-go(/ws) -> web-ui
```

事件类型：

- `tasks_updated`
- `task_status_changed`
- `results_updated`

广播规则：

- 管理员收到所有事件
- 租户只收到自己 `tenant_id` 范围内的事件

前端效果：

- 任务列表自动刷新
- 仪表盘摘要自动刷新
- 结果页在重分析、任务结束、结果更新后自动刷新

## 8. 结果重分析

```text
管理员 web-ui -> api-go(/api/results/{filename}/reanalyze)
             -> MySQL(worker_jobs)
             -> Redis(list) [可选]
             -> worker-py/tools/result_reanalysis_bridge.py
             -> MySQL(result_items 更新)
             -> Redis(pubsub) -> /ws -> web-ui
```

流程：

1. 管理员发起重分析。
2. `api-go` 创建 `worker_jobs(reanalyze_result)`。
3. `worker-py` 领取作业并运行重分析 bridge。
4. bridge 完成后回写结果。
5. 发布 `results_updated`。
6. 前端自动刷新结果页和总览。

## 9. 通知与公告

### 公告

```text
管理员 -> api-go(/api/announcements) -> MySQL -> web-ui
```

- 公告配置由 `api-go` 管理。
- 租户页面通过普通 API 获取生效公告。

### 测试通知

```text
web-ui -> api-go -> Python bridge -> 通知渠道
```

- 平台通知测试
- 租户通知测试
- AI 账号测试

这些工具动作仍通过 Python bridge 调用原有能力，但入口已经统一在 `api-go`。

## 10. 生产运行建议

生产环境推荐的职责拆分：

- `web-ui`
- `api-go`
- `worker-py`
- `MySQL`
- `Redis`

推荐模式：

1. `api-go` 只负责控制面和查询
2. `worker-py` 只负责执行面
3. `Redis` 同时承担：
   - 作业实时投递
   - 事件总线
4. `MySQL` 负责业务主数据与作业元数据

这就是当前 `fishRadar2` 的标准生产流转模型。

