# R4C M3B-A2 R1 — blocked identity and monthly lineage repair

Date: 2026-09-30. C2C task: `c2c_a1d7`, follow-up iteration 67. Base: pushed A2 head `8b5440142c183762d202bc8c0e5a69830f0a3635` / tree `59d954885a9df3785997dbcfdfb5cc922f714df2`.

## Remote review and authorization

Iteration 66 exact-head review returned `M3B_A2_DECISION=CHANGES_REQUIRED` and retained the technical route. The reviewer read the released identity/diff/test evidence and confirmed the final GitHub head. Two bounded gaps remain before A2 can pass:

1. If the prerequisite D freeze is blocked for a W/M request, `_freeze_period_chan_input()` currently returns the D logical series, revision and source-bar IDs as if they were period identities. A blocked W/M result must propagate the bounded reason/detail but leave period `logical_series_id`, `input_revision_id`, `source_bar_ids`, and `constituent_source_bar_ids` empty. `price_basis_id` and `source_as_of` may be retained if known.
2. The A2 historical-correction lineage test exercises weekly aggregation only. Add a monthly regression with at least two month aggregates: correct one persisted D constituent and its `quality_hash`; the affected month ID and lineage must change, the unrelated month ID and lineage must stay stable, the M logical series and price-basis namespace must stay stable, and the input revision/hash must change.

No M3B-B work is authorized until this A2 follow-up passes exact-head remote review. The review explicitly keeps M3B-C, M4, main integration, and production false.

## Frozen implementation

- Repair only blocked W/M metadata propagation in `backend/app/research/chan_input.py`.
- Keep weekly/monthly aggregation and identity formulas unchanged.
- Do not change the D identity ledger, `_period_source_bar_id`, period config, `aggregate_bars()` semantics, W/M logical-series formula, M2 `input_hash`, corporate-action arithmetic, or settlement rules.
- Add regression coverage in `backend/tests/test_chan_m3b_input.py` for blocked W/M identity metadata and monthly historical correction lineage.
- Update only the stage receipt, `STATUS.md`, `HANDOFF.md`, and `tasks/todo.md` for this handoff.
- No `candle_periods.py`, provider, adapter, worker, API, UI, persistence/schema, main, production, real-data qualification, actionable, or trading changes.

## TDD and verification

1. Add the two regressions first and capture the expected failure on the blocked W/M identity fields.
2. Run the A2-focused Chan test file; implement the minimal blocked-result metadata correction; rerun until green.
3. Run `test_chan_m2_contract.py`, `test_chan_m3_persistence.py`, and the relevant R4A corporate-action/history tests.
4. Re-run M2 Windows/Linux gates (25/25 each), adapter semantic digest, and R5.2.1 Windows/Linux digest/collision validators. Expected digests and collision gates remain frozen. This host's isolated Windows interpreter is Python 3.12.10; the Linux runner is Python 3.12.14.
5. Run Ruff, compileall, Node syntax, scoped secret scan, and `git diff --check`.
6. If `candle_periods.py` or another shared R4A/runtime file must change, stop for a new remote plan; the full Windows suite then becomes mandatory. Otherwise the focused gate is the planned verification.
7. Update receipts/status/handoff/todo with the blocker, repair, test evidence, and `NOT_DEPLOYABLE_SUBSTAGE`; commit/push the exact code/test candidate and documentation, read back GitHub tip, release bounded evidence, then request another exact-head remote review.

## Acceptance boundary

`M3B_A2_DECISION=PASS` requires: blocked W/M results contain no D identity metadata; monthly correction changes only the containing aggregate identity/lineage while preserving price-basis and M logical-series namespace; all prior A2 tests and frozen cross-platform gates pass; GitHub head and released evidence match. Until the remote returns PASS, M3B-B remains NO-GO.

Deployment disposition remains `NOT_DEPLOYABLE_SUBSTAGE`: no runtime consumer exists. Production is unchanged, real-data qualification is `UNKNOWN`, and `actionable=false`.

## Iteration 67 execution evidence

- TDD RED: two parameterized blocked-W/M cases failed because the returned `logical_series_id` was the D identity; the new two-month correction test passed against the generic implementation and now locks the missing coverage.
- Minimal code change: stopped passing D logical/revision/source IDs into the W/M blocked result. Safe bounded reason/detail and known basis/as-of fields remain propagated.
- Focused regression: 99 collected, 95 passed, 4 environment skips, 0 failures/errors; all 29 `test_chan_m3b_input.py` tests pass. New monthly assertions confirm only January's aggregate/lineage changes after a January D correction; February, M namespace, and price basis remain stable; revision/hash change.
- Windows M2 contract: 25/25 on Python 3.12.10/CZSC 1.0.1. Windows adapter digest is unchanged. R5.2.1 Windows validator reports the frozen history/semantic digests, 0/0/0 collisions, and injected collision detected.
- Linux M2 contract and validators: 25/25 on Python 3.12.14/CZSC 1.0.1; frozen M2/R5 digests and collision gates unchanged.
- The first Windows mirror attempt failed before meaningful collection because the isolated mirror omitted `backend/app/utils/hashing.py`; after copying that exact dependency, the same gate passed 25/25. This is retained as harness history, not a product failure.
- Ruff, Python 3.13.14 compileall, Node syntax, scoped secret scan, and diff-check passed. `candle_periods.py` and shared R4A/runtime code are unchanged; no full repository suite was required by the remote plan.
- Code/test commit: `9f935a864f5071debbd66b0f6d4cc40e68a73a2d` / tree `04294de8952b45f4245cd2bc0b3e569322fa9857`, parent `8b5440142c183762d202bc8c0e5a69830f0a3635`. It changes only `chan_input.py` and its tests. Pending: docs-only receipt commit, GitHub push/readback, bounded evidence release, and second exact-head remote review. A2 remains `CHANGES_REQUIRED` until that review returns `PASS`.
