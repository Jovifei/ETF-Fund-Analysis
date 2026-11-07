# Canonical current-decision source contract — 2026-09-03

## Why

The decision board and Signal Center must not create two competing **current** conclusions for the same ETF. Historical `SignalSnapshot.state`, current five-grade classification, ranking scores, and take-profit heat are useful evidence, but they have different responsibilities.

## Source precedence

Resolve the current user-facing state **per instrument** in this order:

1. latest `DecisionBoardSnapshot.rows[].grade` when that instrument has a valid grade;
2. deterministic `SignalGradeService` output when the latest board snapshot is absent or does not contain that instrument;
3. `SignalSnapshot.state` only as a last-resort compatibility/audit value.

The first two sources are canonical. The third is not.

A partial decision-board snapshot therefore produces explicit `mixed_per_instrument` lineage instead of silently pretending every ETF came from the same source.

## Ranking and history

- Signal Center coefficient may rank members inside a current category.
- Coefficient and heat must not move a canonical `观望/减仓` ETF into `opportunity`, or a canonical `可加仓/可入场/可试探` ETF into `risk`.
- `take_profit` remains an orthogonal overheat research view.
- Historical curves continue to use historical `SignalSnapshot` records and are labeled separately from the current canonical state.

## Open-source ideas reviewed

### `sameerjain0106/systematic-etf-research` — MIT

Borrowed concept: distinguish canonical/frozen research outputs from later forward observations, keep source lineage explicit, and avoid rewriting a historical signal merely because a later layer has more information. Its append-only forward-paper workflow is a useful model for separating a current decision from historical audit evidence.

No source code is copied.

### `microsoft/qlib` — MIT

Borrowed concept: rolling/online workflows explicitly separate task generation, historical segments, and the model/result used for the current online decision. This supports making the current-decision source an explicit contract rather than an implicit side effect of ranking code.

No Qlib source code is copied and no dependency is added.

## Safety boundary

This change does not alter `SignalGradeService.assign_grade()`, prediction algorithms, holdings, database schema, providers, schedulers, or order execution. It only makes current-state resolution deterministic, per-instrument, and auditable.
