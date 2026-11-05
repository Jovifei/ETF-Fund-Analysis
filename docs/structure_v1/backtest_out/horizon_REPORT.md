# Horizon eval — structure_heavy vs soft_c (B0 research)

- Generated: `2026-11-05T18:08:57.250742+08:00` (Asia/Shanghai)
- Bars: `/workspace/etf_structure_features/data/bars_cache.json` · 34 codes · calendar last=`2026-11-05`
- Selection as_of: **2026-06-10 → 2026-10-22** (90 days)
- Holdout as_of: **> 2026-10-22** (10 days through `2026-11-05`)
- Horizons: forward close→close **5d (week-ish) / 10d / 20d (month-ish)**; gross, no costs
- MACD proxy: **12/26/9** hist→tanh (matches production); **no 21-day** in live
- **Live untouched**: no assign_grade / CONFIG_HASH / strategy.json edits

## Board bypass weights (suggested, NOT applied)

| key | current (box v0.7.4) | structure_heavy bypass |
|---|---:|---:|
| `wyckoff` | — | **0.14** |
| `dow` | — | **0.16** |
| `atr_inv` | — | **0.10** |
| `macd` | 0.2 | **0.10** |
| `ma` | 0.2 | **0.14** |
| `volume` | 0.15 | **0.10** |
| `kdj` | 0.15 | **0.10** |
| `rsi` | 0.15 | **0.08** |
| `momentum` | 0.1 | **0.05** |
| `td` | 0.05 | **0.03** |

- **structure trio (wy+dow+atr_inv) = 0.40 > macd = 0.10**
- Soft overlay blend inside walk-forward: `w_structure_combo=0.4` vs `w_macd=0.1`; when `|structure|≥0.45`, MACD weight halves (override).

## Usable as_of days per horizon

| window | 5d days | 10d days | 20d days |
|---|---:|---:|---:|
| selection | 90 | 90 | 80 |
| holdout | 5 | 0 | 0 |

- Holdout **20d unavailable** yet (need ≥20 trading days after first holdout as_of; calendar ends `2026-11-05`). Re-run after more sessions.

## Headline: soft_c vs structure_heavy

### selection

| variant | h | n_active | win_rate | avg_pnl_active | avg_pnl_all |
|---|---:|---:|---:|---:|---:|
| `baseline_always_long` | 5 | 3060 | 41.90% | -0.6318% | -0.6318% |
| `baseline_always_long` | 10 | 3060 | 38.56% | -1.4421% | -1.4421% |
| `baseline_always_long` | 20 | 2720 | 37.54% | -2.9731% | -2.9731% |
| `baseline_momentum5` | 5 | 2722 | 50.22% | -0.1019% | -0.0907% |
| `baseline_momentum5` | 10 | 2722 | 51.47% | 0.2268% | 0.2017% |
| `baseline_momentum5` | 20 | 2425 | 47.13% | -0.7031% | -0.6268% |
| `baseline_macd_only` | 5 | 2109 | 51.87% | 0.1431% | 0.0986% |
| `baseline_macd_only` | 10 | 2109 | 52.54% | -0.0651% | -0.0449% |
| `baseline_macd_only` | 20 | 1852 | 48.33% | -1.0992% | -0.7485% |
| `soft_c_strict_ternary` | 5 | 840 | 50.83% | 0.0266% | 0.0073% |
| `soft_c_strict_ternary` | 10 | 840 | 53.33% | 0.1334% | 0.0366% |
| `soft_c_strict_ternary` | 20 | 698 | 53.72% | 0.3222% | 0.0827% |
| `structure_heavy_ternary` | 5 | 1185 | 52.91% | 0.0481% | 0.0186% |
| `structure_heavy_ternary` | 10 | 1185 | 54.01% | 0.1956% | 0.0757% |
| `structure_heavy_ternary` | 20 | 999 | 49.25% | -0.2730% | -0.1003% |
| `structure_heavy_long_only` | 5 | 499 | 42.89% | -0.3642% | -0.0594% |
| `structure_heavy_long_only` | 10 | 499 | 43.69% | -0.5744% | -0.0937% |
| `structure_heavy_long_only` | 20 | 469 | 43.28% | -0.8821% | -0.1521% |

### holdout

