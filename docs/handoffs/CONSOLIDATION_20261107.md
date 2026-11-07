# 分支整合与邮件完善记录（2026-11-07）

执行：Muse（应 Jovi 指令）。分支：`muse/consolidate-20261107`（自 main `2dd06627` 切出）。立场不变：research_only=true、actionable=false、not_calibrated；不连接券商、不自动交易。

## 1. 分支审计（远端 25 条，2026-11-07 点算）

以 `origin/main` 为基准的 ahead/behind 结论：

- **真正待合并只有两条线**：
  - `feature/structure-v1-wyckoff-dow-atr`（= `review/structure-v1-from-a0d52e44`，同指 `db703a27`）：领先 main 6 提交、落后 0。本次已合并（见 §2）。
  - `codex/stage-b-pit-replay-20261106`（`7c95d54e`，PR #67 draft，含 `codex/strategy-closure-20261106` 的 2 提交）：领先 main 6 提交。2026-11-06 仍在更新、未定稿，**本次未合并**，待其定稿后另行合并。
- **内容已全部包含于 main**（ahead=0，历史分支，可由仓库所有者择机删除）：codex 的 20261023–20261031 各线（audit-completion、calc-decision-factors、daily-pipeline-*、momentum-audit-fix、pipeline-execution、receipt-reconcile、settled-fixture-clock、v109-release-receipt、watchlist-quote-source、main-consolidation-20261014）、`research/decision-momentum-validation-20261024`、两条 muse ci 修复线（已由 PR #62/#63 合入）。
- **古老分叉，原样保留不动**：`bot/local-live-phase1-closure`（2026-10-15，独有 2 提交）、`codex/local-chart-algorithm-acceptance-20261004`（独有 44 提交）、`codex/c2c-a7f2-trusted-consumption-20261023`（独有 1 提交，PR #53 draft）、`codex/review-integration-20261011`（独有 2 提交）、`docs/cadence-status-reconciliation-20261022`（独有 1 提交，PR #50 draft）。
- 开放 PR：#67（Stage B，draft）、#53（c2c，draft）、#50（docs 更正，draft）。本次未动任何 PR 的合并状态；main 未做任何变更。

## 2. 本次合并

- `muse/consolidate-20261107` = main + merge(`feature/structure-v1-wyckoff-dow-atr`)，无冲突。带入内容：structure_v1 代理（威科夫/道氏/ATR）、Phase B1 结构影子（冻结 soft_c_strict 权重并行展示，`structure_shadow_changes_grade=false`，live 分级未动）及其测试。
- 后续新代码（§3、§4）均提交在本分支；是否合回 main 由 Jovi 验收后决定。

## 3. 邮件主表完善（research/etf_structure_features/email_render/render_strategy_email.py）

背景：支撑/压力与多期限预测原本各有独立章节与图表，但「逐标的决策点」主表看不到数值，阅读需跨节对照。

- 新增模块级 helper：`levels_cell_parts(r)`（复用 `lvl_zone`/`zstr` 口径，与支撑压力章节同源：nearest_* 优先、entry/exit zone 兜底，缺失侧省略）与 `next_day_forecast(r)`（`fc_get(r, ("1",))`，含 legacy `fc1` 兼容）。
- HTML 主表新增两列：**支撑/压力**（区间值+距现价百分比，支绿压红，与既有章节配色一致）、**明日预期**（期望涨跌幅着色 + 上涨概率小字，缺失显示「当前未提供」）；分级组头 colspan 7→9。
- 纯文本版逐标的行同步追加「支撑/压力 …」「明日预期 …（上涨概率 …）」片段，仅在有数据时出现。
- 主题（theme_l1/l2）原本已在主表标的名下展示，本次未动。
- 仅展示层变更：未改任何指标公式、权重、阈值、闸门或数据字段口径，`config/strategy.json` 未动，无需策略版本升级。预测仍为未校准研究口径，主表沿用既有免责说明。
- 测试：新增 `backend/tests/test_email_render_levels.py`（7 项，先失败后通过）。注：渲染器依赖工作站侧 `market_summary` 模块（发送端提供），测试中以 stub 注入使渲染器可独立导入——这是既有约束，非本次引入。

## 4. 文档归类

- `docs/README.md` 新增「文档分类总览（2026-11-07 归类）」：五层查找口径、各目录职责与计数、docs/ 根目录 100 篇的文件族点算，并规定新文档入目录、根目录不再新增专题文档。
- 未移动、未删除任何既有文档（多处被程序/测试/收据引用，移动会断链）；归类以索引方式完成。

## 5. 阈值复核结论（2026-11-06 故障复盘）

