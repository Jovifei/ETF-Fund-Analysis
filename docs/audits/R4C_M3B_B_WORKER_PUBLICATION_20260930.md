# R4C M3B-B audited worker publication — local execution receipt

Date: 2026-09-30

C2C task: `c2c_a1d7`, iteration 68

Remote plan base: `6166587d718992237908099b6b89ea83f3779d3d` / tree `f7a096be408ce908cb5e5c282b19025153ec0653`

Local implementation and GitHub push/readback completed. Remote exact-head review of `e28766ad4dc5d186b335d4cca5cecb3ec3930f10` returned `M3B_B_STATUS=CHANGES_REQUIRED`, retained the route, and authorized M3B-B-R1.

Code/test commit: `e38d524c639a938e5bf709302c95923b9f20df1f` / tree `a00ae89bfa7045d151b8c90b3ea09695cc49307e`, parent `6166587d718992237908099b6b89ea83f3779d3d`.

## Remote scope and release disposition

Iteration 67 accepted M3B-A2 and authorized M3B-B. This stage connects an internal bounded Chan request to the existing workspace data-job queue and worker, freezes each code's accepted input in a short transaction, closes that transaction before CZSC runs, then writes through the existing immutable `ChanObservationPublisher` in a separate short transaction.

M3B-B is `NOT_DEPLOYABLE_SUBSTAGE` / `PRE_RELEASE_RUNTIME_COMPONENT`. It has no ordinary producer, public enqueue route, read model, scheduler, UI, or production activation. Production was not contacted or changed. Real-data qualification remains `UNKNOWN`; `actionable=false`; automatic trading remains absent. M3B-C and later stages remain blocked pending this head's remote review and a separate remote plan.

## Implementation

- Added internal `ChanStructuresRequest` and persisted `ChanStructuresJobRequest` schemas in `backend/app/workspace/protocol.py`. Codes are explicit, unique, sorted, and bounded to 1–30 ETF/LOF identifiers; interval is D/W/M; `as_of` must be timezone aware and is normalized to UTC. Public `DataRequest.task` still rejects `chan_structures`.
- Added `enqueue_chan_structures()` in `backend/app/workspace/data_jobs.py`. It uses `owner_scope(None)`, `user_id=None`, the existing `workspace-data-queue` lock/capacity/idempotency rules, and the existing claim/lease path. Exact retries reuse the existing row; changed payloads raise `data_idempotency_conflict`; terminal jobs are not silently requeued.
- Added `backend/app/services/chan_structure_service.py`. Each code is isolated. Blocked inputs skip CZSC. The freeze session closes before adapter execution; publication runs in a separate transaction. Results contain bounded status/reason/identity/sequence/count fields only. The service never records raw exception text, full price history, Provider/model output, qualification changes, or actionability.
- Added a lazy `chan_structures` worker branch in `backend/app/workspace/worker.py` before runtime credential resolution and ordinary `TaskService` construction. No top-level CZSC import or public/scheduled producer was added. The existing `prices` → `TaskService` path remains covered.
- Added `backend/tests/test_chan_m3b_worker.py` for request bounds and public-task rejection, queue idempotency/capacity/lease, unchanged ordinary enqueue and worker routing, freeze/compute/publish transaction boundaries, blocked inputs, failure isolation, bounded results, W temporary-to-settled lifecycle, exact retry, M smoke, and chronology/head retention.

## Verification

| Gate | Result |
|---|---|
| New worker unit group on repository Python 3.13.14 | 19 collected; 17 passed; 2 skipped because exact-engine and PostgreSQL runs are separate; 0 failures/errors |
| Full Windows repository pytest, Python 3.13.14 | 1,369 collected; 1,348 passed; 21 skipped; 0 failures; 0 errors; 35 warnings; 1,516.123 s; exit 0 |
| Focused M3B-A/A2, M2/M3 persistence, workspace-job tests, Windows Python 3.12.10 | 70 collected; 69 passed; 1 skipped; 0 failures/errors; 23.973 s |
| R4A corporate-action contract, Windows Python 3.12.10 | 8/8 passed |
| Exact CZSC worker integration, Windows Python 3.12.10 / CZSC 1.0.1 | Passed D publication with two synthetic FX structures, W temporary→settled sequence advancement, exact retry as idempotent, older-cutoff rejection with head retained, and M publication |
| Exact CZSC worker integration, Linux Python 3.12.14 / CZSC 1.0.1 | Passed the same D/W/M lifecycle and retained the same semantic digest as Windows |
| Disposable PostgreSQL worker integration, PostgreSQL 16.15 / Windows Python 3.12.10 / CZSC 1.0.1 | Passed W publication, exact retry with one immutable observation, and earlier-cutoff rejection while retaining the accepted head; loopback container stopped and removed |
| M2 and R5.2.1 Windows/Linux validators | Passed; frozen M2 semantic, R5 history, and R5 semantic digests remain unchanged; R5 namespace collision counts are all 0; weak-ID self-test detected the injected collision on both platforms |
| Ruff, compileall, Node syntax, scoped secret scan, diff-check | Passed |

