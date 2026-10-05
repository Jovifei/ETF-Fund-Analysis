# Current decision-board temporal read contract — 2026-10-05

Base: `6608602093d27704b4bebc8fb2affe36f65cfc32` on `codex/post-release-indicator-audit-20261004`.

## Confirmed read defect

The latest persisted board was not necessarily usable as current evidence:

- CurrentDecisionService selected the newest board by generation time, then explicitly read that ID without a current-time check.
- SignalCenter independently selected the newest board and consumed its raw payload, bypassing both version/config projection and time validation.
- Default DecisionBoardService reads exposed future-generated snapshots through the current board route too.

Isolated persisted-database regressions reproduced five failures across these routes. The old-contract SignalCenter case displayed its original `可入场` grade; a future board was also returned as current. These are software read-contract defects, not proof of real-world trading eligibility.

## Shared contract

`current-board-read-v1-temporal` distinguishes the two existing purposes:

- A default board read (no explicit snapshot ID) validates the latest selected row against application-market time.
- An explicit snapshot ID remains the historical inspection route. Passing `at` additionally applies the current/read-time constraint to that selected ID.
- CurrentDecisionService supplies that read reference even when resolving an ID. SignalCenter delegates to this shared service rather than reading raw payload JSON.
- A future latest row yields an empty, blocked board carrying its original snapshot ID and reason `snapshot_after_read_time`. It never silently falls back to an older board.
- Naive SQLite datetime readback is interpreted in the configured market timezone, consistently with existing current snapshot contracts. Equivalent aware UTC instants and the exact boundary are allowed.
- Legacy version or config identity continues through the established projection: the current grade is `数据异常`, with the original grade preserved only as historical evidence.
- Reads do not insert/update/delete stored boards or invoke a Provider.

SignalCenter version advances to `signal-center-v0.3.3-current-board-contract`. Its strategy-config hash change intentionally makes prior hash-bound current snapshots incompatible until the normal authorized pipeline recomputes them. No formula, score weight, probability calibration or threshold is changed.

## Fixture order independence

The previous stage recorded three additional failures when SignalCenter/history preceded DecisionBoard tests. This stage preserves their assertions and repairs their test setup:

- Both single-instrument tail cases and the official-split case use the existing isolated schema/session fixture. Their `refresh_all.created == 1` assertion is meaningful instead of depending on unrelated enabled instruments.
- The provisional-input case owns an initially empty provisional-input table and restores the transaction in `finally`; its exact count and unchanged DailyBar assertions stay intact.
- The missing-indicator case removes all snapshots for its target instrument, not an arbitrary single historical snapshot, then restores the transaction in `finally`.

The first isolated candidate passed all three affected cases plus their preceding modules (34/34). The expanded candidate exposed the same global-count assumption in the official-split case (66/67); that retained failure motivated applying the same isolation to it. Neither result is relabelled a final full pass.

## Verification

- New contract regression: 5 failed / 3 passed before the fix; 8/8 passed after the initial correction.
- Extended contract tests: 13/13 passed, including independent version/config mismatch, equivalent UTC boundary, SQLite readback, preserved historical inspection, no older-board fallback and no dirty/new/deleted ORM state.
- Full-suite, ordered multi-module and independent review results pending the frozen candidate.

No production deployment, real data refresh, provider activation, account change or investment transaction is part of this stage. Real-data qualification remains UNKNOWN, actionable=false and forecast calibration remains not_calibrated.

### Independent review

Independent review PASS for the six frozen source/test/config files. Reviewer reran the 13 contract cases: 13 passed, exit 0. The 120 existing DecisionBoard assertions remain 120; the only assertion expression adaptation uses the cached equivalent instrument ID after deletion. Review verified the current/historical split, no older-board fallback, row-copy projection, config-hash invalidation and transaction cleanup. Full-suite and ordered regression remain separate pending gates.

Frozen SHA-256 identities:

