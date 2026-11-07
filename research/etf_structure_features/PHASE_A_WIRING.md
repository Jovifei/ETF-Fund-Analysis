# Phase A wiring status (2026-11-05, updated after review fixes)

> **方向更正（2026-11-07，项目所有者决定）**：威科夫/道氏/ATR 已正式接入实时决策，不再只是并行影子展示。
> 实现：`backend/app/research/structure_decision.py` 在决策板层以暂定权重 0.5 对基础五档做有界调整（最多一档，
> 不能单独造出可加仓/减仓，硬档不调整）；比例由所有者后续确定。策略版本 signal-v0.7.6-structure-decision。
> 本文其余内容记录 Phase A 接线当时的状态，凡与上述决定冲突处以本注为准。记录见
> `docs/handoffs/CONSOLIDATION_20261107.md`。


## Contract
Optional per-row flat block `structure_v1` only (NOT `research_display`).
Schema: `schemas/structure_fund_row.schema.json` / `research/etf_structure_features/schemas/`.

## Branch
`feature/structure-v1-wyckoff-dow-atr` — rebase onto current `origin/main` (Playwright `ubuntu-24.04` pin).
Review target: `review/structure-v1-from-a0d52e44` only. **Live / main untouched.**

## Proxies (in-repo, reproducible)
Stubs replaced. Real implementations under `research/etf_structure_features/etf_structure_features/`:
- `atr_risk.py` — Wilder ATR(14) + `atr_pct_fixed_v1` bands
- `dow_proxy.py` — confirmed pivots (`lag_n=2`)
- `wyckoff_proxy.py` — range/volume phase proxy
- `pipeline.py` — `build_structure_row`
Shadow builder: `research/etf_structure_features/build_shadow.py`

## Board / production fill
`decision_board_service._row` calls `_resolve_structure_v1_for_row`:
1. Passthrough existing `structure_v1` on grade/values when present
2. Else soft-fill from DailyBar / research history via `app.research.structure_v1`
3. Soft-fail → `None` (UI `—`)
No sidecar required for the three research columns to populate.
`app.js` DECISION_COLUMNS +3 research cols; **not** in `DECISION_SORTABLE`.
`signal_grade_service.assign_grade` / CONFIG_HASH / five-档 **untouched**.

## Box email/slim (optional sidecar still works)
- Runtime: `/workspace/etf_slot/email_render/`
- Join: `attach_structure_v1.py <slim> <shadow> [out]` or extract `--structure-sidecar`
- Sample shadow: `docs/structure_v1/shadow_20261105.json`
