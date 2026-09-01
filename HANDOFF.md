# 交接说明（发行版 0.7.0）

## 当前结论

应用/发行包版本为 `0.7.0`。本版本加入多模型分析网关、六项市场上下文和私有持仓 OCR 流程的文档/验证闭环，但不升级 `config/strategy.json` 中的策略、指标、预测或回测版本（当前策略仍含 `signal-v0.4.0`）。当前结论必须写作本地/Mock 已验证，不能写作生产就绪、实时、calibrated 或投资建议。

## 接手前阅读

1. `AGENTS.md`
2. `STATUS.md`
3. `README.md`、`QUICKSTART.md` 与 `docs/USER_GUIDE.md`
4. `CODEX_DEPLOYMENT_TASKS.md`
5. `docs/ARCHITECTURE.md`、`docs/IMPLEMENTATION_MATRIX.md`、`docs/ALIYUN_DEPLOYMENT.md`
6. `config/strategy.json`、`config/market_context.json` 和 `vendor/manifest.json`

## 分析 provider 契约

默认关闭。生产若明确启用，只配置一个 Codex/OpenAI Responses 主 provider：服务器本地 `.env` 的 `OPENAI_API_KEY`、`ANALYSIS_PRIMARY_MODEL`、`ANALYSIS_CODEX_BASE_URL`、`ANALYSIS_PRIMARY_MODE=responses`，以及 `ANALYSIS_ENABLED=true`、`ANALYSIS_CODEX_ENABLED=true`、`ANALYSIS_PRIMARY_PROVIDER=codex_openai_responses`。Anthropic Messages/DeepSeek 仅手工切换且必须成为唯一 enabled primary；失败不静默 failover。

模型无工具、无凭据/数据库/网络抓取/券商权限，不计算指标、预测、仓位或交易动作。Codex/Claude Code 只能在应用生成证据包后异步生成只读 review candidate；人工明确接受后才记录。不得从聊天、Git、报告或截图回传密钥。

## 市场上下文与 OCR

- 六项默认上下文是中国行业/板块广度、S&P 500、Nasdaq Composite、Nasdaq-100、中国半导体 ETF 代理、韩国半导体 ETF 代理。两个代理的代码默认 null，disabled/unverified，直到 Provider 资格包证明代码、覆盖、流动性、时间和字段质量。
- 今日变化是观察主字段，价格次级；Mock、unavailable、历史快照或缺失核心数据不得产生 actionable 信号。上下文刷新默认 15 分钟，scheduler 只每 30 秒检查到期。
- Pillow 是核心 OCR 校验；Paddle 仅限 Python 3.12/Linux 本地资格验证、`paddle-local-v1` manifest（路径/大小/SHA-256）和私有只读模型根。当前环境没有真实 Paddle 包/model 资格证明。Docker 镜像不安装重型 Paddle，缺模型诚实返回 503/unavailable。
- OCR 上传最大 10MiB、12,000×12,000、4,000 万像素、60 秒硬超时、15 分钟 TTL；transient root 0700、模型 root 私有只读；生产 Windows fail-closed。上传→OCR→编辑/拒绝→确认，确认前不写持仓；云复核默认关闭，仅明确同意可用且当前不出网。

## 迁移、备份与运行

生产数据库只用 PostgreSQL 16；先做可验证备份，再按以下顺序执行：

```text
158ca7025305 -> 9f1c2b3a4d5e -> a2b3c4d5e6f7 -> b3c4d5e6f7a8 -> c4d5e6f7a8b9 -> d5e6f7a8b9c0 (current head)
```

The disposable SQLite migration chain now passes `alembic upgrade head`, `current`, full `downgrade base`/re-upgrade, and `alembic check` at `d5e6f7a8b9c0`.  The audited metadata reconciliation preserves the historical review/analysis hash-check names, the opaque import-session check, and legacy nullable calibration JSON; a unique `candidate_id` constraint remains its lookup index.  Real PostgreSQL upgrade/downgrade/backup-restore evidence remains a deployment gate.

