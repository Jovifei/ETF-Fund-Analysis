# Indicator definition contract audit — 2026-10-04

Base/release SHA: `efc0898dd13d386b8b4d91854323e36ceffa0630`
Audit branch: `codex/post-release-indicator-audit-20261004`

This post-release code-only audit freezes project definitions that intentionally differ from external libraries. It does not change production forecast qualification, does not deploy, and does not claim TA-Lib/CZSC equivalence.

## Frozen project definitions

- MACD histogram is `2 * (DIF - DEA)`; EMA uses pandas EWM with `adjust=False` from the first observation.
- ATR uses project Wilder-style EWM `alpha=1/window`, `adjust=False`, `min_periods=window`.
- ADX/DMI exposes zero-filled warm-up values. This remains a definition difference rather than being silently rewritten.
- OBV begins at zero, then cumulatively adds/subtracts volume by close direction. Because downstream percentage slope depends on the starting offset, this convention is now explicit.
- KDJ uses rolling extrema from the first available row, K/D seeds of 50, and an unclipped J value.
- CMF treats a flat high-low bar as neutral multiplier zero and fills unavailable warm-up with zero.
- RSRS is OLS(high ~ low), raw score `beta * R²`, population-ddof rolling z-score with the current minimum-period rule.
- TD is only the project's close[t] vs close[t-4] Setup counter. It is **not** a complete TD Sequential implementation and must not be described as a trading/turning-point signal.

## Runtime wording correction

TD calculation/counts are unchanged. Structured TD snapshots now carry `definition_version`, `scope=setup_only_not_full_td_sequential`, and `actionable=false`. User-visible legacy labels were reduced from "top/bottom signal / reversal" language to "trend-exhaustion setup reference / not a trading signal".

## Classification

ATR/MACD/ADX-DMI/OBV initialization differences remain `DEFINITION_DIFFERENCE`, not confirmed formula bugs. KDJ/CMF/RSRS/TD are project-defined contracts. The new regression suite freezes these semantics so a future formula change must be intentional and version-reviewed.


## Follow-up confirmed bug: OBV percentage slope

The cumulative OBV starting offset itself remains a definition difference. A separate downstream bug was confirmed: the public `obv_slope_5` feature used `OBV.pct_change(5)`. Percentage change of a cumulative series is not invariant to an arbitrary additive starting offset, and zero denominators were converted through inf/NaN to 0. That feature feeds forecast/factor/strategy research.

The compatibility field name remains `obv_slope_5`, but its definition is now the bounded five-session net directional volume balance:

`sum(sign(close.diff()) * volume, 5) / sum(abs(volume), 5)`

It is dimensionless, offset-invariant and bounded to [-1,1]. Existing strategy thresholds retain their intended sign/magnitude interpretation. Unknown volume in the recent window remains unknown rather than becoming zero. Because semantics change, indicator, feature schema, forecast and strategy-engine identities are all advanced; old persisted results must fail version compatibility rather than be relabelled.
