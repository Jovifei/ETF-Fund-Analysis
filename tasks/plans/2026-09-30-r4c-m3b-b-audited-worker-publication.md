# R4C M3B-B — audited internal Chan worker publication

Date: 2026-09-30. C2C task `c2c_a1d7`, iteration 68. Plan base: pushed A2-R1 head `6166587d718992237908099b6b89ea83f3779d3d` / tree `f7a096be408ce908cb5e5c282b19025153ec0653`.

## Remote gate and deployment disposition

Remote iteration 67 exact-head review accepted A2: `M3B_A2_STATUS=PASS`. It authorized `M3B_B_GO=true`; `M3B_C_GO=false`, `M4_GO=false`, `MAIN_INTEGRATION_GO=false`, `PRODUCTION_GO=false`. Technical route remains the accepted CZSC 1.0.1 / observed-revision path.

M3B-B is `NOT_DEPLOYABLE_SUBSTAGE` / `PRE_RELEASE_RUNTIME_COMPONENT`: it adds an internal worker consumer but no normal producer, public endpoint, or read model. Production remains unchanged. The first release-bearing application stage remains M3B-C and requires its own remote plan plus the already required backup, migration rehearsal, rollback, and live smoke gates. Real-data qualification remains `UNKNOWN`; `actionable=false`; no automatic trading.

## Objective and frozen boundaries

Wire the accepted M3B-A/A2 inputs to the existing audited workspace worker:

`internal bounded request → existing data-job queue → short DB freeze transaction → close transaction → CZSC adapter → short publisher transaction → bounded per-code result`

Use the existing `WorkspaceDataJob`, `workspace-data-queue` lock, queue capacity, idempotency conflict rules, claim/lease mechanism, `ChanAdapter`, and `ChanObservationPublisher` public interface. Do not add a second queue/table/scheduler or a second publication layer. Do not alter M2/M3 contracts, A2 identities, calendar aggregation, or ordinary `data_jobs.enqueue()` behavior.

The Chan task is internal only. Do not add it to public `DataRequest.task`; public `/api/.../data-jobs` requests for `chan_structures` must remain rejected. Do not add a public enqueue route, scheduler producer, frontend/UI, GET/read model, main merge, production activation, real Provider/model/network call, or actionable/trading behavior. Keep `config/chan_research.json` disabled and unqualified.

## B0 — read the current integration contracts before editing

Re-read these exact files and the related queue/worker/M3 tests through the bound workspace:

- `backend/app/workspace/protocol.py`
- `backend/app/workspace/data_jobs.py`
- `backend/app/workspace/worker.py`
- `backend/app/research/chan_input.py`
- `backend/app/research/chan_adapter.py`
- `backend/app/research/chan_contract.py`
- `backend/app/services/chan_observation_service.py`
- existing `test_workspace_jobs.py`, workspace worker/data-job tests, and `test_chan_m3_persistence.py`

Use the accepted adapter and publisher interfaces exactly. If either must change, stop and return to the remote plan gate before editing it.

## B1 — bounded internal request contract

Add an internal request model in `protocol.py` (or a narrowly scoped protocol module) with:

- `schema_version="r4c-chan-job-v1"`, `task="chan_structures"`;
- 1–30 explicit, unique, canonically sorted ETF/LOF codes;
- `interval` in `D|W|M`;
- timezone-aware `as_of`, normalized deterministically and persisted unchanged for retries;
- an existing-format bounded idempotency `request_key`.

Canonicalize codes before persistence so result and execution order are deterministic. The public `DataRequest.task` literal must not change. Add a regression that the existing public request model still rejects `chan_structures`.

## B2 — reuse the existing internal queue

Add one narrowly named internal helper in `data_jobs.py`, such as `enqueue_chan_structures(...)`. It must use:

- `WorkspaceDataJob`;
- `owner_scope(None)` and `user_id=None` (global market research, not personal holdings);
- existing `workspace-data-queue` lock, active queue capacity, and claim/lease mechanism;
- the same request-key idempotency semantics: same key + canonical request returns the existing job with `created=false`; same key + changed payload returns `data_idempotency_conflict`.

No normal worker, scheduler, API, UI, or producer may call this helper in M3B-B. Tests may enqueue an internal job directly. Existing ordinary data-job enqueue behavior stays unchanged.

## B3 — per-code orchestration and exact transaction boundaries

Prefer new `backend/app/services/chan_structure_service.py` with only these responsibilities:

