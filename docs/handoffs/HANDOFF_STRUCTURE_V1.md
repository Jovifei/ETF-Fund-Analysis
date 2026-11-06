# HANDOFF — structure_v1 (Wyckoff / Dow / ATR)

**Canonical (box research, fullest copy):** `/workspace/etf_structure_features/HANDOFF_STRUCTURE_V1.md`  
**In-repo (ETF Bot path):** `docs/handoffs/HANDOFF_STRUCTURE_V1.md`  
**Acceptance sibling:** `/workspace/etf_structure_features/REQUIREMENTS.md` · `docs/handoffs/REQUIREMENTS_STRUCTURE_V1.md`  
**Timezone:** Asia/Shanghai (UTC+8) · **Updated:** 2026-11-05 ~19:10

> Successor AI/agent should continue from this file. Do **not** change live `assign_grade` or flip `CONFIG_HASH`. No Cursor CloudAgent / work-quota.

---

## 0. Hard constraints

1. **Forbidden:** edit live `code_sha=a0d52e44…`, flip `CONFIG_HASH`, or change `assign_grade` / production five-档 unless user explicitly approves **and** gates in §10 pass.
2. **Forbidden:** default Cursor cloud / work-quota.
3. Do not touch server containers **药箱 / 逐星 / jourvolt**.
4. Strategy mail must be **图文** (compact HTML + inline/CID images), not body.txt + PNG attachment piles.
5. Keep `actionable=false` · `research_only=true` · `calibration_status=not_calibrated`.
6. Phase A needs **≥3 trading-day parallel** + holdout standing + user approve before any live merge.

---

## 1. Goal & phases

**Goal:** Put Wyckoff (volume–price / accumulation–distribution proxies), Dow trend structure, and ATR risk into the ETF decision stack — display first, soft weights next, live five-档 only if evidence holds.

| Phase | Name | What changes | Live five-档 / CONFIG_HASH |
|-------|------|--------------|----------------------------|
| **A** | Display-only | Optional per-row `structure_v1` on slim/email + decision board research columns | **Untouched** |
| **B0** | Soft-weight research | Offline walk-forward / holdout; proposed `board_score_weights` / `structure_soft_weight` fork | **Untouched** (旁路 only) |
| **B1** | `shadow_grade` | Parallel旁路 grade column from rule-tree copy + structure gate | Live five-档 still frozen |
| **B2** | Live promote | Change live `assign_grade` / strategy.json / CONFIG_HASH | Only after §10 |

**Authorized now:** Phase A parallel + B0 research. B1/B2 not started.

**Update 2026-11-06 (Muse, on the user's direct instruction after Grok Bot
had no new submission for ~12h):** B1 is now implemented on the feature
branch — see `docs/structure_v1/PHASE_A_WIRING.md` §"Phase B1 wiring".
Frozen soft_c weights run as a parallel `structure_shadow` column
(board / web / email); live five-档 and CONFIG_HASH remain untouched.
B2 is still **not** authorized or gated-in: it needs the ≥3 trading-day
parallel record, holdout standing, and a separate explicit approval.

---

## 2. Current status (2026-11-05 Asia/Shanghai) — FACTS

### Git / merge (authoritative)

| Ref | Value |
|-----|-------|
| Feature tip (wiring + ETF Bot handoff) | **`9a072f26675a51eca9d7ec11961efcd1b5ff7e01`** |
| Remote feature | **`origin/feature/structure-v1-wyckoff-dow-atr`** — **pushed** |
| Wiring commit | `5844e828` — Phase A structure_v1 display columns (research only) |
| Review baseline | **`origin/review/structure-v1-from-a0d52e44`** @ frozen **`a0d52e44`** |
| PR into review | **#64** merged as **`ecc26155bc504b20f4387234541f8ab675168526`** |
| Live / `main` merge | **NOT done** — do not treat review merge as production cutover |
| Live trading SHA | **`a0d52e44`** still frozen for grade logic |
| Live CONFIG_HASH (example) | `a12c6ea1…` (do not flip for structure) |

### Phase A runtime

