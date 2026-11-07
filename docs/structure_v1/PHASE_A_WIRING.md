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

## Phase B1 wiring (2026-11-06, Muse — user-directed takeover)

Parallel bypass only; live five-档 / CONFIG_HASH still untouched.

- `backend/app/research/structure_shadow.py` — pure frozen soft_c_strict
  overlay (`structure_shadow_v1`, weights id `soft_c_strict_frozen_v1`):
  confidence-weighted Wyckoff/Dow combo (0.40/0.60), conf floor 0.45,
  ATR scale low 1.0 / mid 0.9 / high 0.4 / extreme 0.0 / unknown 0.4,
  ternary position at buy_thresh 0.30 / flat_band 0.12. These are the B0
  frozen research weights (verdict `WEAK_PASS_KEEP_FROZEN`) — running them
  in parallel is the Phase A/B1 gate activity, **not** a live promotion.
- Board: each row gains `structure_shadow` (dict or `null`);
  payload gains `structure_shadow_changes_grade: false`.
  `assign_grade` / CONFIG_HASH / five-档 unchanged.
- Web: `app.js` adds a non-sortable 结构影子 column after ATR桶.
- Email: `render_strategy_email.py` adds a 结构影子 column to the full
  table, computed with the same frozen constants (or read from a
  bundle-provided `structure_shadow` block when present).
- Tests: `backend/tests/test_structure_shadow.py` (formula, ATR scaling,
  confidence floor, live-agreement, board helper).
- B2 (live promote) remains gated: ≥3 trading-day parallel + holdout
  standing + separate explicit user approval. Not done here.

## Box email/slim (optional sidecar still works)
- Runtime: `/workspace/etf_slot/email_render/`
- Join: `attach_structure_v1.py <slim> <shadow> [out]` or extract `--structure-sidecar`
- Sample shadow: `docs/structure_v1/shadow_20261105.json`
