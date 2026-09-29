# R4C 遗留修复与下一阶段实施计划

日期：2026-09-30。执行目录：`C:\Users\Admin\.codex\worktrees\etf-r4c-m1\ETF-Fund-Analysis`。
分支：`codex/r4c-pre-m4-regression-diagnostic`；修复基线：`9fe14a6b69779e602b4fd9027ea9e8e8a021adc2`。

## 目标与当前证据

先关闭 M3B-A R1 的历史公司行动因果性缺陷，再交付可读取、可解释、可部署的缠论研究功能。沿用 CZSC 1.0.1、observed-revision 路线及现有不可变持久化，不重开已接受的 M0/M1/M2/M3。

本地状态文件落后于实际远端回复：iteration 64 已审查为 CHANGES_REQUIRED；iteration 65 PLAN_UPDATE 已允许 DecisionBoard 两处截止日期修复。旧聊天 interrupted 仅反映其自身发布工作，不能证明本聊天 M0 未过或阻挡后续工程。2026-09-30 已从同一远端聊天完整 DOM 读取并核对补充方案，连接健康。

当前实质缺陷：历史图表已按 as_of 排除未来拆分，而 DecisionBoard `_derive_provisional` 和 `_row` 仍套用全部已登记事件。旧测试示例 MA20 为 1.0 对 2.0。两处转换须按 observed_at / generated_at 的上海日期截断。此修复不证明整个历史快照链已获 PIT 认证。

本地已有上一轮未提交的 corporate_action_contract、chan_input、read_model 和测试修复。全部保留并一起验收。已推送基线的全量 1297 passed / 19 skipped 只作历史对照，不能作为本次修复验收。

## A：先修复接力与状态台账

- [x] 读取 iteration 65 PLAN_UPDATE，确认两个 DecisionBoard 调用点已获得远端范围决定。
- [x] 修正 etf 自动化：从当前 checkpoint 和本工作区接续，不再等待旧 R4B 聊天结束。
- [x] 更新 STATUS、HANDOFF、todo、lessons 与审计收据，记录修复和全部本地验证结果。
- [x] 将 checkpoint 从 BLOCKED/GPT_PLAN 改为 EXECUTING，保留任务 c2c_a1d7 和 iteration 65。

验收：下次接力能定位 R1 修复与测试结果，不重复 INIT，不重做 M0。生产状态必须标明最近验证时间；旧文档中的部署 SHA 不作当前在线事实。

## B：完成 R1 两处时间截止修复

文件：`backend/app/services/decision_board_service.py`、`backend/tests/test_decision_board.py`、`backend/tests/test_v103_history.py`，连同已有 R1 三个模块及其测试。

- [x] 新增 `_row` 两事件回归：拆分前仅第一事件生效，UTC 时间进入上海次日后第二事件生效；先观察旧代码 RED。
- [x] `_row` 以 generated_at 的上海日期传入 effective_through。
- [x] `_derive_provisional` 以 observed_at 的上海日期传入 effective_through。
- [x] 原图表/DecisionBoard MA20 相等断言保留，增加拆分生效当日参数用例。
- [x] 新增固定标的测试使用独立内存数据库，避免同组合其他夹具的 UNIQUE 冲突。首次组合失败保留在执行记录中。
- [x] 所有 R1 定向测试通过后冻结代码；不改行情选择、指标公式、评级阈值、身份公式或持久化协议。

本轮结果：原来 76 passed / 1 failed 的七模块组重新运行，新增拆分当日参数后为 **78 passed / 0 failed / 0 errors**，JUnit：`E:/Claude_allow/Download/ETF_R4C_M3_20260929/r1-original-group-20260930.xml`。

后续核验更新：扩展定向组 **84 passed / 4 skipped / 0 failed / 0 errors**，228.708 秒。首轮全量完成后为 **1314 passed / 19 skipped / 2 failed / 2 errors**，两项问题追到 Chan 输入固定证券代码与 R4A 历史测试共用会话数据库导致唯一键冲突；这是测试隔离问题。保留首轮全量报告作 RED 证据。新增两个固定证券代码的 Chan 测试改用独立临时 SQLite 后，单独两项通过；下一步先重跑定向组，再对最终代码候选重跑全量。