| Item | Status |
|------|--------|
| Proxies in-repo | **Real** ATR/Dow/Wyckoff (stubs removed 2026-11-05 review fix); `build_shadow.py` reproducible |
| Board fill | `decision_board_service` soft-fills from history when block missing; sidecar optional |
| Tests | `backend/tests/test_structure_v1.py` |
| Contract | Flat per-row `structure_v1` (**not** nested `research_display`) |
| Schema | `research/etf_structure_features/` in feature tree · box `schemas/structure_fund_row.schema.json` |
| Shadow | **34/34** → box `/workspace/etf_structure_features/out/shadow_20261105.json` · in-repo `docs/structure_v1/shadow_20261105.json` |
| ATR bucket | `atr_pct_fixed_v1` (low<1%, mid[1%,2%), high[2%,3.5%), extreme≥3.5%) |
| Email attach | `attach_structure_v1.py` / extract `--structure-sidecar` · slim `etf-email-slim-v1.1` |
| Dry-run | OK 2026-11-05 · `/workspace/etf_slot/email_render/out/phase_a_dryrun_20261105/` |
| Board cols | +3 research cols; **not** in `DECISION_SORTABLE`; `assign_grade` untouched |
| Worktree (Jovi) | `E:\worktrees\etf-phase-a-structure-v1-20261105` |
| Live worktree | live a0d52e4 worktree — **do not hang feature SHA on live tasks** |
| B0 weights | **Frozen** after verdict **`WEAK_PASS_KEEP_FROZEN`** |
| Phase A live-merge gate | Still need **≥3 trading-day** parallel after 2026-11-05 |
| Live / main | **NOT merged** |

### 2026-11-05 production slots (already sent — do not re-push)

| Slot | message_id | site sequence | grades (可加仓/可入场/观望/可试探/减仓 — as logged) |
|------|------------|---------------|------|
| 11:40 | 6258777 | 1793850081225 | 17/0/15/2/0 |
| 14:30 | 6287852 | 1793860274210 | 15/0/17/2/0 |
| 14:45 | 6290545 | 1793861175135 | 15/0/17/2/0 |

From `jovi-bot@mail.grokbot.com` → `zxf977191131@gmail.com` + `977191131@qq.com` (standing **direct send**).

---

## 3. Requirements from user (verbatim intent)

1. 把威科夫（量价、吸筹派发）、道氏、ATR **加入决策因子**，且 **占比重高于 MACD**。
2. **周 / 月** 尺度对定权重比日更重要。
3. 用历史数据跑出推荐买卖与权重公式；先验证再改 live。
4. **先不改权重，再跑 holdout**（user freeze answer）。
5. 问过决策是否可行、**胜率是否大于 60%** → research: **not yet stably >60%** (short holdout ~62% with tiny n).
6. 决策、测试结果、需求、每天发信时刻、网站推送路径全部记录，便于 **另一 AI 接手**；提交仓库并合并（**review OK; live/main only after gates**）。
7. Standing: no Cursor CloudAgent; ETF strategy mail direct-send; bots report before merging to main that affects production.

**MACD fact:** production **12/26/9**, not 21. “MACD21” → MA20 / monthly horizon / optional research slow-MACD only.

See also `REQUIREMENTS.md` for checkbox acceptance criteria.

---

## 4. Test results (B0) — detailed

Five-档 historical win-rate CLI **still does not exist**. Numbers = structure soft-overlay walk-forward (gross close→close, no costs, 34 ETFs, akshare qfq).

### Selection `2026-06-10 → 2026-10-22` (90 days with 10d forward)

| variant | horizon | win_rate | n_active | avg_pnl_active |
|---------|---------|---------:|---------:|---------------:|
| baseline_always_long | 5d | 41.90% | 3060 | -0.6318% |
| baseline_momentum5 | 5d | 50.22% | 2722 | -0.1019% |
| **soft_c_strict_ternary** | **5d** | **50.83%** | 840 | +0.0266% |
| soft_c_strict_ternary | 10d | 53.33% | 840 | +0.1334% |
| soft_c_strict_ternary | **20d** | **53.72%** | 698 | +0.3222% |
| **structure_heavy_ternary** | **5d** | **52.91%** | 1185 | +0.0481% |
| structure_heavy_ternary | 10d | 54.01% | 1185 | +0.1956% |
| structure_heavy_ternary | **20d** | **49.25%** | 999 | -0.2730% |

