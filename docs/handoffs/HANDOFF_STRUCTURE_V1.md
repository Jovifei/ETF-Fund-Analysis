# HANDOFF · structure_v1 / Phase A–B（接手包）

**As of:** 2026-11-05 Asia/Shanghai · **Owner bots:** ETF Bot（接线/邮件/现网冻结）+ Grok Bot（shadow/离线胜率）  
**Audience:** 下一个接手的 AI / 人 · 只读研究 · **非操作指令**

---

## 0. 硬约束（先读）

1. **禁止**改 live `code_sha=a0d52e44…`、**禁止**改 `CONFIG_HASH`、**禁止**动 `assign_grade` / 现网五档，除非用户书面批准且满门禁。
2. **禁止**默认使用 Cursor cloud / work-quota；先问用户。
3. 服务器上 **药箱 / 逐星 / jourvolt** 容器勿动。
4. 策略邮件必须是 **图文**（compact HTML + inline/CID 图），不要 body.txt+PNG 附件堆。
5. `actionable=false` · `research_only=true` · `calibration_status=not_calibrated` 保持。
6. Phase A 需 **满 3 个交易日平行** + holdout 站稳 + 用户再批，才谈合 live。

---

## 1. 仓库 / 分支 / 工作树

| 角色 | 路径 / 引用 |
|------|-------------|
| Live compute（勿改） | `C:\Users\Admin\.codex\worktrees\etf-live-v113-a0d52e4\ETF-Fund-Analysis` @ `a0d52e44` |
| Phase A 旁路 | `E:\worktrees\etf-phase-a-structure-v1-20261105` · 分支 `feature/structure-v1-wyckoff-dow-atr` |
| 数据根 | `F:\ETF_Data\ETF-Fund-Analysis`（`db\research.sqlite3` · `outbox\` · `config\live.json`） |
| origin/main（展示仓，≠ live SHA） | `E:\project\ETF-Fund-Analysis` @ `66b386a` |
| 远程 | `https://github.com/Jovifei/ETF-Fund-Analysis.git` |
| Box 特征原型 | `/workspace/etf_structure_features/` |
| Box 邮件渲染 | `/workspace/etf_slot/email_render/` |

**契约：** 每行可选扁平块 `structure_v1`（**不是** `research_display`）。Schema：`schemas/structure_fund_row.schema.json` / worktree `research/etf_structure_features/`。

**slim_version：** `etf-email-slim-v1.1`  
**Join：** `attach_structure_v1.py` 或 `extract_slim.py --structure-sidecar`（按 `ts_code`）。

---

## 2. 决策与测试结果（摘要）

### Phase A（展示-only）— 已接线

- 邮件 + 看板新列：威科夫 / 道氏 / ATR 桶；缺数据 → `—`。
- 看板列 **不进** `DECISION_SORTABLE`。
- Dry-run（2026-11-05）：34/34 shadow 命中；`/workspace/etf_slot/email_render/out/phase_a_dryrun_20261105/`。
- Shadow 样例：`/workspace/etf_structure_features/out/shadow_20261105.json`（亦有 `C:\Users\Admin\etf_structure_v1_shadow_20261105.json`）。
- ATR 桶规则版本：`atr_pct_fixed_v1`（low&lt;1%，mid[1%,2%)，high[2%,3.5%)，extreme≥3.5%）。
- `git diff` 对 `signal_grade_service.py`：**空**（assign_grade 未动）。

### Phase B（进行中 · 旁路）

- 用户方向：周/月尺度优先于日；Wyckoff / Dow / ATR **要进决策因子**且权重 **高于 MACD**；问过 MACD 21 日。
- **现网 MACD = 12/26/9**（`strategy.json` → `indicator.macd`）；**无** 21 日 MACD。
- `board_score_weights.macd=0.20` 只服务 `BoardService` 板块分，**不进** `assign_grade`。旁路可降 macd、加 structure 块权重。
- 约定阶梯：**B0** soft score 旁路 + 5d/20d holdout → **B1** `shadow_grade` 平行列 → **B2** 用户批准后才改 live assign_grade。
- 现成因子胜率脚本：`E:\worktrees\etf-calc-decision-20261024\research\calc_decision\run_empirical_factors.py`（IC/hit，**不是**五档回放；测量口径曾有审计 bug）。
- **无**现成五档历史胜率 CLI；需要时旁路加 `replay_assign_grade`。

