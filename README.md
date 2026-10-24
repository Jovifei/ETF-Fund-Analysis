# ETF / LOF 私有研究工作台

目标是网页与后续 App：真实数据留本机，定时执行确定性计算，只把有界展示结果推送到网站。当前已有 Vue 网页，独立手机 App 尚未交付。

不连接券商、不自动下单。资格保持 UNKNOWN；research_only=true、actionable=false、not_calibrated 不因页面可用或上传成功自动改变。

## 核心入口

| 内容 | 文档 |
| --- | --- |
| 当前可用情况与阻塞 | [STATUS](STATUS.md) |
| 启动与正常访问 | [QUICKSTART](QUICKSTART.md) |
| 工程接手 | [HANDOFF](HANDOFF.md) |
| 数据流与安全边界 | [架构](docs/ARCHITECTURE.md) |
| 产品下一步 | [路线](docs/PROJECT_MASTER_ROADMAP.md) |
| 专业合同、证据与历史 | [文档地图](docs/README.md) |

## 已有功能

市场总览、ETF详情、日/周/月图表、原始/研究价格切换、指标与支撑压力、板块及上下文、私有持仓和自选；本机slot/job台账、漏跑恢复、同包上传重试和有界存储。当前预测期限为 **1/3/7/20/60交易日**，提供收益区间与上涨概率，仍未校准。

## 数据与运行

- 源码根：`E:\project\ETF-Fund-Analysis`。正式任务另用固定SHA工作树，更新main不等于更换生产运行源码。
- 本机数据根：`F:\ETF_Data\ETF-Fund-Analysis`。研究库在 `db/research.sqlite3`，调度库在 `state/schedule.sqlite3`，包与回执在 `outbox`。
- Windows任务负责每天运行；Codex用于维护，LLM不算指标/仓位/回测，不执行交易。GPU不是现有确定性链路的必需条件。
- 云端保存有界展示结果及私有用户/持仓事务；不把本地研究整库同步上去。旧云端数据是否迁走以独立搬迁收据为准。
- 私有配置和凭据不读取、回显、提交或截图。文档清理不涉及数据库、配置、备份和回滚资产。

## 时间和价格口径

14:30 盘中 quote/OHLCV 可用于当时研究观察，日线、指标和预测各自保留真实日期/as-of。禁止用当前 14:30 状态直接匹配历史收盘状态冒充盘中预测。

原始价格与官方拆分调整研究价格不等价时，原始图隐藏无法映射的指标/支撑压力；研究图可保留指标。历史记录中的 **1/3/5/10 交易日**仅用于旧版本复现，不是当前期限。

## 验证和维护

依赖以pyproject.toml为准，隔离环境安装 `python -m pip install -e ".[dev]"`。常规验证：`pytest -q`、`python -m compileall -q backend/app`、`node --check backend/app/static/app.js`。

迁移检查使用 `alembic current`、`alembic check`；`alembic upgrade head`只用于已备份和获准的迁移。保留AGENTS、NOTICE、有效测试及失败证据。源码、测试、部署、网页消费和真人验收分层记账。
