# 2026-11-06 远端大阶段输入：阶段 B 真实 PIT/OOS 与同口径策略回放

状态：Jovi 已授权本次远端在独立 `codex/` 分支内完成“审核 → 制定下一阶段 → 实现 → 测试/修复 → 自审 → 提交并推送 GitHub”的完整阶段。授权不包括合并 `main`、生产部署、修改生产配置/凭据/数据库，也不包括启用自动交易。

## 五项精简接力

1. **最终目标**：本机真实数据与确定性研究计算 → 有界、可追溯、带签名的展示包 → 云端只做认证与展示；每天约 14:30 为人工 ETF 决策提供排序、风险与动作参考。不接券商、不自动下单、不把模型输出描述成事实。总路线见 `docs/PROJECT_MASTER_ROADMAP.md`。
2. **已经完成**：v1.0.13 网站受控上线且 Reader 同代读取通过；八族策略已接入 `Indicator → SignalV05` 运行链；阶段 A 已提交 `c11f563`（tree `74fb6d6a`，基于 `main` `2dd0662`）：新增统一 `strategy_replay_contract`、研究用 `StrategyFamilyReplayBacktestService`、PIT 证据门 `evaluate_pit_evidence`、shadow 审计使用配置市场时区，并注册 `backtest_strategy_replay` 任务。阶段 A 聚焦测试 23 项通过，`compileall` 与 `node --check` 通过。
3. **现在卡在哪里**：策略资格链仍未建立：真实 5/15 分钟 PIT 数据与许可、14:30 cutoff 与第一条可成交价、新闻发布时间、purged walk-forward、纯 holdout、含 T+1/费用/滑点/涨跌停/停牌/LOF-QDII 溢价的事件回测、≥20 交易日 shadow、人工批准均无完整证据。当前 family replay 仍是 `family_selector_replay_partial`，没有回放预测/新闻/持仓状态与动作状态/目标仓位/迟滞全链。全量 pytest 在本机出现 1 项新增测试的顺序依赖失败（聚焦运行通过）和 1 项与本阶段无关的腾讯 SDK 测试失败，需要在 CI 中定论。
4. **关键文件**：`STATUS.md`、`HANDOFF.md`、`docs/PROJECT_MASTER_ROADMAP.md`、`docs/ETF_1430_VALIDATION.md`、`tasks/plans/2026-11-06-strategy-and-production-closure.md`；`backend/app/services/strategy_replay_contract.py`、`strategy_family_replay_backtest_service.py`、`strategy_engine.py`、`indicator_service.py`、`signal_v05_service.py`、`backtest_v05_service.py`、`pit_oos_harness.py`、`shadow_run_audit_service.py`；`backend/tests/test_strategy_*.py`、`test_pit_oos_harness.py`、`test_shadow_run_audit.py`；`config/strategy.json`。
5. **下一步**：见下方“本阶段任务合同”。

## 输入基线

- 分支：`codex/strategy-closure-20261106`
- 阶段 A 提交：`c11f563ceb08446f71cb7ccf0c75fb6437417b42`，tree `74fb6d6ac4893c638b5b7671eb97f1c8b24d075b`
- 基线 `main`：`2dd06627320a47ef20f46e2d02e682a26c5ea040`
- 远端开始前必须自行核对 GitHub 上该分支的最新 head；若已被推进，以新证据调整方案，不得 force-push 或整文件覆盖他人改动。

## 本阶段任务合同（一次完整大任务）

### 0. 先审核阶段 A

- 审查 `c11f563` 的改动是否最小、正确、失败关闭：contract 是否稳定、`identity_hash` 是否覆盖版本与权重、PIT 门是否只做因果检查而不冒充资格、shadow 时区修改是否影响既有测试语义。
- 定位新增测试 `test_strategy_family_replay_uses_runtime_family_contract` 在全量顺序下的失败原因并修复，不通过放宽断言掩盖。
- 修复后必须在本机/CI 同一源码上给出全量 `pytest -q` 退出码与 JUnit；腾讯 SDK 测试若为环境性既有失败，给出与基线的对照证据，不得算作本阶段通过。

### 1. 同口径策略回放（从 partial 推进）

- 让回测账本复用运行时的策略族评分、动作状态（entry/probe/reduce/hard_reduce）、目标仓位、市场门控和迟滞语义；运行时 `SignalV05Service` 与回测输出必须能用同一 `strategy_replay_contract` 对齐。
- 对同一输入做 exact replay 回归：给定固定日线切片，运行时与回放的动作序列应逐项一致；任何不可回放字段必须在报告中显式列出 `not_replayed` 原因。
- 预测、新闻、持仓状态当前无历史证据，必须保持 `not_replayed` 并阻断资格晋升，不得用日线回放冒充完整策略。

### 2. 真实 PIT/OOS 证据

- 核查 Provider Adapter 的 5/15 分钟 OHLCV/amount、source timestamp、许可与可保存范围；核查新闻发布时间与 14:30 后第一条可成交价字段。
- 建立 14:30 cutoff、horizon-aware purge、pristine holdout、版本冻结报告；报告必须记录数据区间、provider、字段口径、提交与参数 hash。
- 证据不完整时输出 `UNKNOWN` / `actionable=false` / `not_calibrated`，并逐项列出缺口；只有证据完整才可生成候选封版报告，且仍需人工批准。

### 3. 事件驱动约束回测

- 将 T+1、费用、滑点、最小交易单位、涨跌停、停牌、LOF/QDII 溢价、组合上限、主题集中度、换手迟滞纳入事件回测。
- 与上一版本、`510300.SH` 基准比较；记录数据泄漏检查与失败样例。
- 任何由 holdout 调参得来的结果必须标注为污染并作废。

### 4. Shadow 与生产验收准备（本阶段只做代码与证据，不做生产切换）

- 修正/补齐 14:30 不可变 shadow 快照生成与审计；保持每日快照不可修改、不追着结果改阈值。
- 检查生产自然链路的既有缺口：两个完整自然交易日、7–14 天观察、快槽源到接收 ≤4 分钟、正常登录与手机、SMTP/AI 真实投递；不把 CI 或 mock 当作生产验收。

## 允许与禁止

- 允许：独立 `codex/` 分支内的后端服务、测试、配置版本字段、审计/交接文档；必要的依赖安全修补需附官方公告依据。
- 禁止：合并 `main`、生产部署、修改生产 `.env`/凭据/账户数据、直写生产数据库、删除备份与回滚资产、启用自动交易、放宽 `actionable`/`calibrated` 门禁。
- 第三方 NOTICE 与许可证保留；不复制第三方仓库凭据。

## 交付要求

- 固定 base/head SHA、tree、分支/PR 链接、改动文件清单。
- 同一源码的完整 `pytest -q`（退出码 + JUnit 摘要）、`python -m compileall -q backend/app`、`node --check backend/app/static/app.js`；前端/CI 门若改动前端则一并运行。
- 失败与 NOT_RUN 明列，不得用局部绿灯拼成整体通过。
- 最终回复给出本地接收指令：拉取分支、核对 SHA/tree、复跑哪些命令。

## 历史证据索引

- `docs/handoffs/REMOTE_INTEGRATION_STAGE_20261024.md`（远端阶段格式与验收边界）
- `docs/audits/ETF_FACTOR_EMPIRICAL_INDEPENDENT_AUDIT_20261024.md`（因子审核 `REQUIRES_CHANGES`）
- `docs/audits/DAILY_PIPELINE_CANDIDATE_20261027.md`（v1.0.13 每日链路候选证据）
