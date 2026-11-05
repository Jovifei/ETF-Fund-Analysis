# FORMULA — structure_decision_v1 (structure over MACD)

**Status:** B0 research design only · **do not apply to live**  
**Zone:** Asia/Shanghai  
**Sources:** `/workspace/etf-p1/config/strategy.json` (box copy `signal-v0.7.4`); live may be `v0.7.5` — MACD periods unchanged per ETF Bot.

---

## 1) Production MACD finding (user asked about “21日”)

| Item | Value |
|---|---|
| Box `indicator.macd` | **fast=12, slow=26, signal=9** |
| Backend default (`indicators.py`) | same 12/26/9; hist=`2*(dif−dea)` |
| Production **21-day MACD** | **Does not exist** |
| Likely confusion | MA20 / 20d forward (month-ish) / research slow-MACD idea |

Optional slow MACD (e.g. 21/55/9) may be studied **旁路** later; **never** flip live `indicator.macd` in B0.

---

## 2) Current Board 综合分 weights (box; display only)

`signal_grade.board_score_weights` (sum≈1.0) — **does not** drive five-档 `assign_grade`:

| volume | ma | macd | kdj | rsi | td | momentum |
|---:|---:|---:|---:|---:|---:|---:|
| 0.15 | 0.20 | **0.20** | 0.15 | 0.15 | 0.05 | 0.10 |

Five-档 remains the rule tree (KDJ/MACD cross / volume / MA), not this blend.

---

## 3) Proposed bypass — `board_score_weights` structure-heavy

**Only** if/when forked in a旁路 worktree. Affects Board 综合分 only. **assign_grade untouched.**

| key | current | **structure_heavy** |
|---|---:|---:|
| `wyckoff` | — | **0.14** |
| `dow` | — | **0.16** |
| `atr_inv` | — | **0.10** |
| `macd` | 0.20 | **0.10** ↓ |
| `ma` | 0.20 | 0.14 |
| `volume` | 0.15 | 0.10 |
| `kdj` | 0.15 | 0.10 |
| `rsi` | 0.15 | 0.08 |
| `momentum` | 0.10 | 0.05 |
| `td` | 0.05 | 0.03 |
| **sum** | 1.00 | **1.00** |

**Constraint satisfied:**  
`wyckoff + dow + atr_inv = 0.40 > macd = 0.10`

`atr_inv` board feature (when wired): map `atr_risk_bucket` → score  
`{low:+1, mid:+0.35, high:−0.35, extreme:−1, unknown:0}`.

---

## 4) Soft overlay used in offline walk-forward (`structure_heavy_*`)

This is the **decision** signal evaluated on 5d/20d — parallel to Board weights, not a live write.

```
# inner structure combo (same wy/dow mix as frozen soft_c)
structure_raw = (0.40 * wy_score * wy_conf + 0.60 * dow_score * dow_conf)
                / (0.40 + 0.60)
if avg(wy_conf, dow_conf) < 0.45: structure_raw = 0
structure_score = structure_raw * ATR_STRICT[atr_risk_bucket]
# ATR_STRICT: low=1.0, mid=0.9, high=0.4, extreme=0.0, unknown=0.4

# MACD proxy (production 12/26/9, causal ≤ as_of)
macd_score = tanh( 0.75 * macd_hist / max(atr14, |close|*0.01) )

# structure dominates MACD (0.40 vs 0.10); override when |structure| high
w_s, w_m = 0.40, 0.10
if |structure_score| ≥ 0.45: w_m *= 0.5
decision = (w_s * structure_score + w_m * macd_score) / (w_s + w_m)

# ternary position
+1 if decision ≥ 0.28
−1 if decision ≤ −0.28
0  if |decision| < 0.10
±0.5 otherwise
```

**Frozen soft_c** (reference, no retune):  
`w_wy=0.40, w_dow=0.60, conf_floor=0.45, buy_thresh=0.30, flat_band=0.12`, ATR_STRICT, **no MACD term**.

---

## 5) Horizon policy for locking weights

| Horizon | Meaning | Role |
|---|---|---|
| 5d | ~1 trading week | Primary short lock |
| 10d | intermediate | Secondary |
| 20d | ~1 trading month | **Preferred** for weight lock (less daily noise) |

Holdout 20d needs ≥20 sessions after first holdout as_of — currently truncated; re-run later.

---

## 6) Phase gates

| Phase | Action |
|---|---|
| **B0** (now) | Soft overlay + 5d/20d offline; Board weight **design only** |
| B1 | `shadow_grade` parallel (still not live) |
| B2 | Live fork of `board_score_weights` / `structure_soft_weight` — needs explicit promote |

Forbidden in B0: live `strategy.json`, `assign_grade`, `CONFIG_HASH`, CloudAgent.

---

## 7) Artifact pointers

- `proposed_weights_structure_heavy.json` — numeric dump of this formula  
- `horizon_REPORT.md` — selection/holdout 5d/20d tables  
- `overlays.py` — `BOARD_SCORE_WEIGHTS_STRUCTURE_HEAVY`, `STRUCTURE_DECISION_V1`  
- Frozen soft_a/b/c: `proposed_weights.json` (unchanged by horizon eval)

## 8) Offline result note (2026-11-05 Asia/Shanghai)

Selection 2026-06-10→10-22:
- **5d**: structure_heavy beats soft_c (wr 52.91% vs 50.83%).
- **20d**: soft_c beats structure_heavy (wr 53.72% vs 49.25%) — MACD tilt hurts month horizon in this window.
Holdout 5d (short): roughly tied (~62%). Holdout 20d: pending.

→ Keep Board design (structure trio 0.40 > macd 0.10). For **month weight lock**, prefer soft_c / lower `w_macd` until holdout 20d exists. Still **not** live.
