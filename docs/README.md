# 文档地图

> 2026-11-07 两次整理的合并结果：① 按功能归类（现行主文档 → 合同 → 指南 → 研究 → 规划 → 交接 → 审计 → 版本 → 归档）；② V070–V106 时代的收据/过程日志/旧路线从工作区删除，git 历史可随时找回（`git log --diff-filter=D --name-only`）。

## 查找规则（新增文档先对号入座，不再平铺到 docs/ 根目录）

| 类别 | 位置 | 内容与规则 |
| --- | --- | --- |
| 现行事实（唯一口径） | 根目录 `README.md`、`STATUS.md`、`HANDOFF.md`、`QUICKSTART.md`、`CHANGELOG.md`、`OPERATIONS.md` | 当前状态与接手入口；结论只在这里更新，别处引用不复制 |
| 契约与语义 | `docs/contracts/`（15 篇）+ 根目录 `ARCHITECTURE.md`、`*_SEMANTICS.md` | 接口/数据/展示口径；变更需同步代码与测试 |
| 审计与证据 | `docs/audits/`（108 篇） | 带日期的发布、失败、回滚、验收原始证据；只增不改，按日期+固定源码理解 |
| 发布与版本 | `docs/versions/`（13 篇）+ `CHANGELOG.md` 各版本节 | 版本专题与发布记录；应用版本四处一致由测试锁定 |
| 计划与路线 | `PROJECT_MASTER_ROADMAP.md`、`docs/planning/`（5 篇）、`tasks/`（现行） | 未落地计划与路线；落地后把结论回写现行事实层 |
| 研究记录 | `docs/research/`（8 篇）、`docs/structure_v1/`（14 篇）、`research/` | 因子/结构研究与影子记录；研究结论不等于生产口径 |
| 交接 | `docs/handoffs/`（11 篇） | 跨 Agent/跨日交接；以最新一篇为准，旧篇仅作沿革 |
| 历史归档 | `docs/archive/`（34 篇：pre-v103、release-v1.0.0、project-simplification-20261002、main-3c7bdc7、planning-v1、pre-audit-close-20260913、root-2026-11-07、superpowers-2026-08） | 已被取代的方案与旧收据；只读，不作为操作依据 |

## 主线入口

| 目的 | 入口 |
| --- | --- |
| 产品与数据位置 | [README](../README.md) |
| 当前事实与验收 | [STATUS](../STATUS.md) |
| 启动/正常访问 | [QUICKSTART](../QUICKSTART.md) |
| 工程接手 | [HANDOFF](../HANDOFF.md) |
| 每次提交必须执行的步骤 + 错误记录 | [OPERATIONS](../OPERATIONS.md) |
| 数据流与边界 | [ARCHITECTURE](ARCHITECTURE.md) |
| 产品下一步 | [路线](PROJECT_MASTER_ROADMAP.md) |
| 阶段证据计数 | [JSON台账](PROJECT_PROGRESS.json) · [生成视图](PROJECT_PROGRESS.md) · [维护规则](PROJECT_PROGRESS_MAINTENANCE.md) |
| 变更/评审流程 | [PR_CHECKLIST](PR_CHECKLIST.md) |
| 用户指南 | [USER_GUIDE](USER_GUIDE.md) |

## 承重文件（程序/测试/配置引用，路径勿改）

- [14:30工作台](ETF_1430_DECISION_WORKBENCH.md)、[支撑压力语义](SUPPORT_RESISTANCE_SEMANTICS.md)、[1430 本地 Agent 提示](LOCAL_AGENT_PROMPT_ETF_1430.md) —— `backend/tests/test_etf_1430_workbench.py` 断言存在。
- [DELIVERY_P0_P4](DELIVERY_P0_P4.md) —— `config/research_styles.json` 溯源引用。
- [Bundle 身份与周末运行手册](BUNDLE_IDENTITY_AND_WEEKEND_RUNBOOK.md) —— `scripts/check_bundle_identity.py` 引用。
- [盘中刷新节奏](INTRADAY_REFRESH_CADENCE.md) —— `backend/app/services/decision_board_service.py` 注释对齐。
- [audits/DAILY_PIPELINE_A0D_ISOLATED_20261027.json](audits/DAILY_PIPELINE_A0D_ISOLATED_20261027.json)、[audits/DAILY_PIPELINE_C39_ISOLATED_20261027.json](audits/DAILY_PIPELINE_C39_ISOLATED_20261027.json) —— `config/bundle_identity_registry.json` evidence_ref。

