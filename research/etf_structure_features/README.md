# ETF Structure Features — Phase A (Wyckoff / Dow / ATR)

**Status:** scaffold only · research / display columns · **no grade change**  
**Production base (box):** `/workspace/etf-p1` @ `103522c` (`origin/main`)  
**Git branch (created, no feature commits yet):** `feature/structure-v1-wyckoff-dow-atr`  
**Merge gate:** ≥3 trading-day parallel display test, then review → merge. Do **not** soft-weight into `assign_grade` in Phase A.

## Phase A scope (allowed)

- Compute **read-only** structure fields per fund/day from OHLC(+V) bars already available to local compute.
- Emit sidecar / slim optional block for email + decision board **new columns**.
- Keep `assign_grade` / five-档买卖 **unchanged**; `actionable` / calibration flags stay as production.
- Labels are **proxies** (A-share ETF volume ≠ underlying money flow). UI/email copy must say 代理 / proxy.

## Phase A out of scope

- Changing `signal_grade_service.assign_grade` inputs or thresholds.
- Soft-weighted “final decision” (Phase B after walk-forward).
- CloudAgent / Cursor cloud quota.
- Pushing to `origin` without user/ETF Bot release process.

## Field contract (one fund row)

See `schemas/structure_fund_row.schema.json`. Required display fields:

| Field | Meaning |
|-------|---------|
| `wyckoff_phase` | Proxy phase enum (range/vol heuristic) |
| `wyckoff_score` | −1..1 bullish structure bias |
| `wyckoff_confidence` | 0..1 |
| `dow_phase` | Confirmed-pivot trend enum |
| `dow_score` | −1..1 |
| `dow_confidence` | 0..1 |
| `atr14` | Wilder ATR(14), align with `price_structure` |
| `atr_pct` | `atr14 / close` |
| `atr_risk_bucket` | low / mid / high / extreme (quantile or fixed bands) |
| `evidence[]` | Short audit strings (pivots, range, vol ratio) |

## Causality

- Dow pivots: **confirmed** only after `lag_n` bars (default 2) — no lookahead.
- Wyckoff range edges / vol expansion: use only bars ≤ `as_of`.
- ATR: Wilder recursive from history ending at `as_of`.

## Layout

```
etf_structure_features/
  README.md
  schemas/structure_fund_row.schema.json
  examples/fund_row.example.json
  etf_structure_features/
    __init__.py
    dow_proxy.py      # confirmed-pivot Dow stub
    wyckoff_proxy.py  # range/vol Wyckoff stub
    atr_risk.py       # atr14 / atr_pct / bucket stub
    pipeline.py       # row assembler stub
```

## Handoff to ETF Bot (ingest)

Accept optional `structure_v1` object on each slim/board fund row (or sidecar keyed by `ts_code`+`as_of`). Map columns; **do not** feed into grade. Email/HTML: add columns only when payload present; missing → `—`.

## Other local copies (not used for branch)

| Path | Notes |
|------|--------|
| `/workspace/etf-p1` | **Chosen** — remote `Jovifei/ETF-Fund-Analysis`, clean @ origin/main |
| `/workspace/etf-deploy/ETF-Fund-Analysis` | Same remote; dirty/feature ahead — not base |
| `/workspace/slot1140/repo` | No remote; dirty staged slot1140 patches |
| `/workspace/h5/src` | No remote; heavily dirty H5 WIP |
| `/workspace/etf_slot` | Runtime payloads only, no `.git` |