### Holdout `2026-10-23 → 2026-11-05` (frozen weights)

| note | value |
|------|-------|
| 5d usable as_of | **5 days only** (`10-23→10-29`) |
| 10d / 20d holdout | **unavailable** |
| soft_c_strict_ternary 5d wr | **62.07%** (n=58) |
| soft_a_balanced_ternary 5d wr | 62.50% |
| always_long / momentum5 5d | 50.59% / 49.66% |
| soft_c avg_pnl vs momentum | +0.23% **<** momentum +0.68% |
| **Verdict** | **`WEAK_PASS_KEEP_FROZEN`** — do not promote; ~60% bar **not stable** |

Reports (box):  
`/workspace/etf_structure_features/backtest/out/{REPORT,holdout_REPORT,horizon_REPORT,FORMULA_structure_over_macd}.md`

Weekday ~**17:00** holdout re-run routine exists. **~17:30 research digest mail proposed — not confirmed wired to SendEmail.**

Separate empirical factors (≠ five-档): `E:\worktrees\etf-calc-decision-20261024\research\calc_decision\run_empirical_factors.py`.

---

## 5. Proposed weights (NOT applied to live)

### soft_c_strict (frozen preferred overlay)

```
w_wyckoff=0.40  w_dow=0.60  conf_floor=0.45  buy_thresh=0.30  flat_band=0.12
atr_scale: low=1.0 mid=0.9 high=0.4 extreme=0.0 unknown=0.4
```

`/workspace/etf_structure_features/backtest/out/proposed_weights.json`

### structure_heavy board bypass (structure trio > MACD)

| key | current (box v0.7.4 board) | bypass |
|-----|---------------------------:|-------:|
| wyckoff | — | **0.14** |
| dow | — | **0.16** |
| atr_inv | — | **0.10** |
| macd | 0.20 | **0.10** |
| ma | 0.20 | 0.14 |
| volume | 0.15 | 0.10 |
| kdj | 0.15 | 0.10 |
| rsi | 0.15 | 0.08 |
| momentum | 0.10 | 0.05 |
| td | 0.05 | 0.03 |

Trio share **0.40** > macd **0.10**.  
JSON/FORMULA: `proposed_weights_structure_heavy.json`, `FORMULA_structure_over_macd.md`.

### Live five-档 reference (unchanged)

Rule tree `assign_grade` (not a weighted average): KDJ/MACD death → 减仓; J high / stall → 观望; J&lt;90 + expand + MA bull → 可加仓; …  
`board_score_weights` only feed BoardService industry/concept score — **not** five-档.  
Signal-center gates: entry≥68, probe≥58, reduce&lt;38, hard_reduce&lt;28.  
Fork strategy.json for experiments — **never** edit live file.

Live `strategy.json` key map: `signal_grade.*`, `signal.*`, `backtest.factor_weights`, `strategy_engine.family_weights`, `indicator.macd` = 12/26/9.

---

## 6. Email schedule (Asia/Shanghai)

| Slot | Routine / plan | Notes |
|------|----------------|-------|
| **11:40** | ~11:50 routine `ETF加减仓11:40` (may slip ~3 min) | Midday 图文 |
| **14:30** | weekday 14:30 `ETF加减仓14:30` | Main 图文 |
| **14:45** | ~14:50 `ETF加减仓14:45` | Late 图文 |
| **~17:00** | structure_v1 holdout 收盘复跑 | Research only; not five-档 |
| **~17:30** | research digest (proposed) | **Not confirmed wired** — need user confirm before new routine |

Pipeline: G1–G7 pass → `SEND_CLEAN_*.json` → **parent inline SendEmail** (executor CID PNG unreliable).  
Box render: `/workspace/etf_slot/email_render/`. Phase A: attach shadow **before** render.

---

## 7. Website push path

