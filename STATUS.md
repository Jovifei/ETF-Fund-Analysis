# 当前工程状态：v1.0.1 数据接入修复

当前开发基线为已推送的 `codex/v1.0.0` / `9a0ca1812eda24acc390f1b3097662bfd615dfef`；核对时 main 仍是 3c7bdc7，不要再误报 v1.0.0 未提交或 main 已包含它。

应用/工作站 1.0.1；数据契约 `cn-fund-shares-cny-v1.0.1`。本轮接收在隔离分支 `codex/v1.0.1-data-access` 完成，父提交为 `9a0ca181`；尚未合并 main。原工程脏区和生产现有部署均未覆盖。

新增：Tushare 实时字段/topic/单位与分钟适配、AKShare 有界调用与诚实时间、行情/目录/新闻独立任务、只读接入状态、持久认证本地启动、Vue `/matrix` 与 `/classic/etf-board` 原版指标总表。

先读 [v1.0.0审核](docs/V100_DEPLOYMENT_AUDIT_20260907.md) → [v1.0.1记录](docs/versions/V1.0.1.md) → [数据接入/运行](docs/DATA_ACCESS_V101.md) → [验证](docs/VALIDATION_V101.md)。

本地验收：后端 812 项收集全部无失败（Windows 条件跳过 5 项），Vue 19、标准 Playwright 5、PostgreSQL 条件测试 6、Docker 镜像 smoke、ShellCheck、Compose、迁移和密钥扫描通过。公共 AKShare 探测仅日线/新闻可读，Sina 日线缺量导致两标的衍生任务诚实为 partial；Tushare Token 未读取。生产切换仍需 CI/PR、staging 恢复和维护窗口门禁。原 STATUS/HANDOFF 保留在 docs/archive/release-v1.0.0。