- current_decision_service.py: `3ca79833446afbc28167581038b3a65c9a99447e76eb991f51bd898ee53b0b59`
- decision_board_service.py: `dae9fa324d5981419b0b1df5b0386f665f513872d9f296c70bd4f01611d9ad04`
- signal_center_service.py: `2fbd59a616517fcd1b91373e47c8a88d0b93ce6869915f1a593adbc5af54aa19`
- test_current_board_contract.py: `7efead548961fc8908b0e3822f5c1981afe742f358ca99cbc333d6fbe9f2d683`
- test_decision_board.py: `e126c546f087e4ad24256e334b614ae210fa666135d965632ca6ed71573f5c2c`
- strategy.json: `676792372ce771e7e86fe8481e219cbc032ba6b72ff7fbf4e5293995ec76c668`

### Expanded integration findings retained

The first ordered suite completed with 109 passed / 1 failed out of 110. The remaining failure was an adapter regression: the common reader correctly blocked the future board, but instrument_detail lost the existing per-instrument reason and reported `decision_not_generated` instead of `decision_snapshot_after_read_time`.

The final adapter uses one `read_latest(at=read_as_of)` and a pure `instrument_from_payload` projection shared with `read_instrument`. A blocked payload retains only normalized instrument codes, not future grades/prices; a detail reason is mapped only when the requested instrument belongs to that blocked board. A missing board or an absent instrument remains `decision_not_generated`. New tests cover that distinction and a board valid at an explicitly historical cutoff. No historical-ID bypass or second read is used.

The first full run completed with a separate random fixture failure: Chan's `uuid % 10000` test code collided at `597050.SH`, with a consequent teardown transaction error. The JUnit report retained 1,750 entries (including the duplicate teardown-error entry), 11 skips, 1 failure and 1 error. A deterministic repeated-entropy regression reproduced the UNIQUE failure; the Chan helper now allocates against actual occupied codes while preserving explicit codes and prefixes. Its original quantity/qualification assertions are unchanged.

The adapted/final focused set passed 17/17. The new frozen full and ordered suites are rerunning; previous review hashes for changed files are historical only.

### Adapted candidate independent review

The adapted candidate passed independent actual-diff review and an independent 17/17 rerun (new current-board module, original v103 future-reason regression and deterministic Chan-code regression). The new projection is provider/DB-free and does not mutate the source payload. Chan's original assertions were not deleted.

Updated frozen SHA-256 identities (superseding only these files' earlier hashes):

- decision_board_service.py: `d3f296a638042d816486d7262b1aba653a50fbd80a1518cacfc2b1b1aa5356e1`
- workspace/read_model.py: `82b7f8f5052920132e0ff7fb1fc19eaa6ec4ebfc73cc946408588c07644d86c3`
- test_current_board_contract.py: `4d6bc994369383fc41146f8f621363573be7314c1105cc35464209a866680c7d`
- test_chan_m3b_input.py: `4d8b926f12f44ce66427a5cd840876a17dc5f88e9750f853063c3103b3282f8f`

### Final ordered regression

The adapted frozen candidate completed the expanded ordered suite: **142 tests, 142 passed, 0 failures/errors/skips**, 409.551 seconds. Order included SignalCenter, v103 history, DecisionBoard, current-board contract, temporal/current snapshot compatibility, flow-share callers/golden coverage and Chan M3B input tests. This specifically reruns the earlier order-dependent failure path rather than relying only on the normal full-suite ordering. The independent-review source hashes still match. Final complete-suite and exact-commit hosted CI remain pending.

### Final complete regression

Frozen final candidate: **1,752 collected, 1,741 passed, 11 existing optional/platform skips, 0 failures/errors**, 935.871 seconds. JUnit SHA-256: `db6eff3a609b2b36175dd98c6e249f1e2052c1602b4ed6209640d5d730178ba2`.

The ordered 142/142 JUnit SHA-256 is `adcb70e082040369cb3bf3386037c18e4e86b7d511936fb5bdd34c76cef96595`. All reviewed source hashes remain unchanged. Python compile, legacy app JavaScript syntax, critical Ruff checks (`E9,F63,F7,F82` on affected files), committed-secret scan, diff check and progress-view generation/check passed. This is not a claim of a full style-lint pass or of platform tests skipped locally.

The original branch was re-read at parent `6608602093d27704b4bebc8fb2affe36f65cfc32` before publication preparation. Exact-commit hosted CI is still a separate post-publication gate. Production has not been changed.
