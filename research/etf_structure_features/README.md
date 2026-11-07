# ETF Structure Features — Phase A (Wyckoff / Dow / ATR)

**Status:** real OHLCV proxies in-repo · research / display columns · **no grade change**  
**Git branch:** `feature/structure-v1-wyckoff-dow-atr`  
**Merge gate:** ≥3 trading-day parallel display test, then review → merge. Do **not** soft-weight into `assign_grade` in Phase A. Live / `main` still frozen.

## Phase A scope (allowed)

- Compute **read-only** structure fields per fund/day from OHLC(+V) bars.
- Emit shadow JSON + optional slim/board `structure_v1` block for email + decision board **new columns**.
- Board `_row` **fills** `structure_v1` from DailyBar / research history when the block is missing (soft-fail → `None` / UI `—`). Sidecar join still optional.
- Keep `assign_grade` / five-档买卖 **unchanged**; `actionable` / calibration flags stay as production.
- Labels are **proxies** (A-share ETF volume ≠ underlying money flow). UI/email copy must say 代理 / proxy.

## Phase A out of scope

- Changing `signal_grade_service.assign_grade` inputs or thresholds / `CONFIG_HASH`.
- Soft-weighted “final decision” (Phase B after walk-forward).
- CloudAgent / Cursor cloud quota.
- Merging this branch to live / `main` without the ≥3-day gate + explicit approve.

## ATR risk bands (`atr_pct_fixed_v1`)

`atr_pct = atr14 / price` (Wilder ATR(14); slim `atr14`/`price` overrides allowed in shadow builder):

| bucket | band |
|--------|------|
| low | `[0, 1.0%)` |
| mid | `[1.0%, 2.0%)` |
| high | `[2.0%, 3.5%)` |
| extreme | `≥ 3.5%` |
| unknown | missing atr/price |

## Causality

- Dow pivots: **confirmed** only after `lag_n` bars (default 2) — no lookahead.
- Wyckoff range edges / vol expansion: use only bars ≤ `as_of`.
- ATR: Wilder recursive from history ending at `as_of`.

## Layout

```
etf_structure_features/
  README.md
  PHASE_A_WIRING.md
  build_shadow.py          # reproducible shadow builder (cache and/or --fetch)
  schemas/structure_fund_row.schema.json
  examples/fund_row.example.json
  etf_structure_features/
    __init__.py
    dow_proxy.py           # confirmed-pivot Dow proxy (real)
    wyckoff_proxy.py       # range/vol Wyckoff proxy (real)
    atr_risk.py            # Wilder ATR + atr_pct_fixed_v1 buckets (real)
    pipeline.py            # build_structure_row assembler
```

Backend soft-import: `backend/app/research/structure_v1.py` → `build_structure_row`.
Tests: `backend/tests/test_structure_v1.py`.

## Rebuild shadow

```bash
# with bars cache (no network)
python research/etf_structure_features/build_shadow.py \
  --slim /path/to/slim.json \
  --cache research/etf_structure_features/data/bars_cache.json

# or fetch missing symbols
python research/etf_structure_features/build_shadow.py --slim /path/to/slim.json --fetch
```

Sample shadow (34/34, 2026-11-05): `docs/structure_v1/shadow_20261105.json`.

## Handoff

Accept optional `structure_v1` on each slim/board fund row. Map columns; **do not** feed into grade. Missing → `—`.