收窄定向复验结果：84 项因果/Chan/M2/M3 组通过 80、条件跳过 4、失败 0；DecisionBoard 选定 7 项（含原临时行情计数与刷新不写日线回归、两事件 `_row`、provisional 与 refresh 路径）全部通过，213.794 秒。故意反向挑选测试顺序曾使共享 provisional 计数断言遇到前一个测试的持久行；按模块声明顺序复跑已全绿。新增 Chan 测试写库现已隔离到专用临时库。两份最终定向 JUnit 已存下载目录。Ruff、compileall、Node、diff-check 通过。

R1 定向、完整 Windows、跨平台和静态门禁均已通过。最终 Windows pytest：**1,316 passed / 19 skipped / 0 failed / 0 errors / 35 warnings**，1,335 collected，1,497.50 秒，exit 0。输出/JUnit：`E:/Claude_allow/Download/ETF_R4C_M3_20260929/r1-full-final-clean-20260930.txt` 和 `.xml`。

失败处理：定位第一个失败并记录 RED；若需要扩展到其他运行模块，先携带具体证据与远端讨论，不修改旧断言掩盖差异。回退只撤销本次具体 patch，不 reset/clean 或覆盖已有 R1 工作。

## C：R1 验证、提交与远端复核

PowerShell 从执行目录运行；解释器为 `E:/project/ETF-Fund-Analysis/.venv/Scripts/python.exe`。测试产物放 `E:/Claude_allow/Download/ETF_R4C_M3_20260929/`，不使用生产库。

```powershell
E:/project/ETF-Fund-Analysis/.venv/Scripts/python.exe -m pytest backend/tests/test_corporate_action_contract.py backend/tests/test_chan_m3b_input.py backend/tests/test_v103_history.py backend/tests/test_freshness_recovery.py backend/tests/test_chan_m2_contract.py backend/tests/test_chan_m3_persistence.py backend/tests/test_decision_board.py -q
E:/project/ETF-Fund-Analysis/.venv/Scripts/python.exe -m pytest -vv --durations=20 -o faulthandler_timeout=120 --junitxml=E:/Claude_allow/Download/ETF_R4C_M3_20260929/r1-full-20260930.xml
E:/project/ETF-Fund-Analysis/.venv/Scripts/python.exe -m compileall -q backend/app
node --check backend/app/static/app.js
git diff --check
```

- [x] 完成最小阻塞复现、对应 R1 模块及 DecisionBoard 专项；新增参数使数量变化并逐项记录。

原 77 项对应的七模块：test_audit_data_20260912.py、test_audit_history_types_20260913.py、test_chan_m3b_input.py、test_corporate_action_contract.py、test_display_qualification.py、test_freshness_recovery.py、test_v103_history.py。2026-09-30 此组已为 78/78 通过，仍需完成上面的其他门禁。
- [x] 最终候选全量 Windows pytest：记录精确汇总；保留首次 RED/JUnit。
- [x] Windows/Linux Python 3.12.14 + CZSC 1.0.1 M2 25/25 与资源/语义验证。
- [x] M2 摘要 `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac` 和 R5 history digest `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9` 跨平台一致；碰撞为 0，弱 ID 注入被检出。
- [x] Ruff、compileall、Node、密钥扫描、diff-check 通过；未改 DB/持久化，不复跑 PG16。
- [x] 更新 R1 审计收据、STATUS、HANDOFF、lessons 与任务台账，并明确该子阶段不部署。
- [ ] 定向 stage、commit、普通 git push，核对远端同分支 HEAD；代码变化后重新运行受影响门禁。
- [ ] 同一分支提交/推送准确候选，核对 GitHub head 与 SHA/tree。
- [ ] 发布本轮可读执行证据到同一 ChatGPT 项目聊天；远端复核原计划、补充方案、交接和技术路线并裁决 PASS 或 CHANGES_REQUIRED。