### 2026-11-05 三槽（现网已发 · 勿重推）

| 槽 | message_id | site sequence | grades |
|----|------------|---------------|--------|
| 11:40 | 6258777 | 1793850081225 | 17/0/15/2/0 |
| 14:30 | 6287852 | 1793860274210 | 15/0/17/2/0 |
| 14:45 | 6290545 | 1793861175135 | 15/0/17/2/0 |

发件：`jovi-bot@mail.grokbot.com` → `zxf977191131@gmail.com` + `977191131@qq.com`（站立直发、无草稿卡）。

---

## 3. 每天几点发邮件（Asia/Shanghai）

| 槽位 | 计划 / 例程 | 说明 |
|------|-------------|------|
| **11:40** | 例程约 11:50（可晚至 ~3 min）`ETF加减仓11:40` | 午间策略图文 |
| **14:30** | 工作日 14:30 `ETF加减仓14:30` | 主策略图文 |
| **14:45** | 工作日约 14:50 `ETF加减仓14:45` | 尾盘策略图文 |
| **~17:00** | 研究 holdout / 旁路数字（拟） | 不进现网五档 |
| **~17:30** | 研究摘要邮件（拟 · Phase B） | 非现网槽；需用户确认后再建例程 |

G1–G7 全过 → `SEND_CLEAN_*.json` → **父进程 inline SendEmail**（executor 不能稳挂 CID PNG）。

---

## 4. 网站怎么推送

1. Live 任务在 Jovi 算出 bundle → 写入 `F:\ETF_Data\ETF-Fund-Analysis\outbox\bundle_<sequence>.json`。
2. Shadow sync 上传；网站回执 **accepted**（同 identity 勿重推；`already_accepted` 则停）。
3. Manifest 含 `code_sha` / `config_hash` / `sequence` / `actionable=false` / `calibration_status`。
4. 邮件侧：`extract_slim.py <bundle>` →（Phase A）`attach_structure_v1` → `render_strategy_email` → 图文发送。
5. **看板旁路** 只在 `feature/structure-v1-wyckoff-dow-atr` serve；**勿**把 live 任务的 `SHADOW_SYNC_CODE_SHA` / CONFIG 切到 feature。

当前 live 例：`code_sha=a0d52e44…` · `config_hash=a12c6ea1…`（以当日 manifest 为准）。

---

## 5. 权重键速查（live `config/strategy.json`）

- **五档规则：** `signal_grade.*` — `j_add_cap`, `volume_expand`, `stall_return`, `macd_approach_hist`, RSI/KDJ 阈，`board_score_weights`（仅看板分）。
- **买卖分数：** `signal.*` — `entry_score`/`probe_score`/`reduce_score`/`hard_reduce_score` + `*_threshold_weight_points`。
- **轮动回测：** `backtest.factor_weights`。
- **家族权：** `strategy_engine.family_weights`。

旁路实验请 **fork** strategy，禁止改 live 文件。

---

## 6. 合并政策

- ✅ 提交 / push：`feature/structure-v1-wyckoff-dow-atr`
- ✅ 合入 **可审查目标**（如 `review/structure-v1-from-a0d52e44` @ frozen `a0d52e44`）或对该 base 开 PR
- ❌ **现在不合** live worktree / 不改 CONFIG_HASH / 不改 assign_grade
- ❌ 不满 3 交易日平行 + holdout + 用户批准 → 不合 production

---

## 7. 接手检查清单

- [ ] 读本文件 + `PHASE_A_WIRING.md` + schema
- [ ] 确认 live SHA 仍为 `a0d52e44`、feature 未挂到 live 任务
- [ ] 下一交易日邮件：render 前跑 `attach_structure_v1`（Phase A 平行 day 计数）
- [ ] Phase B：等 Grok 5d/20d 数字；需要时再要 `replay_assign_grade` 骨架
- [ ] 概念多钉（CPO/光通信/液冷/英伟达/AI芯片/…）仍为待办，勿与 structure 合并混做

---

## 8. 联系面

- ETF Bot：槽位门禁、图文发送、feature 接线、现网冻结
- Grok Bot：structure shadow、离线胜率 / B0 soft weight
- 用户审批：合 live、Cloud Agent、改 assign_grade、新建 17:30 例程
