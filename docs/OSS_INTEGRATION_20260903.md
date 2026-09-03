# Open-source integration audit — 2026-09-03

This change set intentionally borrows proven engineering ideas without replacing the existing FastAPI/PostgreSQL architecture or vendoring large third-party systems.

## Remote branch audit

The current `main` already contains the substance of most recent feature branches. Branches such as the completed local 14:30 workbench, signal-center foundation, multi-user auth, market-context/OCR, and v0.7 qualification are behind `main` and are not re-merged.

`fix/reference-board-signal-consistency-v2` still contains one independently useful correction set. It is merged selectively: the current `main` UI and newer decision-board implementation are kept, while the signal-grade normalization/semantics are absorbed. This avoids rolling back newer dashboard work.

## Open-source references reviewed

### microsoft/qlib — MIT

Adopted idea: horizon-aware chronological validation must purge training observations whose forward labels cross into the validation/test window. Longer prediction horizons require a larger pre-holdout gap.

Implementation in this repository is original and dependency-free in `app.utils.time_split`. No Qlib source code is copied and Qlib is not added as a runtime dependency.

### UFund-Me/Qbot — MIT

Reviewed for modular separation between data, strategy, backtest, execution, and notification layers. The current project already follows a similar separation, so no large dependency or code import is needed.

### polakowo/vectorbt — Apache-2.0 plus Commons Clause

Reviewed for cost-sensitive/vectorized backtest concepts only. No source code is copied and no dependency is added because the licensing terms are not a good fit for indiscriminate reuse.

### ricequant/rqalpha — custom/non-commercial terms

Reviewed for event-driven backtest architecture only. No source code is copied and no dependency is added.

## Changes adopted in this integration

1. Normalize quote percentage-point returns before applying decimal-ratio signal thresholds.
2. Keep the latest main decision-board/UI implementation while recording a real merge ancestry for the useful signal-consistency branch.
3. Add a reusable horizon-aware purged holdout utility.
4. Apply that guard to the optional LightGBM/CatBoost global model research benchmark.
5. Report the purge/embargo bounds in research artifacts for auditability.
6. Add focused tests for the time-split boundary rules.

## Deliberately deferred

The production decision board and the 14:30 point-in-time dataset already use `1/3/5/10` horizons. Some older daily research modules still use `1/5/20`. That mismatch should be migrated as a separate atomic change across feature schemas, factor targets, model research, reports, configuration, and tests. Changing a single JSON list here would create false consistency and is therefore intentionally avoided.