回滚只能在隔离实例验证备份 SHA-256 和可恢复性后执行 `alembic downgrade`，不得手工改生产库。API 仅映射 `127.0.0.1:8080`，PostgreSQL 不暴露宿主机端口，公网必须经 Caddy/Nginx HTTPS；反代上传上限 12MB 以覆盖 10MiB 图像和 multipart 开销。

## 尚未获得的证据

真实 Tushare/AKShare/新闻/OpenAI 端点权限和稳定性、真实 PostgreSQL 迁移/恢复、ECS/HTTPS、Paddle Python 3.12 wheel/model、上下文代理资格、真实 walk-forward/预测校准和完整交易约束仍待部署环境完成。不要把测试绿灯、Mock bootstrap 或候选报告升级为这些证据。

## 交接下一步

运行 `tasks/todo.md` 的 D3 review 命令集，记录实际版本、测试、迁移、Mock HTTP、浏览器烟测、Docker/Compose 和 secret scan 结果；最后用显式文件列表归属本轮变更，不声称拥有复制快照中的其他脏文件。

## 信号中心（v0.6.0）

- 端点：`GET /api/signals/center?coefficient=0.5~1.5&days=5~250`，返回汇总卡、机会/风险/止盈前排、信号行情曲线和板块强度；只读取层，不改写生产信号。
- 设置：`PUT /api/settings` 的 `signal_center_coefficient`（0.50–1.50，默认 1.00），存于 `runtime_settings`，无迁移需求。
- 前端：第 5 个页签"信号中心"——汇总卡、Canvas 三序列曲线、板块强度排名、前排三页签（条目可点开 K 线详情）、信号系数滑块；命中持仓的条目显示"已持有 · 注意账户影响"琥珀色提醒。
- 边界：mock provider 下 `research_only=true` 并全局告警；前排列表一律标注"研究提示，非操作指令"。

## ETF 信号分级（signal-grade-v0.1.0）

- 端点：`GET /api/signals/grade`，只读取 Indicator/Quote/Forecast 快照，派生量能/均线/MACD/KDJ/RSI/九转标签与五档；**不写 Holding、不改生产信号**。
- 前端：第 6 个页签「ETF信号分级」——五张计数卡、分组宽表（空组文案「今日无『X』标的」）、预测格强制「FORECAST · 非实际结果」。
- 标的：`config/watchlist.json` v2 行业主题池 + 标普500/纳斯达克100/黄金/黄金股；`510300.SH` 仍为门控基准。不接同花顺指数代码。
- 卡点：免费档（系统页默认）即可拉东财公开 ETF；完整档才需要 Token。Token 在系统页只写不回显，可用「测试是否连通」。规格见 `docs/superpowers/specs/2026-08-30-etf-signal-grade-design.md`。
- 决策看板现为行业/概念板块卡片（`GET /api/signals/boards`，`config/board_catalog.json`），不是东财实时板块指数。

- 使用说明：`docs/USER_GUIDE.md`。浏览器使用 `AUTH_USERNAME`（或可选 `AUTH_EMAIL`）和原始密码；服务器只保存 `AUTH_PASSWORD_HASH`（Argon2id）与 `AUTH_SESSION_SECRET`，不要发到聊天或提交 Git。`PRIVATE_ACCESS_TOKEN` 仅为旧 CLI/API 的可选 Bearer 兼容凭据，不能用于浏览器登录。

## ETF 14:30 Workbench 本地接收

本交付以完整 ZIP 覆盖包提供，不依赖此前远端空壳分支。使用 `docs/LOCAL_AGENT_PROMPT_ETF_1430.md` 覆盖到本地仓库、运行门禁、创建新分支、提交 PR 后再合并。不要把日线 Mock 结果描述成历史 14:30 策略验证。
