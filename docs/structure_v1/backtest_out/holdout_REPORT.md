# structure_v1 HOLDOUT report (research only — frozen weights)

- Generated: `2026-11-05T17:25:23.880667+08:00` (Asia/Shanghai)
- Mode: **HOLDOUT (frozen weights; no retune)**
- Bars: `/workspace/etf_structure_features/data/bars_cache.json` akshare qfq · 34 codes · common calendar last=`2026-11-05`
- Eval window (as_of candidates): **2026-10-23 → 2026-11-05** (10 calendar days in range)
- Horizon 1d usable as_of: **2026-10-23 → 2026-11-04** (9 days with full 1d forward)
- Horizon 5d usable as_of: **2026-10-23 → 2026-10-29** (5 days with full 5d forward)
- Horizon 10d usable as_of: **none** (truncated — not enough forward bars)
- Selection window (excluded): ≤ `2026-10-22` (prior REPORT.md)
- Weight freeze: Frozen against `/workspace/etf_structure_features/backtest/out/proposed_weights.json` (no rewrite in holdout mode)
- **No retune** on holdout; proposed_weights.json not rewritten
- Horizons: forward close→close **1d / 5d / 10d** (gross, no costs)
- Causality: `build_structure_row` on bars ≤ as_of; Dow lag_n=2; no lookahead
- **Production untouched**: no assign_grade / CONFIG_HASH / live strategy.json edits

## Headline (horizon = 5d)

| variant | n_active | win_rate | avg_pnl_active | avg_pnl_all |
|---|---:|---:|---:|---:|
| `baseline_always_long` | 170 | 50.59% | -0.6043% | -0.6043% |
| `baseline_momentum5` | 149 | 49.66% | 0.6752% | 0.5918% |
| `soft_a_balanced_long_only` | 32 | 78.12% | 0.8986% | 0.1692% |
| `soft_a_balanced_ternary` | 80 | 62.50% | 0.4404% | 0.2072% |
| `soft_b_wy_heavy_long_only` | 40 | 65.00% | 0.4059% | 0.0955% |
| `soft_b_wy_heavy_ternary` | 93 | 59.14% | 0.3718% | 0.2034% |
| `soft_c_strict_long_only` | 26 | 76.92% | 0.5533% | 0.0846% |
| `soft_c_strict_ternary` | 58 | 62.07% | 0.2294% | 0.0783% |

## Full variant × horizon

| variant | h | n_active | win_rate | avg_pnl_active | avg_pnl_all |
|---|---:|---:|---:|---:|---:|
| `baseline_always_long` | 1 | 306 | 52.61% | 0.1748% | 0.1748% |
| `baseline_always_long` | 5 | 170 | 50.59% | -0.6043% | -0.6043% |
| `baseline_momentum5` | 1 | 268 | 47.76% | 0.0227% | 0.0199% |
| `baseline_momentum5` | 5 | 149 | 49.66% | 0.6752% | 0.5918% |
| `soft_a_balanced_long_only` | 1 | 55 | 60.00% | 0.5465% | 0.0982% |
| `soft_a_balanced_long_only` | 5 | 32 | 78.12% | 0.8986% | 0.1692% |
| `soft_a_balanced_ternary` | 1 | 159 | 45.91% | -0.0380% | -0.0198% |
| `soft_a_balanced_ternary` | 5 | 80 | 62.50% | 0.4404% | 0.2072% |
| `soft_b_wy_heavy_long_only` | 1 | 74 | 52.70% | 0.3867% | 0.0935% |
| `soft_b_wy_heavy_long_only` | 5 | 40 | 65.00% | 0.4059% | 0.0955% |
| `soft_b_wy_heavy_ternary` | 1 | 201 | 43.28% | -0.1478% | -0.0971% |
| `soft_b_wy_heavy_ternary` | 5 | 93 | 59.14% | 0.3718% | 0.2034% |
| `soft_c_strict_long_only` | 1 | 40 | 55.00% | 0.3786% | 0.0495% |
| `soft_c_strict_long_only` | 5 | 26 | 76.92% | 0.5533% | 0.0846% |
| `soft_c_strict_ternary` | 1 | 110 | 43.64% | -0.0227% | -0.0082% |
| `soft_c_strict_ternary` | 5 | 58 | 62.07% | 0.2294% | 0.0783% |

## Pass / fail

- **Verdict: `WEAK_PASS_KEEP_FROZEN`**
- soft_c beats both baselines on 5d wr but not both on pnl (or pnl mixed). Keep weights frozen; do not promote yet. (10d full-forward days available: 0)

Criteria (pre-registered, not fit on holdout):
- PASS_PROMOTE_旁路: soft_c_strict_ternary 5d wr **and** avg_pnl_active beat both baselines; n_active≥30
- WEAK_PASS_KEEP_FROZEN: beats both on wr only
- KEEP_FROZEN: beats ≤1 baseline, or sample too small
- FAIL_ABANDON_OR_REVISE: loses to both baselines on 5d wr

## Frozen weight sets (unchanged)

### `soft_a_balanced`
- w_wyckoff=0.45, w_dow=0.55, conf_floor=0.35, buy_thresh=0.2, flat_band=0.08
- atr_scale={'low': 1.0, 'mid': 1.0, 'high': 0.55, 'extreme': 0.0, 'unknown': 0.5}

### `soft_b_wy_heavy`
- w_wyckoff=0.65, w_dow=0.35, conf_floor=0.3, buy_thresh=0.15, flat_band=0.05
- atr_scale={'low': 1.0, 'mid': 0.95, 'high': 0.7, 'extreme': 0.15, 'unknown': 0.5}

### `soft_c_strict`
- w_wyckoff=0.4, w_dow=0.6, conf_floor=0.45, buy_thresh=0.3, flat_band=0.12
- atr_scale={'low': 1.0, 'mid': 0.9, 'high': 0.4, 'extreme': 0.0, 'unknown': 0.4}

## Outputs

- `holdout_trades_detail.csv`
- `holdout_summary_by_variant.csv`
- `holdout_summary_by_atr_bucket.csv`
- `holdout_summary_by_phase.csv`
- `holdout_REPORT.md` (this file)

## Re-run

```bash
cd /workspace/etf_structure_features
python3 backtest/run_walkforward.py --holdout --start-after 2026-10-22
```
