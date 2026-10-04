# Feature maturity and TD evidence audit — 2026-10-04

Base for this stage: `1e7dff77a38fdf078adbc99798ee13182ca9fc0b`
Branch: `codex/post-release-indicator-audit-20261004`

## Confirmed validity defect

Several project indicator functions intentionally expose neutral warm-up placeholders for display: RSI=50, ADX/DMI=0, CCI=0, Williams %R=-50, MFI=50, CMF=0 and RSRS z-score=0. The formulas themselves remain project definitions, but the feature pipeline previously allowed some of these placeholders to enter factor/forecast coverage as if they were mature observations.

MFI/CMF already had volume-window masks, but those masks did not require valid OHLC in the same window. ADX/DMI, CCI/WR and RSRS had no price-maturity mask. RSI display warm-up likewise remained numeric in the feature frame.

The research feature frame now separates display semantics from research maturity. Price-dependent features are set to NaN until their declared input/maturity window is complete, and price gaps contaminate the relevant price/money-flow windows instead of becoming neutral observations. In particular:
- RSI N needs N+1 price bars because it consumes close differences.
- DMI needs the configured directional window plus the prior bar; ADX needs a full subsequent DX window.
- CCI/WR use their configured rolling windows.
- MFI uses price+volume and an extra prior typical-price observation; CMF uses complete price+volume windows.
- RSRS beta/R²/raw require the regression window; z-score/right-skew require enough valid regression outputs for the existing z-score minimum-period rule.
- OBV flow keeps its separate offset-invariant recent-window contract.

The validity policy advances to `raw-dependency-and-maturity-mask-v2`.

## Version isolation

Because feature coverage and some short-history scalar availability change, identities advance to:
- indicator `ind-v0.7.6-maturity-mask`
- feature schema `feature-store-v0.7.6-maturity-mask`
- forecast `similarity-corridor-v0.7.7-maturity-mask`
- strategy engine `strategy-family-v0.5.3-maturity-mask`

Older persisted outputs must fail compatibility rather than be relabelled.

## TD evidence semantics

The project TD Setup counter may contribute evidence inside the reversal-family score, but TD alone is not allowed to emit an oversold-reversal observation. The combined RSI/WR/TD observation is renamed `超跌衰竭观察` and its reason explicitly states that TD Setup is exhaustion evidence, not reversal confirmation. Scoring thresholds are unchanged.

## Classification

This stage fixes a feature-validity defect, not the underlying external-library definition differences. ADX/DMI zero-fill, MFI/CMF neutral display fills and RSRS display zero remain permitted presentation conventions; they are no longer silently counted as mature research features.
