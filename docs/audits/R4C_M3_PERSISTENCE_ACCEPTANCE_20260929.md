# R4C M3 observed-revision persistence acceptance — 2026-09-29

**State:** `M3_PASS_PRE_M4_DIAGNOSTIC_IN_PROGRESS`

**Branch:** `codex/r4c-m3-persistence`

**Accepted M2 base:** `641759eb467ef743f35c142edd50a8208bb2cfa7` / tree `9b4c934c4d8d562ace876f5c5f49c5b0042b4bc1`

**M3 implementation commit:** `ce0aa9b899b6d04ea682581b90343fa2973394ce` / tree `626f80f1011188f5fa429d43b37c83a60e6668e9`

**M3-R1 code commit:** `7fe11e2e02e3f980ae7ac1771f96403e8dcffe20` / tree `c38c3020a603e8e8233c985f23cf936fe237e165`

Remote iteration 60 accepted M2 and returned the M3 persistence publication plan. Jovi's standing instruction authorizes the repeating remote-plan/local-execution/test/GitHub/remote-review loop. This receipt records local evidence only; M3 still requires remote review before the next stage.

## Scope delivered

- Added Alembic revision `h9c0d1e2f3a4`, after `g8b9c0d1e2f3`, and four bounded persistence models: immutable observations, structure revisions, observed transitions, and one mutable head per stream.
- Added `ChanObservationPublisher`. It accepts only factory-validated `ResearchObservation` values, recomputes observation/structure/revision identities, validates prior evidence hashes, enforces stream namespaces and chronology, derives transitions through the shared M2 replay helper, writes immutable evidence, and advances the head in the caller's transaction.
- Exact observation retries are no-ops; reuse of an observation ID for different evidence fails closed. A failed flush requires caller rollback and leaves the published rows/head unchanged after rollback.
- PostgreSQL uses a transaction advisory lock per stream, including first publication when no head row exists. SQLite behavior is covered through a migrated disposable database.
- `config/chan_research.json` remains disabled and blocked. The existing persistence blocker is retained until remote M3 acceptance; runtime and read-model blockers remain.

## Design points for remote review

The R4B audit found that its revision history relied on service convention, had no database UPDATE/DELETE guard, and used `ON DELETE CASCADE` to instruments. M3 applies these corrections to the new evidence tables:

- SQLite and PostgreSQL migrations add database triggers rejecting UPDATE and DELETE on observations, structure revisions, and transitions. Stream-head DELETE is rejected; UPDATE remains limited to the pointer row.
- Evidence has no cascading FK to mutable instrument rows. Composite FKs bind revisions/transitions to their observation and bind the head to the exact `(stream_id, sequence_number, observation_id)` tuple.
- Each stream receives a monotonically increasing persistence sequence. Cutoff alone cannot order valid same-cutoff, same-time input revisions, so the head points to this sequence as well as the observation ID. M2 identity formulas are unchanged.

Please assess these choices against the M3 plan, especially the append-only guards, no-cascade history, and stream sequence/head contract. Raise any technical-route disagreement with evidence before M4. No persistence blocker has been removed from the disabled runtime config pending that review.

## Verification evidence

### Targeted Windows suite

Python 3.12.14, CZSC 1.0.1. The collected target set contains 39 items: 38 passed and the PostgreSQL test skipped because the regular Windows run has no `R4C_M3_POSTGRES_URL`. The skipped case was run separately against a fresh disposable PostgreSQL 16 container and passed.

```powershell
python -m pytest `
  backend/tests/test_chan_m3_persistence.py `
  backend/tests/test_chan_m2_contract.py `
  backend/tests/test_migration_schema_parity.py `
  backend/tests/test_decision_board.py::test_two_refresh_requests_leave_only_one_active_job `
  -q --tb=short
