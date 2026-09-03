# Scheduler resilience contract — 2026-09-03

This change keeps the existing lightweight PostgreSQL-backed scheduler and adopts a few proven scheduler semantics without adding APScheduler, Celery, Dagster, Redis, or another daemon dependency.

## Borrowed design patterns

- APScheduler: a scheduled time may still run inside a bounded **misfire grace**; multiple recently due times can be **coalesced** to one latest run.
- Dagster daemon: a recently failed tick is retryable instead of being permanently consumed by the first failed submission.
- Existing project rule: `DecisionBoardSlotRun.slot_key` remains the durable idempotency key across process restarts.

No external scheduler code was copied. Only the behavior was adapted to this repository's existing task/audit model.

## Decision-board slot contract

- Existing Shanghai wall-clock slots remain unchanged.
- Exact slot execution remains valid.
- The scheduler additionally accepts the latest slot delayed by at most **180 seconds**.
- If more than one slot is inside that grace window, only the latest slot is selected (coalescing).
- The persisted claim key is the scheduled wall-clock slot, not the delayed execution time. A 14:31 execution of the 14:30 slot is still audited as `YYYYMMDD-1430`.
- A successful slot claim remains idempotent across restarts and concurrent scheduler processes.
- A slot whose task execution fails releases its claim so it may retry during the remaining grace window.

This specifically prevents a slow provider call or scheduler tick drift from permanently skipping the 14:30 decision slot.

## Critical-path ordering

The scheduler now evaluates the decision-board critical path before optional market-context/news work.

A decision-board refresh already performs quote refresh + provisional capture, so a standalone quote refresh is skipped while an exact/recent board slot or queued manual board refresh is active. This avoids duplicate provider calls.

## Quote cadence

The existing runtime setting `quote_refresh_minutes` is now consumed by the scheduler during an open price session between decision-board slots.

- Default production value remains 3 minutes.
- The cadence prefers the last **terminal attempt** (success/failure/partial) to avoid hammering an unavailable upstream every 30 seconds, with the historical last-success value as a compatibility fallback when no terminal attempt exists.
- Board-slot refresh remains the authoritative quote -> provisional -> snapshot path for decision snapshots.

## Failure and transaction isolation

Every scheduler task continues to create its normal durable `TaskRun` audit record through `TaskService`.

`TaskExecutionError` and `TaskBusyError` are caught at the scheduler orchestration boundary so one task cannot kill the remainder of the tick.

The tick result deliberately preserves the existing field meaning:

- `executed`: tasks **attempted** during this tick, including failed attempts;
- `failures`: the failed subset with sanitized failure classes.

`TaskService.run()` owns rollback and durable failure-audit recovery for task failures. The scheduler does not perform a second rollback. Instead, every successful task is committed immediately at the scheduler boundary. Therefore a later independent failure cannot erase an earlier successful quote refresh, decision snapshot, or after-close layer from the same tick.

In particular:

- market-context failure cannot block quote/decision work;
- a failed signal refresh cannot prevent later independent scheduler work;
- a failed news refresh cannot block after-close bars/indicators/forecast/report work;
- after-close layers are attempted independently and each failure remains explicit in `TaskRun` and in the scheduler tick's `failures` summary.

The scheduler does not suppress unknown process/database failures outside the durable task boundary; the outer daemon loop still logs and retries the next tick.

## Explicit non-goals

- No automatic order execution.
- No change to five-grade semantics.
- No change to 1/3/5/10 forecast horizons.
- No change to quote timestamp qualification.
- No new distributed queue or scheduler dependency.