出口：只有本轮全套证据及远端独立 PASS 才为 `M3B_A=PASS`。当前修复为 `NOT_DEPLOYABLE_SUBSTAGE`，没有独立运行消费方，不部署整个累积未发布分支。

## D：R1 PASS 后的阶段方向（待远端逐阶段细化）

以下是依赖顺序，不代替远端下一轮文件级计划；每阶段完成后都须测试、GitHub、独立远端审查及交接。

| 阶段 | 工作范围与主要文件 | 验收出口 | 部署 |
|---|---|---|---|
| M3B-A2 周/月输入身份 | 扩展 chan_input 与输入测试，复用 candle_periods 的周期合同；冻结交易日历、完整周期、成员 bar 修订身份，历史更正仅影响所属周期 | 周/月结束边界、缺失成员、未来 bar 排除、修订传播、日/周/月口径一致；远端确认具体规则 | 不独立部署 |
| M3B-B 后台计算与发布 | 在现有 workspace worker/data-job 路径接已接受 adapter/publisher，具体文件由远端计划锁定 | 禁用状态不计算；同任务幂等、重试不重复、并发发布一致、失败保留旧 head；合成/隔离库证明 | 随 C 部署 |
| M3B-C 只读研究接口 | workspace read_model 与现有 API 路径；仅返回已发布证据，显式 disabled/missing/stale/available | GET 不调用 Provider/模型/CZSC、不入队、不写库；身份、权限、陈旧与错误态测试通过 | 第一完整后端切片，DEPLOY_REQUIRED |
| M4 图表与解释 | frontend/src/components/EtfChart.vue、frontend/src/lib/chartAdapter.ts 及其类型/测试 | 同一画布展示分型/笔/中枢及观察修订证据；未知、候选、失效可区分；移动端与登录态浏览器验证 | DEPLOY_REQUIRED |
| M5 R4C 整体验收 | 审核收据、路线文档、STATUS/HANDOFF | 精确候选全回归、线上结果与上一阶段承诺对账、未支持能力明确；远端最终复核 | 核对最终上线候选 |

R4C 后再进入已有路线 N1 新闻证据、R5 本人本地 Codex Bridge、R6 真实数据与样本外研究。不得用当前合成测试提升真实数据资格或承诺预测收益。技术分歧提交具体代码、反例和替代方案给远端讨论后记录决定。

## E：每个可部署阶段的发布门禁

1. 当次候选测试与远端审核通过，GitHub SHA/tree 确认；只读核对真实生产当前版本、镜像、Alembic、任务锁。不能根据旧聊天猜测现网版本。
2. 在生产主机之外构建不可变镜像，记录 digest 和源代码标签；保留前一镜像。
3. 新鲜备份校验 SHA/完整性/权限，恢复至隔离 PG16，执行候选升级与 smoke；空库测试不替代生产备份升级演练。
4. 演练旧镜像对新 schema 的兼容性；不兼容时必须具备已验证的镜像和数据库恢复方案。不得临时 downgrade。
5. 发布后检查 API/worker/scheduler、认证、页面/静态文件、数据库 head、只读研究接口，核对调用前后任务/证据计数无意外改变。
6. 出现候选导致的健康、权限、迁移、数据副作用失败立即按已演练方案回滚，保留失败收据；成功收据再交远端审查，之后进入下一阶段。

部署与真实数据能力启用各有证据：运行时是否启用、真实数据资格 UNKNOWN、actionable=false 分别记录。本计划不启用自动交易。

## 当前需要与接力方式

无需 Jovi 提供账号、数据或再次授权这两个已明确的修复。当前需要完成本轮测试与远端复核。若未来发布缺少登录或基础设施访问，届时提出精确的一项需求；不提前把项目挂在笼统人工验收上。

C2C 工具更新提示不是当前产品缺陷的根因；现有连接健康，工具维护与应用修复分别记录，不能借工具升级丢失 checkpoint。