```

Coverage includes RED/green publication contracts, migrated SQLite schema and trigger checks, empty complete observations, same-day revisions, namespace isolation, identical retries, conflicting IDs, rollback, backward cutoff/head rewind, M2 replay parity, and disabled-config gates.

### Disposable PostgreSQL 16

One fresh container was bound only to `127.0.0.1` and removed after the run. Its database name was `etf_r4c_m3_test`; no production DB or business rows were used. The PostgreSQL test passed and performed:

- Alembic `upgrade head` → `check` → `downgrade base` → `upgrade head` → `check`.
- Two concurrent exact-ID publishers: one append and one idempotent retry; no duplicate records.
- Two concurrent, different same-cutoff revisions: both append under the same stream lock and the head resolves to the last sequence.
- SQL UPDATE/DELETE rejection for each immutable table, stream-head DELETE rejection, and stream-head rewind rejection.

### M2 and R5.2.1 Windows/Linux regressions

The selected CZSC adapter remains `1.0.1`, `engine_confirmation=unknown`, and `application_observation_status=observed` on both platforms. Each platform passed all 25 `test_chan_m2_contract.py` tests, including the frozen 300-bar resource contract.

| Evidence | Windows 11 | Linux x86_64 / glibc 2.41 |
|---|---:|---:|
| M2 300-bar warm adapter | 6.247 ms | 7.263 ms |
| Combined 20–300 prefix sweep | 943.572 ms | 924.978 ms |
| Peak RSS | 139,628,544 bytes | 227,823,616 bytes |
| M2 semantic digest | `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac` | same |
| R5.2.1 history digest | `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9` | same |
| R5 identity/revision/structure collisions | 0 / 0 / 0 | 0 / 0 / 0 |

The injected weak-ID collision self-test was detected on both platforms. All measured values stayed within the selected M1 resource limits.

### Static and repository checks

- Scoped Ruff: PASS.
- `python -m compileall -q backend/app`: PASS.
- `node --check backend/app/static/app.js`: PASS.
- Scoped secret-pattern scan of changed source/tests: PASS.
- `git diff --check`: PASS.

The full project `pytest -q` run was interrupted after about 23 minutes at 27% with no final pytest report or traceback. The candidate `test_two_refresh_requests_leave_only_one_active_job` passed alone in 1.21 seconds; a separate whole decision-board module attempt was also interrupted after a long test tail. Record the full-suite state as `INTERRUPTED / NOT_VERIFIED`, never PASS. This does not replace the completed M3/M2/migration/PG16 focused gates above.

## Safety and qualification boundary

- Real-data qualification remains `UNKNOWN`; `actionable=false`; canonical action is unchanged.
- Engine/runtime remains disabled. No Provider, real market data, production database, API/read model, worker/scheduler, frontend/chart, production deployment, or auto-trading path was added or used.
- All publication tests use synthetic bars/observations and disposable SQLite/PostgreSQL databases.

## Remote review request

Review the exact pushed head on `codex/r4c-m3-persistence` against iteration 60's M3 plan. Verify migration parity, SQLite/PostgreSQL immutability, atomic rollback, exact retry/conflict semantics, concurrency, chronology, basis/config namespace isolation, shared M2 transition parity, and all scope boundaries. Explicitly accept or request changes to the three design points above. If M3 is accepted, remove only `REVISION_PERSISTENCE_NOT_IMPLEMENTED` as instructed by the M3 plan, retain runtime/read-model blockers, and issue the next detailed stage plan. Do not infer real-data qualification or production readiness from these synthetic gates.

## Iteration 61 remote review and M3-R1 repair — 2026-09-29

Remote review decision: `M3=CHANGES_REQUIRED`, `ROUTE_A=RETAIN`, `M4_GO=FALSE`. It accepted the no-cascade evidence design, immutable evidence triggers, stream sequence/composite head FK, PostgreSQL advisory locking, shared M2 transition helper, and M2/R5 parity. It found two bounded gaps:

1. The stream-head trigger blocked DELETE and sequence rewind, but raw SQL could still UPDATE duplicated stream namespace columns such as `config_id` or `instrument`.
2. Rollback tests covered only a failed first head insert. The plan also required a failed child revision/transition insertion during a later publication to preserve an already committed head and history.

R1 changes on the same branch:

- Kept Alembic revision `h9c0d1e2f3a4`; no second migration was added. SQLite rejects changes to each stream-head identity column. PostgreSQL uses a row-identity comparison and the same immutable rule.
- Both dialects allow an unchanged pointer or a pointer update whose sequence strictly advances to another observation. The composite FK binds an advancing pointer to the exact immutable observation. Raw SQL tests cover stream ID/config/instrument mutation rejection, pointer no-ops, and rewind rejection.
- Two injected later-publication failures (`ChanStructureRevision` and `ChanObservedTransition`) now run after an observation is committed. On rollback, each test compares the previous head and ordered immutable-row snapshots and confirms no failed observation row remains.
- The R1 Windows target set has 41 collected items: 40 passed, 1 PostgreSQL-only skipped. That PostgreSQL case was separately run and passed against a fresh disposable PostgreSQL 16 container.
- SQLite and PostgreSQL migration gates assert both `alembic heads` and `alembic current` identify the single head `h9c0d1e2f3a4`.

R1 M2/R5 regressions were rerun. All 25 M2 focused tests pass on Windows and Linux with CZSC 1.0.1; the 300-bar semantic digest remains `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac`; the R5.2.1 history digest remains `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9`; observation/structure/revision collision counts are zero and the injected weak-ID collision is detected.

| R1 evidence | Windows 11 / Python 3.12.14 | Linux x86_64 / Python 3.12.14 |
|---|---:|---:|
| M2 300-bar warm adapter | 7.183 ms | 6.117 ms |
| Combined M2 prefix workload | 1,020.981 ms | 895.522 ms |
| M2 peak RSS | 139,849,728 bytes | 217,305,088 bytes |
| R5.2.1 prefix sweep | 1,539.917 ms | 1,319.982 ms |

R1 Ruff, compileall, Node check, scoped secret scan, and diff check pass. The remote accepts the full-suite interruption as `INTERRUPTED / NOT_VERIFIED` for this bounded M3 gate; before widening toward main or product integration, complete the full suite or diagnose its long-tail section. The persistence blocker remains in config, runtime remains disabled, and M4 has not started.

## Iteration 62 M3 PASS and Scope A metadata closure — 2026-09-29

Remote review of final M3-R1 head `47ff5c57ae6ccd40864523aa962b3a1fb80f313c` returned `M3=PASS`, `PERSISTENCE_CONTRACT=ACCEPTED`, and `ROUTE_A=RETAIN`. It confirmed the stream-head identity triggers, pointer-forward contract, later-publication rollback tests, PostgreSQL concurrency, migration single head, and M2/R5 invariants. It also records `FULL_PYTEST=INTERRUPTED/NOT_VERIFIED`, `MAIN_INTEGRATION_READINESS=BLOCKED_BY_TEST_DIAGNOSTIC`, `M4_IMPLEMENTATION_GO=FALSE`, and `MAIN_INTEGRATION_GO=FALSE`.

Scope A removes only `REVISION_PERSISTENCE_NOT_IMPLEMENTED` from `config/chan_research.json`. The exact remaining blockers are `RUNTIME_INTEGRATION_DISABLED` and `USER_FACING_READ_MODEL_NOT_INTEGRATED`. `enabled=false`, `qualification_status=BLOCKED`, `selection_status=SELECTED_DISABLED`, `engine_confirmation=unknown`, and `application_observation_status=observed` remain unchanged. The two config regression tests both pass.

Scope B is underway on isolated branch `codex/r4c-pre-m4-regression-diagnostic` at base `47ff5c57ae6ccd40864523aa962b3a1fb80f313c`. No M4 or main integration is authorized until the full suite completes or the remote-required blocked diagnostic is returned with a minimal reproducer and stack/resource evidence.

## Iteration 62 M3 decision and Scope A metadata close — 2026-09-29

Remote review of final head `47ff5c57ae6ccd40864523aa962b3a1fb80f313c` returned `M3=PASS`, `PERSISTENCE_CONTRACT=ACCEPTED`, and `ROUTE_A=RETAIN`. It confirmed both iteration-61 findings are closed against the exact pushed diff. `M4_IMPLEMENTATION_GO=FALSE` and `MAIN_INTEGRATION_GO=FALSE` remain.

Scope A in iteration 63 removes only `REVISION_PERSISTENCE_NOT_IMPLEMENTED` from `config/chan_research.json`. It retains exactly `RUNTIME_INTEGRATION_DISABLED` and `USER_FACING_READ_MODEL_NOT_INTEGRATED`; `enabled=false`, `qualification_status=BLOCKED`, `selection_status=SELECTED_DISABLED`, `engine_confirmation=unknown`, and `application_observation_status=observed` remain unchanged. No engine/version/dialect/identity, resource, real-data, actionable, or production metadata is changed.

## Iteration 63 pre-M4 full-suite diagnostic plan — in progress

The diagnostic branch is `codex/r4c-pre-m4-regression-diagnostic`, created at exact M3 PASS base `47ff5c57ae6ccd40864523aa962b3a1fb80f313c`. This is a test-diagnostic stage only; it does not implement the M4 read model.

Collection baseline: `pytest --collect-only -vv` found 1,316 items in 132 modules. The prior 27% boundary lies within `test_decision_board.py` at `test_due_slots_skip_lunch_and_weekends[value0-20260831-0930]`. This is a search locator, not an assumed root cause. The R4B receipt's 1,279-test count predates M2/M3 additions; count differences alone are not failures.

- Record `pytest --collect-only`, total item count, and module ordering.
- Reproduce the Windows full suite with `-vv --durations=20 -o faulthandler_timeout=120`. Capture each live last-test/progress point and any faulthandler stack; do not stop only because an individual test is slow.
- If it stalls, bisect bounded module groups in collection order. Start with `backend/tests/test_decision_board.py` because the prior run reached that region, without assuming it is the cause. Record elapsed time per group.
- For the isolated long tail inspect unjoined threads, executor shutdown waits, unreaped subprocesses, DB transactions/locks, SQLite file locks, scheduler loops, sleeps/polls, and fixture finalizers. Use existing tooling and do not call real Providers or external services.
- A minimal repair is allowed only for a proven test-harness/resource-lifecycle defect. Do not change product/business behavior or redesign unrelated modules.
- Required exit: the full Windows repository suite completes with a final report; M3 focused tests stay green; rerun PG16 if shared DB/test infrastructure changes; rerun M2/R5 gates when shared runtime code changes; run applicable static checks. If the full suite still cannot complete, report `PRE_M4_DIAGNOSTIC=BLOCKED` with the smallest reproducer and stack/resource evidence. Do not start M4.

The previous full suite remains `INTERRUPTED / NOT_VERIFIED`: it reached roughly 27% after about 23 minutes without a failing assertion or traceback. A standalone `test_two_refresh_requests_leave_only_one_active_job` passed in 1.21 seconds; the whole decision-board module attempt was interrupted after a long tail. This diagnostic must identify the cause or complete the suite before any main/product integration.