1. Live task on Jovi writes `F:\ETF_Data\ETF-Fund-Analysis\outbox\bundle_<sequence>.json`.
2. Shadow sync upload; site receipt must be **`status=accepted`** (same identity → do not re-push; `already_accepted` → stop).
3. Manifest: `code_sha` / `config_hash` / `sequence` / `actionable=false` / `calibration_status`.
4. Mail: `extract_slim.py <bundle>` → (Phase A) `attach_structure_v1` → `render_strategy_email` → 图文 send.
5. Board with structure columns: serve from **feature/旁路** only — **do not** point live task `SHADOW_SYNC_CODE_SHA` / CONFIG at feature tip for production cutover.

---

## 8. Key paths

| Path | Role |
|------|------|
| `/workspace/etf_structure_features/` | Box research + **canonical fullest handoff** |
| `/workspace/etf_structure_features/out/shadow_YYYYMMDD.json` | Daily shadow |
| `/workspace/etf_structure_features/backtest/` | walk-forward / holdout / horizon |
| `/workspace/etf_slot/email_render/` | slim / attach / render |
| `/workspace/etf-p1/` | Box clone of `https://github.com/Jovifei/ETF-Fund-Analysis.git` |
| `docs/handoffs/HANDOFF_STRUCTURE_V1.md` | In-repo handoff (this content) |
| `docs/handoffs/PHASE_A_WIRING_STRUCTURE_V1.md` | Wiring note (ETF Bot) |
| `F:\ETF_Data\ETF-Fund-Analysis\outbox\` | Production bundles |
| `F:\ETF_Data\ETF-Fund-Analysis\db\research.sqlite3` | Research DB |
| Live worktree | `…\etf-live-v113-a0d52e4\…` @ `a0d52e44` |
| Phase A worktree | `E:\worktrees\etf-phase-a-structure-v1-20261105` |

**Agents:** ETF Bot `16301bb9-f7e1-4e48-8d7e-6a397eb81271` (slots/mail/wiring/freeze) · Grok Bot (shadow/B0/holdout/docs).

---

## 9. How another AI continues (checklist)

- [ ] Read this file + `REQUIREMENTS*.md` + `PHASE_A_WIRING*` + schema
- [ ] Confirm live SHA still `a0d52e44`; feature **not** hung on live sync task
- [ ] Confirm feature tip ≥ `9a072f2` on `origin/feature/structure-v1-wyckoff-dow-atr`; review merge `ecc26155` ≠ live
- [ ] Next trading day: rebuild shadow → `attach_structure_v1` before 11:40/14:30/14:45 renders; count Phase A parallel days
- [ ] Keep ~17:00 holdout; wait for 10d/20d windows; keep freeze until promote criteria
- [ ] Optional: ask ETF Bot for旁路 `replay_assign_grade.py`
- [ ] Concept-tag backlog (CPO/光通信/…) stays separate — do not mix into structure merge
- [ ] **Never** CloudAgent by default; no force-push; no silent live/main grade merge

---

## 10. Merge policy

| Action | Status |
|--------|--------|
| Commit/push `feature/structure-v1-wyckoff-dow-atr` | ✅ done @ `9a072f2` (+ follow-up docs commits OK) |
| Merge into **`review/structure-v1-from-a0d52e44`** | ✅ PR **#64** → `ecc26155` |
| Merge into **live worktree / production CONFIG** | ❌ **not done** |
| Merge into **`main` as live grade cutover** | ❌ **not allowed yet** |
| After ≥3 trading-day Phase A parallel + holdout OOS + **user approve** | Then plan live display merge / later B2 |

---

## Quick re-run (box)

```bash
python3 /workspace/etf_structure_features/build_shadow.py
python3 /workspace/etf_structure_features/backtest/run_walkforward.py
python3 /workspace/etf_structure_features/backtest/run_walkforward.py --holdout   # see script --help
python3 /workspace/etf_structure_features/backtest/run_horizon_eval.py
python3 /workspace/etf_slot/email_render/attach_structure_v1.py \
  /workspace/etf_slot/email_render/fetched/YYYYMMDD_HHMM.slim.json \
  /workspace/etf_structure_features/out/shadow_YYYYMMDD.json
```

---

*Prefer in-place updates. Keep `do_not_apply_to_live` until B2.*
