# Research horizon alignment — 2026-09-03

## Goal

Align the daily forecast/research stack with the 14:30 decision product's existing forecast contract: `1/3/5/10` trading sessions.

## What changes

- `forecast.horizons` and `factor_analysis.horizons` are both `1/3/5/10`.
- A shared code-level contract rejects drift between those two configuration sections.
- `FactorAnalysisService` generates forward-return labels for every configured horizon instead of hard-coding `1/5/20`.
- `GlobalModelResearchService` benchmarks the same configured horizons and applies the previously-added horizon-aware purge to 1, 3, 5, and 10-session labels.
- `HORIZON_FEATURES` explicitly supports 3 and 10 sessions.
- The feature schema and forecast version are bumped so persisted research artifacts remain auditable.
- A regression test verifies that the strategy config and the 14:30 workbench config stay aligned.

## Conservative feature reuse

This change does not claim new feature discovery. To avoid mixing horizon alignment with feature-selection optimization:

- 3-session forecasts reuse the existing swing/5-session feature template.
- 10-session forecasts reuse the existing medium/20-session feature template.
- 20-session feature support remains in code only for reproduction/readability of already-persisted v0.7 research artifacts; it is no longer part of new configured forecast/factor runs.

## What does not change

Trailing input windows such as 20/60/120-day momentum, RPS, drawdown, box, or chip features remain unchanged. Those are lookback features, not prediction horizons.

The backtest rebalance period and holding rules also remain unchanged. Changing those would be strategy-design work and requires separate validation.

## Validation expectations

Before merge, CI must cover the full repository suite plus the new horizon-contract tests. The most important behavioral checks are:

1. forecast and factor configs are exactly `1/3/5/10`;
2. 14:30 `forecast_horizons` is the same contract;
3. 3/10 feature templates resolve to non-trivial feature sets;
4. factor/global-model code consumes the aligned configuration rather than hard-coded tuples;
5. legacy 20-session feature lookup remains available only for historical artifact reproduction.
