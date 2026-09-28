# 当前状态：R4C M2-R1 本地修复与验证完成，远端复审待进行（2026-09-28）

## 当前阶段

- R4B 本地接受与 M0 技术门禁已通过；R4C M1 的引擎/方言选择已由远端接受，CZSC `1.0.1` + `r4c-observed-revision-v1` 仍保持禁用。
- 首个 M2 提交 `ac8e3ea3fc251d74c7d88e82550ae88cfb3d14ff` 已推送；远端迭代 56 保留 CZSC + observed-revision 路线，但判定 `CHANGES_REQUIRED`。M2-R1 已修复同 ID 冲突证据丢弃、回放流缺少配置/引擎命名空间，以及禁用配置中的过期 blocker 文案。
- M2-R1 修复提交 `73a23cb50004bea7c2994a8a0838beced812b64d` 已推送到原隔离分支，基于首个 M2 提交 `ac8e3ea3fc251d74c7d88e82550ae88cfb3d14ff`。Windows/Linux 各 25 项专项测试通过；300-bar 摘要跨平台一致，M2 与 R5.2.1 身份/碰撞/资源回归均通过。详细证据见 [R4C M2 acceptance](docs/audits/R4C_M2_ADAPTER_ACCEPTANCE_20260928.md)。
- 当前状态为 `M2_R1_IMPLEMENTED_TESTED_PENDING_REMOTE_RE_REVIEW`。下一步发送迭代 57 的执行收据并等待远端复审；M3 仍关闭，只有远端确认 M2 PASS 并给出下一阶段计划后才继续。
- 这是阶段间交接，不是项目收尾或等待人工验收。产品最终验收仍在后续阶段；远端计划、本地执行、测试、GitHub、远端复核的循环继续。

生产没有部署或修改；真实数据资格仍为 **UNKNOWN**，`actionable=false`，canonical action 未改变。M2-R1 未添加数据库、任务/worker、API、前端、Provider 或自动交易路径。

---

# 历史状态快照：R4B 本地接受完成，C2D 文档对账（2026-09-28）

## 生产身份（保持不变）

公网生产仍运行应用 SHA `0dbd3fee58a3f5e080aacbcd8eae8d5964aec54f`、tree `f8607b3de8decde6065ccc559c5c26b0262b8e6b`，镜像 `sha256:251a0623c694b07525bd398b52f41eecc17ec3d1216912c6d593b704fc8ae81a`，Alembic head `e609200001`。本轮没有合并、部署、生产数据库写入或 Provider 请求。

## 接受的本地工程身份

R2–R4B 已在独立 worktree 通过远端 ChatGPT 独立审查与最终平台门禁。最终应用候选为 SHA `43bfbf6929a70f520c216b759edbaa433e920e91`、tree `12d217af3edbe34c67bc36e75b4395ab4917b001`，候选迁移 head `g8b9c0d1e2f3`。最终 JUnit 为 1279 tests、0 failures、0 errors、15 条件跳过；SQLite 与隔离 PostgreSQL 16 migration/roundtrip 通过，compileall、Node、相关 Ruff、secret scan、diff check 通过。权威收据见 [R4B final acceptance](docs/audits/R4B_FINAL_ACCEPTANCE_20260928.md) 和 [R2–R4B reconciliation](docs/audits/R2_R4B_RECONCILIATION_20260927.md)。

当前阶段：`R4B=ACCEPTED_LOCAL`，`M0_TECHNICAL_GATE=PASS`，`M0_FINAL_STATUS=PENDING_C2D_RECONCILIATION`。C2D 只对账文档与收据，R4C 尚未开始。真实数据资格保持 **UNKNOWN**，`actionable=false`，canonical action 未改变。

## 下一步

完成 C2D 文档对账并交远端独立审查；审查通过后才进入 R4C M1 引擎/方言资格。接受的本地候选不等于生产部署身份。

---
# 当前状态：R4B 日线结构本地实现与验收完成（2026-09-27）

