# legacy web_api

这里保留的是从旧单体仓库迁移过来的 Python 控制面实现，作为过渡期参考代码。

当前 `fishRadar2` 的默认方向是：

- `services/api-go` 承接控制面与业务 API
- `services/worker-py` 只保留执行链与 bridge

因此这部分代码：

- 不再属于默认运行入口
- 不再属于主测试集
- 仅用于迁移对照、行为回归参考和必要时的历史兼容排查

如果需要显式运行这套历史实现，请从：

- `legacy/web_api/app.py`

启动，而不是使用 `src/app.py`。