| variant | h | n_active | win_rate | avg_pnl_active | avg_pnl_all |
|---|---:|---:|---:|---:|---:|
| `baseline_always_long` | 5 | 170 | 50.59% | -0.6043% | -0.6043% |
| `baseline_always_long` | 10 | 0 | n/a | n/a | n/a |
| `baseline_always_long` | 20 | 0 | n/a | n/a | n/a |
| `baseline_momentum5` | 5 | 149 | 49.66% | 0.6752% | 0.5918% |
| `baseline_momentum5` | 10 | 0 | n/a | n/a | n/a |
| `baseline_momentum5` | 20 | 0 | n/a | n/a | n/a |
| `baseline_macd_only` | 5 | 106 | 61.32% | 2.0064% | 1.2511% |
| `baseline_macd_only` | 10 | 0 | n/a | n/a | n/a |
| `baseline_macd_only` | 20 | 0 | n/a | n/a | n/a |
| `soft_c_strict_ternary` | 5 | 58 | 62.07% | 0.2294% | 0.0783% |
| `soft_c_strict_ternary` | 10 | 0 | n/a | n/a | n/a |
| `soft_c_strict_ternary` | 20 | 0 | n/a | n/a | n/a |
| `structure_heavy_ternary` | 5 | 66 | 62.12% | 0.2591% | 0.1006% |
| `structure_heavy_ternary` | 10 | 0 | n/a | n/a | n/a |
| `structure_heavy_ternary` | 20 | 0 | n/a | n/a | n/a |
| `structure_heavy_long_only` | 5 | 17 | 82.35% | 0.6668% | 0.0667% |
| `structure_heavy_long_only` | 10 | 0 | n/a | n/a | n/a |
| `structure_heavy_long_only` | 20 | 0 | n/a | n/a | n/a |

## 5d / 20d contrast (locking weights)

Daily noise is large; prefer **5d (week)** and **20d (month)** when judging whether structure_heavy beats soft_c / baselines.

| window | metric | soft_c_strict_ternary | structure_heavy_ternary | delta (heavy−soft_c) |
|---|---|---:|---:|---:|
| selection | 5d win_rate | 50.83% | 52.91% | +2.08% |
| selection | 5d avg_pnl_active | 0.0266% | 0.0481% | +0.0215% |
| selection | 20d win_rate | 53.72% | 49.25% | -4.48% |
| selection | 20d avg_pnl_active | 0.3222% | -0.2730% | -0.5952% |
| holdout | 5d win_rate | 62.07% | 62.12% | +0.05% |
| holdout | 5d avg_pnl_active | 0.2294% | 0.2591% | +0.0297% |
| holdout | 20d win_rate | n/a | n/a | n/a |
| holdout | 20d avg_pnl_active | n/a | n/a | n/a |

## B0 verdict (weights still frozen for live)

- Selection **20d**: structure_heavy behind soft_c — keep as design, do not promote.
- Holdout **5d**: structure_heavy wr ≥ soft_c (short sample).
- Holdout 20d: **pending** more trading days.
- **Do not** write live strategy.json / assign_grade. B1=shadow_grade later; B2=live.


## Recommendation for next B0 iteration (still offline)

| Use case | Prefer | Why |
|---|---|---|
| Week lock (5d) | `structure_heavy_ternary` | +2.08pp wr / +pnl vs soft_c on selection; holdout 5d tied/slightly better |
| Month lock (20d) | **`soft_c_strict_ternary`** (structure-only) | soft_c 20d wr 53.72% / pnl +0.32% vs heavy 49.25% / −0.27% |
| Board 综合分 design | keep structure trio **0.40** > macd **0.08–0.10** | Formula direction OK; live not written |
| MACD period | keep **12/26/9** | No production 21-day MACD |

Optional next offline knob (not run this turn): drop overlay `w_macd` 0.10→**0.05** and board `macd`→**0.08** (give +0.02 to `wyckoff`), re-check selection 20d before any B1 shadow_grade.

## Artifacts

- `horizon_trades_detail.csv`
- `horizon_summary_by_variant.csv`
- `proposed_weights_structure_heavy.json`
- `FORMULA_structure_over_macd.md`
- `horizon_REPORT.md` (this file)

## Re-run

```bash
cd /workspace/etf_structure_features
python3 backtest/run_horizon_eval.py
```
