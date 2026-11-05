# Concrete knobs that could take structure_v1 soft weights

Source: `/workspace/etf-p1/config/strategy.json` (repo copy; live on Jovi is separate — do not edit live).

| Knob | Current | Soft-weight use |
|---|---|---|
| `signal_grade.j_add_cap` / `j_high` / `stall_return` / volume_* / rsi_* / macd_approach_hist | five-档 thresholds | **Do not touch** until grade replay exists |
| `signal_grade.board_score_weights` {volume,ma,macd,kdj,rsi,td,momentum} | sum≈1.0 | Add `wyckoff`/`dow`/`atr_inv` keys later; renormalize |
| `signal.entry_score` / `probe_score` / `reduce_score` / `hard_reduce_score` | 68/58/38/28 | Overlay shift by combined structure score (points) |
| `signal.portfolio_exposure_caps` | low/normal/high/extreme | Map `atr_risk_bucket` → cap |
| `signal.forecast_risk_adjustment.*` | enabled | Parallel ATR dampener |
| `backtest.factor_weights.structure` | 0.04 | Bump after validation (rotation backtest, not five-档) |
| `strategy_engine.family_weights.structure` | 0.10 | Same |
| **NEW** `structure_soft_weight` | — | Preferred: w_wyckoff/w_dow/conf_floor/buy_thresh/atr_scale from proposed_weights.json |

assign_grade() itself is rule-based (KDJ/MACD/MA/volume) with no numeric soft blend today.
ETF Bot confirmed: no five-档 historical win-rate CLI — structure overlay harness is the correct Phase B path.