- 2026-11-06（周五）14:30/14:45 两档未出策略：G4 报价时效闸门拦截（报价源时间冻结于 14:45:12–14:45:17，取数时已超窗）。闸门口径约 10 分钟与策略侧 `maximum_quote_age_minutes=12` 基本一致，**阈值本身没有设错，不建议放宽**（放宽等于用过期报价生成策略）；改进方向在取数节奏：时段后尽早取数并在窗口内预留一次重试（属本地调度侧事项，本次未改）。
- 五档门槛（entry 68 / probe 58 / reduce 38 / hard_reduce 28）与 board 权重为经验值、无校准证据；按 AGENTS 规则不凭单次结果调阈值，如需调整必须走 walk-forward + holdout 并升级版本。
- 结构影子阈值（0.30/0.12、置信门 0.45，soft_c_strict 冻结权重）：2026-11-06 holdout 复跑结论由 WEAK_PASS_KEEP_FROZEN 降为 **KEEP_FROZEN**（soft_c_strict 5 日胜率 50.68%，前值 62.07%，均值 −0.2344%）。Phase B2（结构信号正式参与五档分级）门槛仍未满足，**本次未晋升**；待并行样本与 holdout 重新站稳后另行标定与审批。

## 6. 链路核查结论（取数 → 本地策略 → 上传 → 网站 → 邮件）

- 五段均有 2026-11-06 实证：三档数据包均被 etf.joviluma.com 接收（bundle 号见当日巡检记录），11:40 档策略邮件正常送达；下午两档为闸门按设计拦截，非链路断裂。
- 口径澄清：仓库内 SMTP 配置仍为默认停用（见 STATUS.md），实际策略邮件由本地 Bot 通道（jovi-bot@mail.grokbot.com）发送；两条路径并存，以本地 Bot 通道为准。

## 7. 验证记录（2026-11-07）

- 定向：test_email_render_levels（7，新）+ test_structure_shadow + test_structure_v1 + test_decision_board 全过；`python -m compileall -q backend/app` 与 `node --check backend/app/static/app.js` 均通过。
- 全量：252 个测试文件分 9 批逐批跑完（单进程整跑曾被运行环境重启打断于约 19%，改分批后完成）。8 批全绿；第 8 批 2 项失败——`test_sina_quote_provider.py::test_public_composite_registers_sina_as_quote_fallback`、`test_tencent_provider.py::test_public_composite_contains_tencent_independent_candidate`（public_composite 注册在本机环境缺 sina）。已在 pristine main（`2dd06627`，独立 worktree）复跑同两文件，**失败完全一致，属既有环境依赖，非本次改动引入**；该两项在 GitHub CI 环境的历史结论为通过，待本分支 CI 复核。
- 结论：本次整合与邮件/文档改动零新增失败。

## 8. 决策记录（2026-11-07，Jovi 批准 Muse 的建议）

- **Stage B 线**：等 PR #67 定稿后再合入本集成分支，不合入其进行中的版本。
- **B2 晋升**：不晋升。结构信号维持影子并行（Phase B1），待 holdout 重新站稳后另行标定与审批。
- **main**：不动。集成分支继续承载新代码，合回 main 须经 Jovi 验收后另行决定。

## 9. 未完成 / 待决

- Stage B 线（PR #67）定稿后合并进本集成分支。
- B2 晋升：待 holdout 重新站稳 + Jovi 单独批准。
- review 分支与 feature 分支同指，合并已由本分支承接，远端删除与否由 Jovi 决定。
- 本地取数节奏优化（§5）属工作站调度侧，本次未动。


## 10. Stage B 提前合入（2026-11-07 午间，所有者新指示，取代 §8 第 1 条）

- 所有者指示：「为什么要等它定稿之后再合并？你都可以做的，不用管本地。」遂将
  `origin/codex/stage-b-pit-replay-20261106`（`7c95d54e`）以 --no-ff 合入本集成分支，
  合并提交 `079e40c`，零冲突；其新增契约测试 `backend/tests/test_strategy_replay_contract.py` 通过。
- PR #67（base=main，draft）本身未动，仍由其作者线维护；本集成分支已包含其内容。

## 11. 威科夫/道氏/ATR 正式接入决策（2026-11-07 午间，所有者新指示，取代 §8 第 2 条）

- 所有者指示：三因子「我是要求加入到我的决策当中去的，至于决策的比例是多少，那是后面再定」。
  即：接入是现在时，比例是暂定值、后续再标定。holdout 的 KEEP_FROZEN 结论约束的是冻结权重
  soft_c_strict 本身的晋升，本次不改动该权重，只新增一层有界调整。
- 实现（提交 `f0f02f1`）：新增 `backend/app/research/structure_decision.py` 纯函数
  `apply_structure_decision`，在决策板层（网站决策板与策略邮件的共同数据源）生效：
  `final_rank = clamp(base_rank + round(weight × shadow_score × 2), ±1 档)`，暂定 weight=0.5；
  结构不能单独造出「可加仓」（base 未到顶档时封顶「可入场」）或「减仓」（base 非减仓时下限「观望」）；
  硬档「减仓/数据异常」不调整；影子缺失/禁用/权重 0 时完全不改变。
