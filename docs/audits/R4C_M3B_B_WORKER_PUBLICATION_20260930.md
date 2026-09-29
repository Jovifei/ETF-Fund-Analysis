# R4C M3B-B audited worker publication — local execution receipt

Date: 2026-09-30

C2C task: `c2c_a1d7`, iteration 68

Remote plan base: `6166587d718992237908099b6b89ea83f3779d3d` / tree `f7a096be408ce908cb5e5c282b19025153ec0653`

Local implementation and GitHub push/readback are complete; remote exact-head review is pending.

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

Attach bounded execution evidence to C2C and ask remote ChatGPT to review the pushed exact head against iteration 68. Keep M3B-C, M4, main integration, and production disabled until that review and a new remote plan.
