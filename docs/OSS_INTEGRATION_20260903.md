# Open-source integration audit — 2026-09-03

This change set borrows proven quantitative-research ideas without replacing the existing FastAPI/PostgreSQL architecture or vendoring large third-party systems.

## Remote branch audit

The current `main` already contains the substance of most recent feature branches. The completed local 14:30 workbench, signal-center foundation, multi-user auth, market-context/OCR, v0.7 qualification, and source-export branches are behind `main` or mainly contain stale automation/source copies, so they are not blindly re-merged.

`fix/reference-board-signal-consistency-v2` is recorded as a real merge parent so the branch is explicitly reconciled. Conflict resolution keeps the newer `main` decision-board/UI and current signal-grading semantics. Its more aggressive `bear_cont -> 减仓` behavior failed the existing grade-contract test and is therefore rejected instead of being forced into production.

## Open-source references reviewed

### microsoft/qlib — MIT

Adopted idea: horizon-aware chronological validation must purge training observations whose forward labels cross into the validation/test window. Longer prediction horizons require a larger pre-holdout gap.

Implementation here is original and dependency-free in `app.utils.time_split`. No Qlib source is copied and Qlib is not added as a runtime dependency.

### sameerjain0106/systematic-etf-research — MIT

Reviewed because its methodology closely matches this project's main risk: point-in-time research leakage. Useful patterns include expanding walk-forward evaluation, target-overlap purge boundaries, fold-local preprocessing, next-session execution assumptions, transaction-cost sensitivity, and append-only forward paper predictions. This integration adopts only the leakage-boundary principle now; the other checks are candidates for later atomic work.

### UFund-Me/Qbot — MIT

Reviewed for modular separation between data, strategy, backtest, execution, and notification layers. The current project already follows a similar separation, so no large dependency or code import is needed.

### polakowo/vectorbt — Apache-2.0 plus Commons Clause

Reviewed for cost-sensitive/vectorized backtest concepts only. No source code is copied and no dependency is added.

### ricequant/rqalpha — custom/non-commercial terms

Reviewed for event-driven backtest architecture only. No source code is copied and no dependency is added.

## Changes adopted in this integration

1. Record a real merge ancestry for the reviewed signal-consistency branch while resolving conflicts in favor of the newer `main` behavior.
2. Add a reusable horizon-aware purged holdout utility.
3. Apply that guard to the optional LightGBM/CatBoost global-model research benchmark.
4. Support optional embargo sessions and persist exact leakage-guard boundaries in research artifacts.
5. Add focused tests for split-boundary correctness.

## Deliberately deferred

- `QuoteSnapshot.pct_change` is stored in percentage-point units while some signal thresholds are decimal returns. The old branch attempted to normalize this, but the same branch also changed signal semantics and failed an existing contract test. Unit normalization should therefore be landed in a small dedicated PR with explicit unit tests rather than bundled with this merge.
- The production decision board and 14:30 point-in-time dataset use `1/3/5/10` horizons, while some older daily research modules still use `1/5/20`. That migration must update feature schemas, factor targets, model research, configuration, reports, and tests atomically; changing one JSON list would create false consistency.