- 每行新增 `grade_base`（基础五档）与 `structure_decision`（版本/权重/是否生效/前后档位/分数/理由），
  `grade_reason` 在生效时追加说明；payload 顶层带 `structure_decision` 摘要。
  `structure_shadow` 本身仍标注 `structure_shadow_changes_grade=false`（影子字典未变，消费它的是新层）。
- 版本：`config/strategy.json` 新增 `signal_grade.structure_decision` 配置块；
  顶层 version → `signal-v0.7.6-structure-decision`，`signal_grade_version` → `signal-grade-v0.3.5-structure-decision`
  （按仓库规则：权重类改动必须升级版本）。SignalGradeService.assign_grade 本身未改（纯基础档），
  板塊视图仍用基础档——调整面就是决策板这一官方出口。
- 口径修正：邮件渲染的免责声明由「仅展示，不参与五档分级」改为如实说明已参与（权重 0.5、最多一档、
  不能单独造出可加仓/减仓、比例暂定）；`PHASE_A_WIRING.md` 与 `docs/handoffs/HANDOFF_STRUCTURE_V1.md`
  已加「方向更正（2026-11-07）」注；`research_only=true / actionable=false / not_calibrated` 立场未动。
- 测试：新增 `backend/tests/test_structure_decision.py` 13 项（先失败后通过）；golden 夹具
  `flow_share_non_flow_golden.json` 补 `grade_base`/`structure_decision` 两键（样本行为硬档，档位不变）；
  决策板相关 6 个测试文件整批通过；compileall 与 node --check 通过。

## 12. 文档瘦身执行记录（2026-11-07，所有者指示）

- 盘点：docs/ 根目录原 100 篇 md（全仓 1269 个受控文件；无 .pyc/.bak/.tmp 类字面垃圾，
  「垃圾」实为过期文档与旧报告）。按「代码/测试/脚本/配置是否引用」逐篇核对引用后分类：
  - **保留现行（28 篇）**：架构、部署手册、决策工作台、预测走廊、现行语义/契约、进度台账、
    因子目录与数据文件等（清单逻辑见 docs/README.md 分类总览）；
  - **移入 contracts/（4 篇）**：CURRENT_DECISION_SOURCE_CONTRACT、SCHEDULER_RESILIENCE、
    SINGLE_DECISION_SURFACE_AND_FORECAST_SEMANTICS、REFERENCE_BOARD_PARITY——内容与现行实践仍一致；
  - **归档（68+12+4 篇）**：docs 根 67 篇 + 仓库根 VALIDATION.md → `docs/archive/root-2026-11-07/`
    （含索引 README）；docs/planning + docs/plans → `docs/archive/planning-2026-11-07/`；
    docs/superpowers → `docs/archive/superpowers-2026-08/`；
  - **删除（1 篇）**：docs/CALC_DECISION_BRANCH.md（过期分支说明，内容早已并入 main）。
  - `deployment_reports/` 虽为 2026-08 旧报告，但 scripts 的默认输出路径仍指向它，原地保留；
    `docs/audits/`（99 篇）、`docs/versions/` 为日期证据链，原样保留。
- 链接修复：FORECAST_CORRIDOR、PR_CHECKLIST、LOCAL_AGENT_PROMPT_V070、UI_UX_CONTRACT 中指向
  已归档文件的 5 处引用已改指归档路径（其中 UI_UX_CONTRACT 的「当前验收」已改标「历史验收报告」）；
  代码/测试/脚本对已归档文件零引用（已逐篇 grep 验证），移动不影响测试。
- STATUS.md 已加 2026-11-07 当前条目；HANDOFF.md 已加当前状态指针；docs/README.md 分类总览已同步
  （根目录 100→28、contracts 4→8、planning 已归档）。
- §9 更新：Stage B 合并、B2（以 §11 的有界接入形式）两项已由本节与 §10/§11 关闭；
  仍待决：集成分支合回 main（所有者验收后）、结构决策比例的正式标定、review/feature 远端分支去留。

## 13. 全量验证与 Stage B 顺带修复（2026-11-07 晚）

- 全量本地套件（258 个测试文件，10 批断点续跑，运行环境多次重启后完成）：9 批全过；
  第 8/9 批各剩 1 项失败——`test_sina_quote_provider` 与 `test_tencent_provider` 的
  public_composite 注册断言，与 §7 在 pristine main 上复现的既有环境依赖失败完全一致
  （本机 egress 环境组装不出 sina 候选），非本次改动引入，以 GitHub CI 为准。
- 全量跑出一个真 bug 并已修复（提交 `18c11fd`）：Stage B 线的
  `shadow_run_audit_service.py` 用了裸 `uuid4()` 而文件只有 `import uuid`，
  未来日期拒绝路径会抛 NameError 而非预期的 ValueError；改 `uuid.uuid4().hex`，
  `test_shadow_run_audit.py` 全文件通过。此例说明 §10 提前合入后跑全量的必要性——
  Stage B 自带测试未覆盖该路径。
- 推送后以本分支 GitHub CI（ci / workspace-ci / audit-platforms）为最终结论。
