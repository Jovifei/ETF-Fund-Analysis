# Phase A wiring status (2026-11-05)

## Contract
Optional per-row flat block `structure_v1` only (NOT `research_display`).
Schema: `schemas/structure_fund_row.schema.json`.

## Branch
`feature/structure-v1-wyckoff-dow-atr` @ base `a0d52e44`  
Worktree: `E:\worktrees\etf-phase-a-structure-v1-20261105`  
Live tree untouched.

## Box email/slim
- Runtime: `/workspace/etf_slot/email_render/`
- `slim_version`: `etf-email-slim-v1.1`
- Join: `attach_structure_v1.py <slim> <shadow> [out]` or extract `--structure-sidecar`
- Shadow: `/workspace/etf_structure_features/out/shadow_20261105.json`
- Dry-run:
  - dash (no structure): `out/phase_a_dryrun_20261105/render_dash/`
  - shadow joined: `out/phase_a_dryrun_20261105/render_shadow/`

## Board
`app.js` DECISION_COLUMNS +3 research cols; not in DECISION_SORTABLE.
`shadow_export.ROW_FIELDS` includes `structure_v1`.
`decision_board_service._row` passthrough if present.
`signal_grade_service.assign_grade` untouched.
