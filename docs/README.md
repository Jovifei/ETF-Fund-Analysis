# 当前交付与接手（2026-10-02）

## main tip（已集成）

| 项 | 值 |
|---|---|
| Git tip | `63c426aa9954d950d397c56ad0ece6273da6f19d`（`63c426a`） |
| 集成来源 | [PR #41](https://github.com/Jovifei/ETF-Fund-Analysis/pull/41) ← R4C 分支 + [#39](https://github.com/Jovifei/ETF-Fund-Analysis/pull/39) + [#40](https://github.com/Jovifei/ETF-Fund-Analysis/pull/40) |
| Alembic head | `f0e1d2c3b4a5`（其上为 Chan 观测 `h9c0d1e2f3a4` ← SR 修订 `g8b9c0d1e2f3` …） |
| 真实数据资格 | **UNKNOWN**；`actionable=false` |

### 相对旧 docs 入口的更正

- 不再把「R4C M1 尚未开始 / R2–R4B 仅本地候选 / 生产 Alembic=`e609200001`」写成**当前**事实。那些是 2026-09-23～09-28 时段收据；R4C M3B-C 与后续 chart/flow 已进入 `main` 源码 tip。
- 生产**运行中**镜像是否已等于本 tip，仍以当日部署收据与现场检查为准（R4C M3B-C 收据绑定过 `3a13575` / Alembic `h9c0d1e2f3a4`；flow 迁移 `f0e1d2c3b4a5` 若未上线则生产 head 可能仍落后于 git tip）。

## 入口

- [当前状态](../STATUS.md)
- [当前交接](../HANDOFF.md)
- [接收入口](../START_HERE.md)
- [支撑/压力与缠论边界](SUPPORT_RESISTANCE_SEMANTICS.md)
- [数据接入与 flow_share](DATA_ACCESS_V101.md)
- [盘中刷新节奏](INTRADAY_REFRESH_CADENCE.md)
- [实现矩阵](IMPLEMENTATION_MATRIX.md)
- [R4C M3B-C 生产收据](audits/R4C_M3B_C_PRODUCTION_RELEASE_20261002.md)
- [R4C 读模型接受](audits/R4C_M3B_C_READ_MODEL_ACCEPTANCE_20261001.md)

---
# 当前交付与接手（2026-09-28）

## 生产收据与已接受本地候选

生产仍绑定 [R1 + A-U1–A-U3 production receipt](PRODUCTION_DEPLOYMENT_RECEIPT_AU_20260923.md)：SHA `0dbd3fee58a3f5e080aacbcd8eae8d5964aec54f`、tree `f8607b3de8decde6065ccc559c5c26b0262b8e6b`、Alembic `e609200001`。真实数据资格仍为 `UNKNOWN`。

R2–R4B 已完成独立本地接受，但候选尚未部署：SHA `43bfbf6929a70f520c216b759edbaa433e920e91`、tree `12d217af3edbe34c67bc36e75b4395ab4917b001`、候选 Alembic `g8b9c0d1e2f3`。完整收据：[R4B final acceptance](audits/R4B_FINAL_ACCEPTANCE_20260928.md)；阶段对账：[R2–R4B reconciliation](audits/R2_R4B_RECONCILIATION_20260927.md)；历史实现与最终 addendum：[R4B receipt](09-RPT-R4B箱体与支撑压力验收.md)。

`R4B=ACCEPTED_LOCAL`，`M0_TECHNICAL_GATE=PASS`，当前正在完成 `C2D` 文档与证据对账。生产没有使用候选 migration head，canonical action 未改变，`actionable=false`。R4C 计划已绑定该接受候选，但 R4C M1 尚未开始。

## 入口

- [当前状态](../STATUS.md)
- [当前交接](../HANDOFF.md)
- [R4B final acceptance](audits/R4B_FINAL_ACCEPTANCE_20260928.md)
- [R2–R4B reconciliation](audits/R2_R4B_RECONCILIATION_20260927.md)

---
# 文档入口：当前生产版、研究资格与本地研发（2026-09-27）

当前 main 已部署 R1 单位证据绑定与 A-U1–A-U3 账户/指标工作流。源码、镜像、备份和公网验收绑定在[生产收据](PRODUCTION_DEPLOYMENT_RECEIPT_AU_20260923.md)。应用包为1.0.5，生产 health 配置返回1.0.8；以收据的完整源码 SHA/tree 与镜像 ID识别代码，不用显示版本单独认定身份。真实数据资格仍为 UNKNOWN。

## 当前交付与接手

- [当前状态](../STATUS.md) · [当前交接](../HANDOFF.md)
- [R1 接收合同与 R2–R6 路线](CODEX_RECEIVE_R1_20260922.md)
- [登录、个人中心和指标管理合同](UI_ACCOUNT_HANDOFF_20260923.md)
- [R1 + A-U1–A-U3 生产收据](PRODUCTION_DEPLOYMENT_RECEIPT_AU_20260923.md)

## 2026-09-27 本地 R4B 箱体与结构位

日线拐点身份、ATR 口径、箱体生命周期、快照/API、图表叠加和页面状态结果见[R4B验收收据](09-RPT-R4B箱体与支撑压力验收.md)及[逐页状态矩阵](10-TST-R4B逐页状态验收矩阵.md)。应用提交绑定于 `codex/r4b-price-structure`；本地测试通过，但远端 CI、main 集成和生产部署仍待独立发布门禁。真实数据资格仍为 UNKNOWN。

## 2026-09-26 本地 R2–R4A 实现

详情/图表同一读取时点、逐模块缺数说明、研究价格基准和完整路由验收记录见[实现收据](R2_R3_R4A_IMPLEMENTATION_RECEIPT_20260926.md)与[路由验收矩阵](ROUTE_ACCEPTANCE_R2_R4A_20260926.md)。它们绑定隔离分支提交；本批没有推送、合并 main 或部署生产。真实行情资格仍为 UNKNOWN。

以下文档继续保留此前数据审计、供应商和历史版本证据；其中带日期的生产/资格数字只代表各自记录时点，不替代当前收据。

## 先读的权威文件

1. [原审核报告](CODE_AUDIT_BLOCKERS_20260912.md)：原P1/P2问题与现场证据。
2. [整改关闭矩阵](audits/CLOSURE_20260913.md)：实现、测试、未完成外部验证及每条代码位置。
3. [v1.0.5记录](versions/V1.0.5.md)：代码与策略版本、资格、回滚。
4. [当前交接](../HANDOFF.md)：账户/原数据保护、只读检查及本地验收。
5. [开源与原始资料依据](audits/REFERENCES_20260913.md)：参考设计不等于整套安装或收益证据。

固定应用提交 **c87cfa1df906eee902c1e37509c63cf847d29209**：[验收收据](audits/ACCEPTANCE_20260913.md) · [Codex本地接收与现场验证](CODEX_RECEIVE_AUDIT_20260913.md)。代码测试、来源资格、生产部署分别记账，不以旧报告替代本轮结果。

## 产品与工程知识继续保留

[知识库总览](PROJECT_KNOWLEDGE_BASE_V103.md)、[技术路径](TECHNICAL_ROUTE_V103.md)、[制造过程](PROJECT_BUILD_AND_DOCUMENTATION_V103.md)、[完成项证据分类](COMPLETION_AND_EVIDENCE_MATRIX_V103.md)、[UI/UX合同](UI_UX_CONTRACT.md)、[planning-v2](planning/WORKSPACE_PLANNING_V2.md)。其中状态数字按其记录日期理解，冲突以本轮关闭矩阵和可验证代码为准。

[用户操作](USER_GUIDE_V104.md)、[AI安全](AI_CONNECTION_SECURITY_V104.md)、[原本地验收](LOCAL_ACCEPTANCE_V104.md)、[开源登记](OPEN_SOURCE_ADOPTION_REGISTER_V103.md)、[开源落点](OSS_APPLIED_V104.md)、[历史缓存](HISTORY_STORAGE_V103.md)、[支撑压力](SUPPORT_RESISTANCE_SEMANTICS.md)、[入场离场参考](DECISION_REFERENCE_VIEWS.md)、[14:30验证](ETF_1430_VALIDATION.md)、[盘中刷新节奏](INTRADAY_REFRESH_CADENCE.md)、[本地 Codex 桥接](LOCAL_CODEX_BRIDGE.md)。原WorkBuddy模板仍在总览，同一ETF详情路径不变。

## 原文与过程不能删除

[本轮过程](AUDIT_CONTINUATION_20260913.md)、[前阶段过程](AUDIT_REPAIR_PROGRESS_20260913.md)、[原整改记录](audits/REMEDIATION_20260912.md)反映各自阶段，不是最终完成收据。

[旧文档入口完整归档](archive/pre-audit-close-20260913/docs-README.md)、[旧STATUS](archive/pre-audit-close-20260913/STATUS.md)、[旧HANDOFF](archive/pre-audit-close-20260913/HANDOFF.md)、[版本索引](versions/README.md)。原生产与本地收据仍在仓库，保留可追溯历史；“生产已通过v102单位校验”作为旧结论已被本轮审核纠正。