1. Validate the internal request.
2. For each code, open a short DB session/transaction, call `freeze_chan_input(code, interval, exact request.as_of)`, materialize immutable `PreparedResearchInput`, and close the DB session/transaction.
3. If input is blocked, return a bounded per-item blocked result and do not initialize CZSC.
4. Only after the read transaction is closed, call the existing exact-version `ChanAdapter` and obtain a validated `ResearchObservation`. No application DB transaction may be open during CZSC computation. Do not add thread pools or another child-process layer.
5. After observation validation, open a new short DB transaction, call `ChanObservationPublisher.publish(...)`, commit, and close.
6. Produce only bounded per-code outcomes.

Do not wrap multiple instruments or engine computation in one long transaction. Caller-owned transaction semantics of the publisher stay unchanged.

## B4 — worker selection before ordinary providers/tasks

In `worker.py`, recognize `task == "chan_structures"` before constructing ordinary `TaskService`, `CacheOnlyTaskService`, or a Provider. Use a local/on-demand import of the Chan service so normal worker startup does not load CZSC/native bindings. Do not add a top-level CZSC import to `worker.py`.

Keep the internal branch dormant: `run_once()` gains no Chan enqueue producer, scheduler integration, public API, or discovery behavior. The normal queue continues to claim and supervise the internal job through the existing child-process model.

## B5–B8 — activation, result, failure, and lifecycle contracts

- Config stays `enabled=false`, `qualification_status=BLOCKED`, `selection_status=SELECTED_DISABLED`, and runtime integration disabled. No normal producer exists.
- Per-code statuses are bounded to `published`, `idempotent`, `blocked`, or `failed`. Permitted evidence fields: `ts_code`, `interval`, status, `observation_id`, `input_hash`, publication sequence, `already_published`, structure counts by kind, bounded `reason_code`.
- Never store raw exception text, full structure payloads, full OHLCV history, Provider responses, or model output. Job-level result explicitly carries `provider_called=false`, `models_called=false`, `qualification_changed=false`, `actionable=false`.
- Job status: all published/idempotent → `succeeded`; success mixed with blocked/failed → `partial`; all inputs blocked with no execution defect → `partial`; no successful item plus a real engine/publication failure → `failed`. Input qualification blocks must not be reported as successful data qualification.
- Codes fail independently. A code that publishes successfully remains committed if another code fails. A later same-stream failure never replaces an existing valid head/history. Reuse the M3 publisher; missing/wrong CZSC must fail closed before publication.
- Add at least one worker-level W lifecycle test: Wednesday W publication is temporary; Friday in the same W stream is settled and advances sequence/revision while retaining prior evidence. Add at least one M publication smoke.

## Required tests and platform gates

Add `backend/tests/test_chan_m3b_worker.py` for at least: internal request bounds/canonical order; public `DataRequest` rejection; enqueue retry/conflict; ordinary queue behavior unchanged; claim/lease; Chan selection before TaskService/Provider construction; blocked input without CZSC/publication; freeze transaction closed before adapter; publication in a new short transaction; duplicate observation idempotency; failure isolation; old-head retention; W temporary→settled; M publication; bounded result fields; zero provider/model/qualification/actionable side effects; and public API/scheduler/frontend cannot enqueue Chan work.

Run existing A2 focused tests, M2 contract, M3 persistence, workspace queue/worker tests, and relevant R4A tests. Run exact-engine worker/service integration with CZSC 1.0.1 and synthetic rows on Windows Python 3.12.x and Linux Python 3.12.14: freeze → real CZSC adapter → `ResearchObservation` → SQLite publication for D and one period interval. Record exact Python patch versions and frozen semantic output.

Run one disposable PostgreSQL 16 integration using the existing Alembic head and a fresh loopback database named `etf_r4c_m3_test`; no production DB. Prove a real worker-style freeze/compute/publish, terminal job result, identical retry with no duplicate immutable evidence, and a later publication failure/chronology rejection that preserves the committed head/history. No migration is expected. If PostgreSQL 16 cannot be run, M3B-B remains blocked; SQLite alone is insufficient.

Because this changes shared worker/data-job runtime code, run the complete Windows repository pytest on the final code candidate before push and report collected/passed/failed/errors/skipped/warnings/duration/exit code. Also rerun M2 Windows/Linux, semantic digest, and R5.2.1 Windows/Linux validators; frozen digests/collision checks must remain unchanged. Run Ruff, compileall, Node syntax, scoped secret scan, and diff-check.

## Exact authorized files

Primary: `backend/app/workspace/protocol.py`, `backend/app/workspace/data_jobs.py`, `backend/app/workspace/worker.py`, new `backend/app/services/chan_structure_service.py`, new `backend/tests/test_chan_m3b_worker.py`.