R4B 在隔离分支 `codex/r4b-price-structure` 完成：分型/平台按右侧两根确认；独立触碰和方法贡献分开；实测 Wilder ATR14 代替收盘价 2% 估算；日线箱体增加证据哈希、状态回放、结算日/盘中临时状态分离，并绑定研究价格口径。现有支撑压力快照方法版本为 `support-resistance-v4-structure`（满足既有 PostgreSQL `VARCHAR(32)`），图表合同升级到 `chart-read-v1.2.0`；无数据库迁移，箱体不接入 canonical decision，`actionable=false`。

最终应用提交 `8a5b575904c4cbc5a2d63e53a8521076c80904e1`，tree `1fc3d4657dba7f9e0f0ec5d06875eaaa45c98d83`。后端全量 pytest：1269 项，1255 通过、14 条件跳过、0 失败/错误；前端 Vitest 63/63、普通/认证/响应式浏览器 26/5/18 通过；typecheck、构建、compileall、Node 39/39、安全扫描通过。收据与证据路径见 [R4B验收收据](docs/09-RPT-R4B箱体与支撑压力验收.md) 和[逐页状态矩阵](docs/10-TST-R4B逐页状态验收矩阵.md)。

代码仅在本地隔离分支，尚未推送、CI、合并 main 或部署。main 当前工作副本仍在 `c63f669095e6eb44e1e9c185deecf0f7af02b27c`；真实行情资格 **UNKNOWN**，生产未重新检查。本地 Mock/合成数据验收不授予真实资格。下一步为核对远端状态并走发布门禁，发布后再进入 R4C。

## 上一阶段：R2–R4A 本地实现（2026-09-26）

本地隔离分支 `codex/r2-freshness-lifecycle` 从 `main` 基线 `c63f669095e6eb44e1e9c185deecf0f7af02b27c` 完成详情/图表同读时、模块级可用性、决策变化说明和原始/拆分调整研究序列分离。应用提交 `8b52d39d22ebb21a41e269ab9ce9863b85dd3b83`（tree `d7ce9c857f48a99e130cf6060700974213c4e9c0`），补充前端状态回归提交 `f4286d590fd6f9565192754e40c553048286823d`。最终本机全量 pytest 为 1250 项，1236 通过、14 条件跳过、0 失败/错误；前端 62/62、普通/认证/响应式浏览器 20/20、5/5、18/18 通过。详情见 [R2–R4A 实现收据](docs/R2_R3_R4A_IMPLEMENTATION_RECEIPT_20260926.md) 与[路由矩阵](docs/ROUTE_ACCEPTANCE_R2_R4A_20260926.md)。

本阶段只提交到本地隔离分支；`main` 未改变，未推送、合并或部署。真实行情资格仍为 **UNKNOWN**；没有请求生产 Provider、修改原始 OHLCV/认证、生产数据库或提升 `actionable`。生产最后一次身份记录见下方 2026-09-23 收据段，本阶段没有重新查询生产。

复权序列、决策读模型及支撑压力版本已升级；部署后旧衍生快照将 fail-closed，需经现有受审计刷新链重算后再作为当前数据展示。本次未新增数据库迁移。

## 上一份主线/生产收据（2026-09-23）

公网生产已运行主线应用 SHA `0dbd3fee58a3f5e080aacbcd8eae8d5964aec54f`、tree `f8607b3de8decde6065ccc559c5c26b0262b8e6b`，镜像 ID `sha256:251a0623c694b07525bd398b52f41eecc17ec3d1216912c6d593b704fc8ae81a`。API/worker/scheduler 同一镜像，只有 reports/backups 持久目录挂载；Alembic 为 `e609200001`。GitHub CI 通过后以 smoke-tested OCI 工件在生产加载，部署和备份细节见[生产收据](docs/PRODUCTION_DEPLOYMENT_RECEIPT_AU_20260923.md)。