## contracts/ —— 现行行为合同与语义规范

[FORECAST_CORRIDOR](contracts/FORECAST_CORRIDOR.md) · [UNIFIED_ETF_DECISION_ROW_BOARD](contracts/UNIFIED_ETF_DECISION_ROW_BOARD.md) · [UI_UX_CONTRACT](contracts/UI_UX_CONTRACT.md) · [DECISION_REFERENCE_VIEWS](contracts/DECISION_REFERENCE_VIEWS.md) · [ETF_1430_VALIDATION](contracts/ETF_1430_VALIDATION.md) · [PRODUCTION_DATA_ACCEPTANCE_STANDARD_V106](contracts/PRODUCTION_DATA_ACCEPTANCE_STANDARD_V106.md) · [REMOTE_LOCAL_RELAY](contracts/REMOTE_LOCAL_RELAY.md) · [STRATEGY_AND_VALIDATION](contracts/STRATEGY_AND_VALIDATION.md) · [REFERENCE_BOARD_PARITY](contracts/REFERENCE_BOARD_PARITY.md) · [RESEARCH_INTEGRATIONS](contracts/RESEARCH_INTEGRATIONS.md) · [FTSHARE_PROVIDER](contracts/FTSHARE_PROVIDER.md) · [LOCAL_CADENCE_V1](contracts/LOCAL_CADENCE_V1.md) · [LOCAL_DISPLAY_RECEIVER_SAFETY_V2_1](contracts/LOCAL_DISPLAY_RECEIVER_SAFETY_V2_1.md) · [LOCAL_PRODUCER_ADMISSION_V1](contracts/LOCAL_PRODUCER_ADMISSION_V1.md) · [QUOTE_ROUTE_DEFERRAL_V2](contracts/QUOTE_ROUTE_DEFERRAL_V2.md)

## guides/ —— 部署与运维指南

[ALIYUN_DEPLOYMENT](guides/ALIYUN_DEPLOYMENT.md) · [LOCAL_SMTP_SETUP](guides/LOCAL_SMTP_SETUP.md) · [LOCAL_WORKSPACE_DEPLOYMENT](guides/LOCAL_WORKSPACE_DEPLOYMENT.md) · [LOCAL_CODEX_BRIDGE](guides/LOCAL_CODEX_BRIDGE.md) · [HISTORY（历史精华与 Git 恢复）](guides/HISTORY.md) · [OPEN_SOURCE_ADOPTION_REGISTER_V103（开源借鉴登记册）](guides/OPEN_SOURCE_ADOPTION_REGISTER_V103.md)

## research/ 与 structure_v1/ —— 研究报告与因子/结构实证

- 研究：[ETF_MOMENTUM_VALIDATION_REPORT_20261024](research/ETF_MOMENTUM_VALIDATION_REPORT_20261024.md) · [ETF_QUANT_STRATEGY_RESEARCH_AND_INTEGRATION_20261024_V2](research/ETF_QUANT_STRATEGY_RESEARCH_AND_INTEGRATION_20261024_V2.md) · [MOMENTUM_VALIDATION_ACCEPTANCE_CHECKLIST_20261024](research/MOMENTUM_VALIDATION_ACCEPTANCE_CHECKLIST_20261024.md) · [decision_factors_catalog](research/decision_factors_catalog_20261024.md) · [decision_factors_deep_empirical](research/decision_factors_deep_empirical_20261024.md) · decision_factors_summary.csv · factor_empirical_metrics_20261024.csv · factor_empirical_metrics_audited_20261024.csv；原始工作区在 `research/calc_decision/`
- 结构研究（Stage B）：[structure_v1/README](structure_v1/README.md) · [PHASE_A_WIRING](structure_v1/PHASE_A_WIRING.md) · backtest_out/（回测报告与 proposed_weights）· shadow_20261105.json · structure_fund_row.schema.json

