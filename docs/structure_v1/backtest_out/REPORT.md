# structure_v1 walk-forward report (research only)

- Generated: `2026-11-05T17:19:55.610897+08:00` (Asia/Shanghai)
- Bars: `/workspace/etf_structure_features/data/bars_cache.json` (akshare qfq, 34 codes)
- Eval: **2026-06-10 → 2026-10-22** (90 trading days with full 10d forward)
- Horizons: close→close **1d / 5d / 10d** · gross (no costs)
- Causality: `build_structure_row` on bars ≤ as_of; Dow lag_n=2
- Production: **untouched** (no assign_grade / CONFIG_HASH / live strategy.json)
- Scope note: structure overlay win-rate only — not five-档 grade replay (no CLI yet)

## Headline win-rate (5d)

| variant | win_rate | n_active | avg_pnl_active |
|---|---:|---:|---:|
| baseline_always_long | 41.90% | 3060 | -0.6318% |
| baseline_momentum5 | 50.22% | 2722 | -0.1019% |
| **soft_c_strict_ternary (best)** | **50.83%** | 840 | **0.0266%** |
| soft_a_balanced_ternary | 49.08% | 1471 | 0.0198% |

- soft_c_strict_ternary **10d**: wr=53.33%, avg_pnl_active=0.1334%, n=840
- Window was net **down** for always-long (5d wr 41.90%); ternary short leg is why soft_c beats it.
- Long-only soft overlays ≈ always-long on wr and stay negative on pnl → not recommended in this window.
- Selection bias: best picked on same 90d window — treat as hypothesis; re-check next 3 trading days + a later holdout.

## Ranked weight proposals (NOT applied to live)

### 1) `soft_c_strict` — try next (preferred)
```
w_wyckoff=0.40  w_dow=0.60  conf_floor=0.45  buy_thresh=0.30  flat_band=0.12
atr_scale: low=1.0 mid=0.9 high=0.4 extreme=0.0 unknown=0.4
```
Best 5d/10d ternary wr; kills extreme ATR. Fewer trades (stricter).

### 2) `soft_a_balanced` — runner-up
```
w_wyckoff=0.45  w_dow=0.55  conf_floor=0.35  buy_thresh=0.20  flat_band=0.08
atr_scale: low=1.0 mid=1.0 high=0.55 extreme=0.0 unknown=0.5
```
More active signals; 5d wr ~49% with near-flat pnl.

### 3) `soft_b_wy_heavy` — cautionary / do not promote yet
```
w_wyckoff=0.65  w_dow=0.35  conf_floor=0.30  buy_thresh=0.15  flat_band=0.05
atr_scale: low=1.0 mid=0.95 high=0.7 extreme=0.15 unknown=0.5
```
Mild extreme ATR leak hurts (extreme bucket 5d wr ~40.7%, avg_pnl ~-1.3%). Kept as negative control.

## strategy.json fork targets (later only)

Preferred new block: `structure_soft_weight` ← copy numbers above.
Secondary bumps after parallel display: `backtest.factor_weights.structure` 0.04→0.08,
`strategy_engine.family_weights.structure` 0.10→0.14; map atr bucket → `signal.portfolio_exposure_caps`.
Do **not** change `signal_grade.*` five-档 thresholds without `replay_assign_grade`.

## Full variant table

| variant | h | n_active | win_rate | avg_pnl_active | avg_pnl_all |
|---|---:|---:|---:|---:|---:|
| `baseline_always_long` | 1 | 3060 | 45.85% | -0.1002% | -0.1002% |
| `baseline_always_long` | 5 | 3060 | 41.90% | -0.6318% | -0.6318% |
| `baseline_always_long` | 10 | 3060 | 38.56% | -1.4421% | -1.4421% |
| `baseline_momentum5` | 1 | 2722 | 47.61% | -0.0756% | -0.0672% |
| `baseline_momentum5` | 5 | 2722 | 50.22% | -0.1019% | -0.0907% |
| `baseline_momentum5` | 10 | 2722 | 51.47% | 0.2268% | 0.2017% |
| `soft_a_balanced_long_only` | 1 | 702 | 42.45% | -0.0895% | -0.0205% |
| `soft_a_balanced_long_only` | 5 | 702 | 41.45% | -0.3643% | -0.0836% |
| `soft_a_balanced_long_only` | 10 | 702 | 38.75% | -0.5997% | -0.1376% |
| `soft_a_balanced_ternary` | 1 | 1471 | 46.43% | -0.0248% | -0.0119% |
| `soft_a_balanced_ternary` | 5 | 1471 | 49.08% | 0.0198% | 0.0095% |
| `soft_a_balanced_ternary` | 10 | 1471 | 49.08% | 0.0473% | 0.0227% |
| `soft_b_wy_heavy_long_only` | 1 | 858 | 42.54% | -0.1131% | -0.0317% |
| `soft_b_wy_heavy_long_only` | 5 | 858 | 41.49% | -0.4750% | -0.1332% |
| `soft_b_wy_heavy_long_only` | 10 | 858 | 38.69% | -0.7928% | -0.2223% |
| `soft_b_wy_heavy_ternary` | 1 | 1653 | 45.86% | -0.0207% | -0.0112% |
| `soft_b_wy_heavy_ternary` | 5 | 1653 | 48.88% | -0.0415% | -0.0224% |
| `soft_b_wy_heavy_ternary` | 10 | 1653 | 47.97% | -0.0379% | -0.0205% |
| `soft_c_strict_long_only` | 1 | 346 | 42.77% | -0.0507% | -0.0057% |
| `soft_c_strict_long_only` | 5 | 346 | 39.31% | -0.3239% | -0.0366% |
| `soft_c_strict_long_only` | 10 | 346 | 41.33% | -0.4497% | -0.0508% |
| `soft_c_strict_ternary` | 1 | 840 | 47.14% | -0.0093% | -0.0025% |
| `soft_c_strict_ternary` | 5 | 840 | 50.83% | 0.0266% | 0.0073% |
| `soft_c_strict_ternary` | 10 | 840 | 53.33% | 0.1334% | 0.0366% |

See also `summary_by_atr_bucket.csv`, `summary_by_phase.csv`, `proposed_weights.json`, `KNOBS.md`.
Re-run: `python3 backtest/run_walkforward.py` (see `backtest/README.md`).
