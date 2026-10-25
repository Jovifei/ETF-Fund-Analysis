# 当前工程交接

2026-10-25。最终目标：真实历史与确定性研究留在本机 F 盘，网站只消费有界展示包；账户和持仓隔离云端，不自动交易。

## 当前事实

- main `23c20b6`（PR57 Head `1c1a500`，两者文件树相同），v1.0.9 已发布到统一镜像 `sha256:259181a5…`；schema `f0e1d2c3b4a5` 未变。发布、备份、测试与回滚收据：`docs/audits/RELEASE_1_0_9_20261025.md`。
- 公网健康 `ok/1.0.9/auth_enabled=true`；生产 Reader 默认 34 条、批次 `1792913919058`，报价实时声明 0。自选 6 项中 1 项有批准包历史报价、5 项缺价；不再使用云端 10-09 报价。当前持仓记录 0，Jovi 以收藏暂记所持代码，不提供份额/成本，也不自动导入。
- 已接收展示包到期只标历史，原空白与代码身份不匹配有关；临时周末重复封包任务停用。`ETF-Local-Live-Compute` 已按 Jovi 更正恢复，原触发器/参数不变、执行器换 `pythonw.exe`，17:15 自然触发退出码 0 且无弹窗；`ETF-Local-Reconcile-1630` 也换为 `pythonw.exe`，10-26 自然运行待验。药箱独立任务改由 `wscript.exe` 隐藏启动，17:24 无新终端；自动化 Chrome 实例已结束。源数据资格仍 UNKNOWN/actionable=false/not_calibrated。
- 生产 `SCHEDULER_ENABLED=false`，近 10 分钟 Provider audit 0 新事件；三服务统一新镜像、重启数 0，匿名自选 GET 为 401。正常登录/本人手机尚未验收。
- 存储核账：F 盘活跃研究库 68,962 条日线、最新 10-23；云端遗留日线 22,327 条、最新 10-09，最大决策快照表约 661 MiB。服务器展示包约 232 MiB/320 MiB 上限，PostgreSQL 卷约 1.6 GiB、项目备份约 1.56 GiB；根盘约剩 10 GiB，RAM 约 1.8 GiB、检查时可用约 452 MiB。完整分账见 `docs/audits/STORAGE_LOCATION_AND_DISK_20261025.md`；不能把本机归档算成云端内存，也不能声称云端没有旧原始数据。

## 下一顺序

1. 设计并评审 5 个收藏标的的私有报价覆盖，避免把个人持仓选择写进共享展示包；在有来源、许可、时间口径和隐私边界证据前继续明确缺价。
2. 10-26（周一）验证 16:40/17:40 晚间结算槽自然实跑、两真实交易日与 7–14 日稳定性；不把周末重封旧数据当成新市场观察。
3. Jovi 正常登录和手机复核总览、ETF 分析、自选缺价/历史标记与持仓空态；再处理云盘旧数据保留策略和 S8 资格。

保护 Owner 文件、F 盘库、私有配置、账户与回滚资产；不 reset/clean/stash、不直写生产数据库。失败按发布收据回滚。版本变更需同步 `pyproject.toml`、后端配置、前端 package/lock 和 `CHANGELOG.md`。

## 浏览器认证部署契约

生产保持 `AUTH_ENABLED=true`、持久 `DATABASE_URL`、`AUTO_CREATE_SCHEMA=false`、HTTPS `AUTH_COOKIE_SECURE=true`；首次管理员由 `auth-bootstrap-admin` 初始化，已有用户与持仓保留。不得把展示库当账户库，也不回显凭据。