应用/前端包版本为 `1.0.5`；生产 Compose 配置的 `APP_VERSION` 与公开 health 显示 `1.0.8`，两者口径不同，不能用 health 版本替代源码身份。R1 单位证据绑定及 A-U1–A-U3 账户、个人中心和指标菜单已进入主线并部署。账户关闭只停用登录、保留资料；邮箱/短信/微信验证、找回和永久删除没有实现。

真实数据资格为 **UNKNOWN**：本次没有访问生产业务表、重算认证或触发行情 Provider。行情认证、完整回报、PIT/OOS、预测校准和 actionable 继续受原有证据门禁约束；HTTP 健康、镜像 smoke 与页面显示不改变这些结论。未完成主线依次为 R2 更新及时性、R3 详情空态和决策解释、R4 研究基准/支撑压力/完整缠论、R5 真人本地 Codex、R6 另行授权的真实数据与发布流程。

## 2026-09-20 历史状态快照（不覆盖本页当前结论）

企业行为研究修复基线是 `172db210e3e7e4daa252bdd2746466f79e5da595`。该版本已把四只 ETF 的官方份额拆分只应用于内存研究序列，保留原始展示日线，并修复 stale 重算、信号恢复和任务状态传播。此段只记录当时状态；当前生产镜像、源码和挂载以本页顶部最新收据为准。

绝对量额独立认证合同、公司行动展示/研究序列分离、14:30 PIT/OOS 闸门、实时时间戳 operational-grade 检查和 Codex `live_ready=false` 均已进入主线。这些是失败关闭门禁，**不是**生产数据合格证明。

## 必须纠正的旧结论

旧文档的“新浪 v102 量额恢复即资格通过”不成立。均价比值不能认证绝对单位。512000、512480、515880、588200 的价格断点已与官方份额拆分对账，但公告只支持研究序列连续化，不认证原始成交量、成交额或完整总收益。

## 2026-09-20 应用版本快照（历史）

应用/前端版本统一 1.0.5；数据契约 cn-fund-shares-cny-v1.0.4-corporate-action-research，特征 feature-store-v0.7.3-input-mask，指标 ind-v0.7.3-audit，预测 similarity-corridor-v0.7.3-audit，策略 signal-v0.7.2-qualification-audit。迁移 head 保持 d40609090002。官方拆分事件只生成独立内存研究序列，原始展示日线不改；旧快照不能只改版本字段冒充重算。

累计修复覆盖新浪资格冻结、价格断点拒绝、量额缺失 mask、全输入哈希、同版本前值、统一结算目标、partial/failed 传播、衍生任务恢复、指数盘后任务、跨进程流水线锁、14:30交易日/未来报价门禁、子进程独立登录、NTFS ACL、无效产物终态、不重复付费以及发布 manifest。

只读诊断 `scripts/audit_research_inputs.py` 保留。FTShare 资格脚本已改为失败关闭：接口有记录不再等于 qualified，必须同时具有独立绝对单位证据和 operational-grade 时间证据。2026-09-20 对五只 ETF 的 bounded probe 全部返回 CapabilityUnavailable，因此 FTShare 仍不得进入生产回退链。

## 2026-09-20 资格快照（当前资格需按新证据重新确认）

35 只标的的独立绝对单位认证、完整公司行动/复权总收益序列、真实 14:30 历史回测与前瞻观察、本人 Codex 登录/付费响应/端到端公网回传仍未完成。生产研究板可以展示 stale 研究结果，但 `actionable` 保持 false。下一主线任务是在可用的第二行情源恢复后完成同日量额对账；在此之前不启动预测校准。

[逐项关闭矩阵](docs/audits/CLOSURE_20260913.md) · [版本记录](docs/versions/V1.0.5.md) · [交接](HANDOFF.md)。最后测试收据与固定应用SHA由 docs/audits 下的最终验收文件补充。

[FTShare 现场资格收据](docs/audits/FTSHARE_QUALIFICATION_20260920.md) · [原状态完整归档](docs/archive/pre-audit-close-20260913/STATUS.md)。
