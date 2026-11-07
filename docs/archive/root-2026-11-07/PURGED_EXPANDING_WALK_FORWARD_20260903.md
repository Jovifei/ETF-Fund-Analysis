# Purged expanding walk-forward research — 2026-09-03

## Goal

Replace the optional global-model benchmark's single 80/20 holdout with multiple chronological out-of-sample folds while preserving the project's strict target-overlap leakage guard.

This remains a **research benchmark only**. It never writes production forecasts and never promotes a model automatically.

## Default fold contract

- 4 non-overlapping out-of-sample folds;
- 20 trading sessions per test fold;
- at least 150 leakage-safe training sessions in the first fold;
- training always starts at the first available session and expands as the test window rolls forward;
- for an `h`-session target, purge `h + embargo_sessions` sessions immediately before every test fold;
- no random shuffle;
- every exact train/purge/test boundary is persisted in the research artifact.

With the existing minimum 240-session research history, the longest configured 10-session target has exactly 150 leakage-safe training sessions before the first 20-session test fold when using four folds.

## Model fitting

Each fold trains its own quantile models using only data available before that fold's leakage guard. The current benchmark does not learn a scaler/encoder outside the model. If learned preprocessing is added later, it must be fitted **inside each fold only** and applied to that fold's OOS test data.

Metrics are stored both per fold and on the concatenated OOS predictions:

- q50 MAE;
- q10/q50/q90 pinball loss;
- 80% interval coverage;
- mean interval width;
- raw quantile-crossing rate before post-fit ordering.

## Open-source references

### `sameerjain0106/systematic-etf-research` — MIT

Adopted methodology: expanding walk-forward evaluation, target-overlap purge boundaries, fold-local preprocessing, and keeping the resulting OOS stream distinct from later forward observations. This project independently implements the same safeguards for its own data model; no source code is copied.

### `microsoft/qlib` — MIT

Qlib's rolling task generator explicitly supports an expanding training segment while validation/test segments roll forward, and its implementation warns against leaking future test observations into validation. The multi-horizon rolling generator also makes label-horizon leakage a first-class boundary concern. This project adopts those ideas without adding Qlib as a dependency or copying its implementation.

## What does not change

- production `ForecastService` remains unchanged;
- configured forecast horizons remain `1/3/5/10`;
- feature templates remain unchanged;
- holdings, signals, orders, providers and schedulers remain unchanged;
- `production_promotion` remains `false`.
