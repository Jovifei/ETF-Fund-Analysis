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

## 8. 未完成 / 待决

- Stage B 线（PR #67）定稿后合并进本集成分支。
- B2 晋升：待 holdout 重新站稳 + Jovi 单独批准。
- review 分支与 feature 分支同指，合并已由本分支承接，远端删除与否由 Jovi 决定。
- 本地取数节奏优化（§5）属工作站调度侧，本次未动。
