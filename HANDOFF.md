# 交接说明

## 目标

把当前 0.4.0 工程部署到用户已有的阿里云 ECS，接入用户的 Tushare Token 和 OpenAI-compatible 模型，先运行 ETF/LOF 私有研究版，再逐步完成真实数据校准。

## Codex 接手前必须阅读

1. `AGENTS.md`
2. `STATUS.md`
3. `CODEX_DEPLOYMENT_TASKS.md`
4. `docs/ALIYUN_DEPLOYMENT.md`
5. `docs/STRATEGY_AND_VALIDATION.md`
6. `vendor/manifest.json`

## 不可假设

- 不可假设 Tushare 某接口一定有权限。
- 不可假设 AKShare 在阿里云 IP 上稳定。
- 不可把日线最后收盘价伪装为实时行情。
- 不可把 `not_calibrated` 改成 `calibrated`，除非验证产物和人工封版记录齐全。
- 不可因用户是个人私用而忽略上游许可证、署名或服务条款。
- 不可从第三方仓库复制任何 Token、Cookie、内网 IP、账户号或券商配置。

## 环境输入

部署人员需要用户提供或在服务器本地填写：

- ECS 操作系统与架构；
- 域名或仅 SSH 隧道访问；
- Tushare Token；
- OpenAI-compatible Base URL、API Key、模型名和 API 模式；
- 最终 ETF/LOF 自选池；
- 是否自建 RSSHub，以及 RSS 路由；
- 备份保留期限和异地备份目的地。

所有密钥仅写服务器 `.env`，权限 `0600`。不得通过聊天、日志、PR 或截图回传。

## 建议的上线顺序

1. 在本地或临时 ECS 使用 Mock 验证页面。
2. 关闭 scheduler，只启动 PostgreSQL/API。
3. 运行 provider smoke，记录每个接口的返回字段、权限和耗时。
4. 拉取 900 天日线，核验随机 5 只基金的 OHLCV。
5. 执行指标、预测、信号和报告。
6. 开启 scheduler，观察至少一个完整交易日。
7. 再启用 LLM 新闻结构化。
8. 执行 `validate_forecasts` 与 `backtest_rotation`，再用真实数据补足停牌/涨跌停/LOF 溢价和第二引擎对账，之后才讨论阈值调整。

## 数据库

- 生产数据库：PostgreSQL 16。
- 迁移：API 启动前执行 `alembic upgrade head`。
- PostgreSQL 不开放宿主机端口。
- 每日使用 `scripts/backup_postgres.sh`，备份包含 `--clean --if-exists`。
- 恢复前先在隔离实例验证备份文件 SHA-256 和可恢复性。

## 运行时

- API：`127.0.0.1:8080`。
- scheduler：每 30 秒检查一次是否到期，不等于每 30 秒调用数据源。
- 行情默认 3 分钟。
- 信号默认 15 分钟，可在网页改为 10～15 分钟。
- 普通新闻 30 分钟，午间 10 分钟。
- PostgreSQL advisory lock 防止手工任务与 scheduler 重叠。

## 报告验收

每份报告应能够追溯：

- 数据源和更新时间；
- 是否实时/退化/Mock；
- 指标、预测和策略版本；
- 输入哈希；
- 新闻事实与推断的分离；
- 信号过期时间；
- 预测校准状态；
- 回测决策日、次日执行日、费用、滑点、整手约束和是否含 Mock 数据。
