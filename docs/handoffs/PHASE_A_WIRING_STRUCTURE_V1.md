# Phase A wiring status (2026-11-05, updated after review fixes)

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
