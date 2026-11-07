# 文档地图

常用入口只保留一条主线：

| 目的 | 入口 |
| --- | --- |
| 产品与数据位置 | [README](../README.md) |
| 当前事实与验收 | [STATUS](../STATUS.md) |
| 启动/正常访问 | [QUICKSTART](../QUICKSTART.md) |
| 工程接手 | [HANDOFF](../HANDOFF.md) |
| 数据流与边界 | [ARCHITECTURE](ARCHITECTURE.md) |
| 产品下一步 | [路线](PROJECT_MASTER_ROADMAP.md) |
| 阶段证据计数 | [JSON台账](PROJECT_PROGRESS.json) · [生成视图](PROJECT_PROGRESS.md) · [维护规则](PROJECT_PROGRESS_MAINTENANCE.md) |

## 专业参考保留

- [AGENTS](../AGENTS.md)、[部署](ALIYUN_DEPLOYMENT.md)、[AI连接安全](AI_CONNECTION_SECURITY_V104.md)。
- [支撑压力语义](SUPPORT_RESISTANCE_SEMANTICS.md)、[盘中刷新](INTRADAY_REFRESH_CADENCE.md)、[14:30工作台](ETF_1430_DECISION_WORKBENCH.md)。
- [调度/恢复](contracts/LOCAL_CADENCE_V1.md)、[报价路由](contracts/QUOTE_ROUTE_DEFERRAL_V2.md)及contracts目录的其他接口合同。
- [本轮链路验收](audits/LOCAL_FIRST_CHAIN_20261023.md)及audits目录的原始发布/失败/回滚证据，按日期和固定源码理解。
- LICENSE、[第三方NOTICE](../THIRD_PARTY_LICENSES/NOTICE.md)、frontend/NOTICE和开源登记保留。

## 历史与兼容

旧方案精华已归纳到当前架构和路线；[HISTORY](HISTORY.md)提供Git恢复方式。仍被程序、测试、生成器或保留收据引用的旧路径保留，是兼容/证据入口，不是今天的新操作说明。

不删除业务代码、有效测试、私有配置、数据库、备份、回滚资产或另一AI处理的服务器资料。

## 文档分类总览（2026-11-07 归类）

全仓文档按「现行事实 → 契约语义 → 证据收据 → 计划研究 → 历史归档」五层查找；新增文档先对号入座，不再平铺到 docs/ 根目录。

| 类别 | 位置 | 内容与规则 |
| --- | --- | --- |
| 现行事实（唯一口径） | 根目录 `README.md`、`STATUS.md`、`HANDOFF.md`、`QUICKSTART.md`、`CHANGELOG.md` | 当前状态与接手入口；结论只在这里更新，别处引用不复制 |
| 契约与语义 | `docs/contracts/`（8 篇）+ 根目录 `ARCHITECTURE.md`、`*_SEMANTICS.md` | 接口/数据/展示口径；变更需同步代码与测试 |
| 审计与证据 | `docs/audits/`（99 篇） | 带日期的发布、失败、回滚、验收原始证据；只增不改，按日期+固定源码理解 |
| 发布与版本 | `docs/versions/`（13 篇）+ `CHANGELOG.md` 各版本节 | 版本专题与发布记录；应用版本四处一致由测试锁定 |
| 计划与路线 | `PROJECT_MASTER_ROADMAP.md`、`tasks/`（现行）；旧计划已归档至 `docs/archive/planning-2026-11-07/` | 未落地计划与路线；落地后把结论回写现行事实层 |
| 研究记录 | `docs/research/`、`docs/structure_v1/`、`research/` | 因子/结构研究与影子记录；研究结论不等于生产口径 |
| 交接 | `docs/handoffs/`（18 篇） | 跨 Agent/跨日交接；以最新一篇为准，旧篇仅作沿革 |
| 历史归档 | `docs/archive/`（含 pre-v103、release-v1.0.0、project-simplification-20261002 及 2026-11-07 瘦身批次 root-2026-11-07、planning-2026-11-07、superpowers-2026-08） | 已被取代的方案与旧收据；只读，不作为操作依据 |

docs/ 根目录经 2026-11-07 瘦身后保留 28 篇现行文档（另有进度台账的 .json/.html 与因子数据 .csv、资格 .json）；67 篇版本专题/验收报告/收据/旧路线图已移入 `docs/archive/root-2026-11-07/`，4 篇仍现行的契约移入 `docs/contracts/`，1 篇过期分支说明（CALC_DECISION_BRANCH.md）已删除。归档内容可由 git 历史与归档目录随时找回；瘦身执行记录见 [handoffs/CONSOLIDATION_20261107.md](handoffs/CONSOLIDATION_20261107.md) §12。