Exact D/W/M semantic digest on Windows and Linux: `66b8092b122ffb1819d18e45963b3f708fca0581550fb062395efc96023096bd`.

PostgreSQL retry/chronology semantic digest: `ea2b21d4c2eb5a5542d5143f4a51bd8eff6fe7e76801a4691f5fe74fe13d4c37`.

Frozen M2 digest: `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac`.

Frozen R5 history digest: `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9`.

Frozen R5 semantic digest: `0f4ae0322b5d390c41e618da4c342abea66baac30bce4ccfe4a5f0d713cff76f`.

## Evidence files

Outputs are local synthetic-test evidence under `E:/Claude_allow/Download/ETF_R4C_M3_20260929/`:

- `m3b-b-full-windows-projectpy-final.xml` and `.txt`
- `m3b-b-worker-windows-projectpy-final.xml` and `.txt`
- `m3b-b-focused-windows31210.xml` and `.txt`
- `m3b-b-r4a-windows31210.xml` and `.txt`
- `m3b-b-worker-win31210-final.txt`
- `m3b-b-postgres16-final.txt`
- `m3b-b-m2-win31210-final.json`, `m3b-b-r5-win31210-final.json`
- `iteration68-linux/m3b-b-worker-linux31214-final.txt`
- `iteration68-linux/m3b-b-m2-linux31214-final.json`, `m3b-b-r5-linux31214-final.json`

No production endpoint, Provider, model, real market-data source, or production database was used. The disposable PostgreSQL database was loopback-only and existed only for the test run.

## Remaining gate

Iteration 68 remote review found that the service did not enforce persisted `Instrument.kind` as ETF/LOF before freeze/engine, and that worker-level historical correction and publication-failure isolation/head-retention tests were missing. Follow `tasks/plans/2026-09-30-r4c-m3b-b-r1-scope-failure-isolation.md`; only `chan_structure_service.py` and `test_chan_m3b_worker.py` are authorized code/test files. Keep M3B-C, M4, main integration, and production disabled until the R1 exact-head review and a new remote plan.

### Iteration 69 R1 local verification

R1 code/test changes are limited to `backend/app/services/chan_structure_service.py` and `backend/tests/test_chan_m3b_worker.py`. Code/test commit is `ec473eb40d3e28bc7c51a74c3a0a91f7679296f8` / tree `c8f705eec059538d97f635a6b3f886bd5d77faa0`, parent `e28766ad4dc5d186b335d4cca5cecb3ec3930f10`; the documentation receipt commit, push, and exact-head review remain.

- Eligibility is checked from persisted `Instrument.kind` in the short freeze scope. Missing instruments and non-ETF/LOF kinds return bounded blocked reasons before freeze/CZSC/publisher. ETF and LOF follow the normal path; `chan_input.py` and identities are unchanged.
- RED-first scope cases failed before the type gate and pass afterward. Same-as_of historical D correction is tested through worker→freeze→CZSC 1.0.1→publisher; the stream stays stable, input/observation changes, sequence advances, old evidence remains, and the head advances.
- Publication failure isolation and rollback tests pass on SQLite: code A's committed observation survives code B's publication failure; a later staged failure leaves the old head/observation/revisions/transitions intact and the attempted observation absent. Failure details remain bounded.
- `test_chan_m3b_worker.py`: repository Python 3.13.14 = 24 collected, 21 passed, 3 environment skips; Windows Python 3.12.10 and Linux Python 3.12.14 = 24 collected, 23 passed, 1 PG fixture skip each. Exact worker D/W/M semantic digest stays `66b8092b122ffb1819d18e45963b3f708fca0581550fb062395efc96023096bd` on both platforms.
- Focused M3B-A/A2, M2/M3 persistence, workspace jobs and R4A gate: 100 collected, 99 passed, 1 skip, 0 failures/errors.
- Disposable PostgreSQL 16.15 retry/idempotency/chronology/head-retention passes. Frozen M2/R5 digests and collision checks are unchanged.
- Final Windows full suite: 1,374 collected, 1,352 passed, 22 skipped, 0 failures/errors, 35 warnings, 1,514.182 seconds, exit 0. Ruff, compileall, Node syntax, scoped secret scan and diff-check pass.

R1 local evidence is under `E:/Claude_allow/Download/ETF_R4C_M3_20260929/` and `iteration69-linux/`. No real data/Provider, production database, deployment or trading was used. Next: finalize/commit the R1 documentation, push and verify the exact branch head, then request remote iteration-69 review; do not start M3B-C until PASS and a separate plan.