## planning/ —— 活跃规划与阶段计划

[SECTOR_TIMING_AFTERNOON_V1](planning/SECTOR_TIMING_AFTERNOON_V1.md) · [SECTOR_TIMING_DIGEST_HANDOFF](planning/SECTOR_TIMING_DIGEST_HANDOFF.md) · [OPEN_SOURCE_FACTOR_SHORTLIST_SECTOR_TIMING](planning/OPEN_SOURCE_FACTOR_SHORTLIST_SECTOR_TIMING.md) · [cadence-recovery-20261016](planning/cadence-recovery-20261016.md) · phase1/provider_admission.json

## handoffs/ —— 跨 AI 交接记录（跨会话继续协议）

[REMOTE_STAGE_B_20261106](handoffs/REMOTE_STAGE_B_20261106.md) · [CONSOLIDATION_20261107](handoffs/CONSOLIDATION_20261107.md) · [HANDOFF_STRUCTURE_V1](handoffs/HANDOFF_STRUCTURE_V1.md) · [REQUIREMENTS_STRUCTURE_V1](handoffs/REQUIREMENTS_STRUCTURE_V1.md) · [PHASE_A_WIRING_STRUCTURE_V1](handoffs/PHASE_A_WIRING_STRUCTURE_V1.md) · [PRODUCTION_DEPLOYMENT_20261031](handoffs/PRODUCTION_DEPLOYMENT_20261031.md) · [REMOTE_INTEGRATION_STAGE_20261024](handoffs/REMOTE_INTEGRATION_STAGE_20261024.md) · [REMOTE_LONG_STAGE_20261023](handoffs/REMOTE_LONG_STAGE_20261023.md) · [C2C_6B31_INTEGRATION_20261024](handoffs/C2C_6B31_INTEGRATION_20261024.md) · [C2C_A7F2_P2_REVIEW_20261023](handoffs/C2C_A7F2_P2_REVIEW_20261023.md) · [C2C_A7F2_TRUSTED_CONSUMPTION_20261023](handoffs/C2C_A7F2_TRUSTED_CONSUMPTION_20261023.md)

## audits/ —— 审计与发布证据（治理记录，保留）

108 篇带日期的审计/验收/回滚证据。入口示例：[LOCAL_FIRST_CHAIN_20261023](audits/LOCAL_FIRST_CHAIN_20261023.md)、[ISOLATED_WORKSPACE_REVIEW_20261028](audits/ISOLATED_WORKSPACE_REVIEW_20261028.md)、[REMOTE_STAGE_B_IMPLEMENTATION_20261106](audits/REMOTE_STAGE_B_IMPLEMENTATION_20261106.md)。**不做清理**；部分 JSON 被身份登记表引用（见上方承重文件）。指向已删 V 时代文档的历史链接有意保留原样——如需原文从 git 历史找回。

## versions/ 与 qa/

- versions/：[V1.0.0](versions/V1.0.0.md) … [V1.0.12](versions/V1.0.12.md)（13 篇）+ [README](versions/README.md)。指向已删文档的历史链接同理保留。
- [qa/PRODUCTION_FRESHNESS_V2](qa/PRODUCTION_FRESHNESS_V2.md) —— 生产新鲜度证据合同（`scripts/production_data_gate.py` 引用）。

## 专业参考

[AGENTS](../AGENTS.md) · LICENSE · [第三方NOTICE](../THIRD_PARTY_LICENSES/NOTICE.md) · frontend/NOTICE —— 保留，不删。

## 边界

不删除业务代码、有效测试、私有配置、数据库、备份、回滚资产或另一 AI 处理的服务器资料。旧文档删除不改变任何治理边界。整理沿革：[handoffs/CONSOLIDATION_20261107.md](handoffs/CONSOLIDATION_20261107.md)（归档批次）+ 本目录 git 历史（删除批次）。