Read/reuse only by default: `backend/app/research/chan_input.py`, `chan_adapter.py`, `chan_contract.py`, `backend/app/services/chan_observation_service.py`, and `backend/app/workspace/models.py`.

Documentation: audit receipt, `HANDOFF.md`, `STATUS.md`, `tasks/todo.md`, `tasks/lessons.md`, and this plan.

Explicitly forbidden: `actions_api.py`, `workspace/api.py`, scheduler/discovery/refresh sequences, frontend, `KlineStabilizationService`, Provider implementations, Chan identities, M3 schema/publisher, config activation flags, public Chan endpoint, scheduled Chan jobs, GET/read model, UI, migration, main merge, production deployment, real-data qualification, actionable promotion, and automated trading.

## Acceptance and next gate

M3B-B passes only after exact-head review confirms the internal worker path, transaction/Provider isolation, immutable retry/failure behavior, D/W/M lifecycle, full Windows test suite, exact-engine Windows/Linux integrations, PostgreSQL 16 integration, and all frozen digest/side-effect gates. Push the verified head, release bounded evidence, and request remote exact-head review. M3B-C stays GO=false until a separate remote plan.

Deployment remains `NOT_DEPLOYABLE_SUBSTAGE` / `PRE_RELEASE_RUNTIME_COMPONENT`, production GO=false. No production changes; real data `UNKNOWN`; `actionable=false`.

## Local execution record — 2026-09-30

Implementation and local commits are complete. Code/test commit is `e38d524c639a938e5bf709302c95923b9f20df1f` / tree `a00ae89bfa7045d151b8c90b3ea09695cc49307e`, parent `6166587d718992237908099b6b89ea83f3779d3d`. The branch was pushed and GitHub readback matched; the remote iteration-68 exact-head review remains.

- Added internal `ChanStructuresRequest` / persisted `ChanStructuresJobRequest`; the public `DataRequest.task` contract still rejects `chan_structures`.
- Added `enqueue_chan_structures()` with global offline scope, the existing queue lock/capacity/idempotency behavior, and the unchanged claim/lease path. No API, scheduler, UI, or regular producer calls it.
- Added `ChanStructureService`: it commits/closes the per-code freeze transaction before invoking the pinned adapter, then uses a separate transaction for `ChanObservationPublisher`. It records only bounded per-code status/identity/count fields and does not persist exception text or alter qualification/actionability.
- Added a lazy worker branch before runtime credential resolution and ordinary task service construction. The ordinary `prices` worker route remains intact. No top-level CZSC import was added.
- Unit tests: `backend/tests/test_chan_m3b_worker.py` is 17 passed / 2 skipped under the repository Python 3.13.14 environment; skips are the exact-engine and PostgreSQL fixtures run separately below.
- Windows full suite: 1,369 collected; 1,348 passed; 21 skipped; 0 failures; 0 errors; 35 warnings; 1,516.123 seconds; exit 0.
- Windows focused M3B-A/A2, M2/M3 persistence and workspace jobs: 70 collected, 69 passed, 1 skipped, 0 failures/errors, 23.973 seconds. R4A corporate-action contract: 8/8.
- Exact CZSC 1.0.1 worker integration: Windows Python 3.12.10 and Linux Python 3.12.14 both pass D publication, W temporary→settled sequence advancement, exact retry idempotency, W chronology rejection/head preservation, and M publication. Windows/Linux semantic digest is `66b8092b122ffb1819d18e45963b3f708fca0581550fb062395efc96023096bd`; D emitted two synthetic `fx` records. Real data was not used.
- Disposable PostgreSQL 16.15 integration on Windows Python 3.12.10/CZSC 1.0.1 passes worker-style W publication, exact retry with one immutable observation, and earlier-cutoff rejection with the accepted head retained. Semantic digest: `ea2b21d4c2eb5a5542d5143f4a51bd8eff6fe7e76801a4691f5fe74fe13d4c37`. The loopback container was stopped and removed after the run.
- M2 semantic digest remains `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac` on Windows/Linux. R5.2.1 history digest remains `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9`; semantic digest `0f4ae0322b5d390c41e618da4c342abea66baac30bce4ccfe4a5f0d713cff76f`; collision counts 0, and weak-ID injection was detected on both platforms.
- Ruff, Python compileall, Node syntax, scoped secret scan, and `git diff --check` pass. Detailed bounded outputs are under `E:/Claude_allow/Download/ETF_R4C_M3_20260929/` and the iteration-68 Linux subfolder.

The full execution receipt is `docs/audits/R4C_M3B_B_WORKER_PUBLICATION_20260930.md`. No production deployment is authorized for B; M3B-C remains GO=false until remote exact-head review and a separate plan.
