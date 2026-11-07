# Single ETF decision surface and forecast semantics — 2026-09-03

## Problem closed by this change

The repository historically exposed several research surfaces and two different current-action engines:

- `/` rendered the WorkBuddy decision board and used the canonical five-grade decision.
- `/legacy` rendered the older full dashboard.
- `/workbench/kline` rendered a separate K-line page.
- `/api/workbench/1430/*` calculated a separate six-component score and converted it into `买入候选 / 可试探 / 持有观察 / 减仓候选 / 回避`.

That made it possible for one ETF to display two different current recommendations even when both pages were reading the same database.

## User-facing surface contract

There is one user-facing ETF research surface: `/`.

Compatibility page routes `/legacy`, `/workbench/1430`, and `/workbench/kline` redirect to `/`. The separate static assets and APIs may remain for backward-compatible automation/report consumers, but they are not independent current-decision UIs.

The unified page keeps the useful information rather than removing it:

- one ETF per row;
- canonical five-grade action;
- volume, MA, MACD, KDJ, TD9, RSI, sector breadth and 1/3/5/10 forecast context;
- red/yellow/blue/green warning semantics;
- ETF detail drawer with historical/future-scenario candles, support/resistance and indicator interpretation.

## One current decision contract

Every current-action consumer must resolve the action in this order:

1. latest `DecisionBoardSnapshot.rows[].grade`;
2. current `SignalGradeService` grade if the decision snapshot lacks the ETF;
3. legacy `SignalSnapshot.state` only as a last-resort audit compatibility source.

The compatibility 14:30 service no longer owns a second `_action()` threshold engine. Its six-component `research_score` remains read-only explanatory/ranking context and is explicitly tagged `explanatory_ranking_only_not_current_decision`.

## One forecast source contract

The compatibility 14:30 API no longer recomputes a separate similarity forecast on every read. It projects the persisted `ForecastSnapshot` rows used by the canonical board for horizons 1/3/5/10.

This eliminates a second forecast answer caused by different feature context or calculation time.

## Probability wording

The baseline similarity model estimates `p_up` as the inverse-distance weighted fraction of historical neighbours whose forward terminal return was positive.

Therefore:

- `calibration_status != calibrated`: `p_up` means **weighted historical-neighbour up frequency**. It is not presented as a calibrated future probability.
- `calibration_status == calibrated`: the UI may label it **up probability**.

The compatibility API exposes `p_up_semantics`, `historical_up_frequency`, `up_probability`, and `probability_calibrated` so clients do not have to infer the distinction.

The explanatory forecast score also shrinks weak/uncalibrated evidence toward neutral 50. `conf < 40` remains neutral. This score never changes the canonical five-grade action.

## Open-source design references absorbed

### Microsoft Qlib / Alpha158

Qlib treats future return as the explicit supervised label and builds a broad rolling feature library (returns, rolling statistics, trend/linearity, extremes, volume and price-volume relationships) around that target. The useful pattern for this project is **target-first + point-in-time features + out-of-sample evaluation**, not presenting a technical-rule score as a probability.

### systematic-etf-research

The project uses point-in-time data, expanding walk-forward evaluation, label-overlap purge, fold-local preprocessing and next-session/cost-aware evaluation. It also checks whether apparent alpha is explained by beta exposure. This reinforces the repository's existing purged walk-forward direction and highlights remaining benchmark-beta/correlation diagnostics.

No external project source code is copied by this change; only methodology and interface/governance patterns are adopted.

## Explicit non-goals

This change does not:

- change `SignalGradeService` thresholds or `bear_cont` semantics;
- promote an unvalidated new factor into the canonical grade;
- claim that the current similarity baseline is calibrated;
- change the 1/3/5/10 horizon contract;
- connect to a broker or execute orders.

Potential new factors (linear slope/R²/residual, time-since-extreme, price-volume correlation, up/down-day fractions, benchmark beta/correlation) must first earn inclusion through point-in-time IC/OOS/walk-forward evidence.