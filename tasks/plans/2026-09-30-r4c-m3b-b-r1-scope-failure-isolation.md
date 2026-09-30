# R4C M3B-B-R1 — instrument scope and failure isolation

Date: 2026-09-30

C2C task: `c2c_a1d7`, iteration 69
Plan base: `e28766ad4dc5d186b335d4cca5cecb3ec3930f10` / tree `30a1904edd9d95fe5a24f94b17773cf415abba79`

## Remote review and authorization

Iteration 68 exact-head review returned `M3B_B_STATUS=CHANGES_REQUIRED` with the architecture retained and `M3B_B_R1_GO=true`. The exact pushed source was reviewed from GitHub; the stale Owner checkout was not used for source review. No M3B-C work is authorized until this R1 head passes exact-head review.

Remote findings:

1. The request validates code syntax but does not verify the persisted `Instrument.kind`. `freeze_chan_input()` accepts any existing instrument, so a valid code for a non-ETF/LOF can reach CZSC. This is a real scope defect.
2. M3B-B lacks a worker-level historical correction test proving a corrected D bar and `quality_hash` produce a new observation on the same logical stream while retaining the earlier observation.
3. Existing tests cover engine failure and PG chronology rejection, but not a publication failure after one code commits or a failed later publication preserving an existing head.

## Objective

Make the already authorized M3B-B worker enforce the ETF/LOF universe, and close the three missing worker/publication regression cases without changing accepted identities, the adapter, or the publisher.

## Scope and tasks

### R1-1 — enforce ETF/LOF eligibility in orchestration

- Change only `backend/app/services/chan_structure_service.py`.
- Before freeze/observe, read the persisted `Instrument` in a short session. The instrument must exist and `kind` must be exactly `ETF` or `LOF`.
- Missing instrument returns bounded `blocked/instrument_missing`; a present unsupported type returns bounded `blocked/unsupported_instrument_type`.
- Blocked or unsupported instruments call neither `freeze_chan_input`, CZSC, nor publisher. ETF/LOF instruments proceed through the existing freeze path.
- Reuse the same short read scope for eligibility and freeze if practical. No DB transaction may remain open while CZSC runs.
- Do not modify `chan_input.py`, public `DataRequest`, queue, worker, identities, publisher, schema, Provider, API, scheduler, UI, or config.

### R1-2 — worker historical correction lifecycle

- In `backend/tests/test_chan_m3b_worker.py`, use a disposable synthetic SQLite DB and the existing worker/service path.
- Publish a D observation at a fixed `as_of`; record its stream/head, input/observation IDs, sequence, and immutable evidence counts.
- Correct a historical `DailyBar` and its `quality_hash`, then run the same interval and same `as_of` again.
- Assert the logical stream is unchanged; `input_hash` and `observation_id` change; sequence increments; new immutable evidence is appended; the old observation and its evidence remain queryable; the head advances to the new observation.
- Preserve all identity formulas and use the existing freeze → adapter → publisher path.

### R1-3 — publication failure isolation and head retention

- Add a multi-code service/worker regression where code A publishes and commits, while code B's publication raises a controlled exception.
- Assert job status is `partial`, A remains `published` with committed evidence, B is `failed` with bounded `publication_failed`, and raw exception text is absent.
- In the same or a separate test, publish a valid head, change same-stream input, then inject a publication failure after the existing publisher has staged its write but before transaction commit.
- Assert the prior head, observations, revisions, and transitions are unchanged; attempted new observation/evidence is absent.
- Reuse `ChanObservationPublisher`; do not add rollback logic or a parallel publisher.

### R1-4 — scope regressions

- Prove ETF and LOF types reach the normal freeze/compute/publication path.
- Prove a syntactically valid non-ETF/LOF and a missing instrument are blocked before freeze/CZSC/publication.
- Keep the public `DataRequest` rejection regression.

## Authorized files

Code/test changes are limited to:

- `backend/app/services/chan_structure_service.py`
- `backend/tests/test_chan_m3b_worker.py`

Conditional documentation only: this R1 plan, M3B-B acceptance receipt, `HANDOFF.md`, `STATUS.md`, `tasks/todo.md`, and `tasks/lessons.md`.

## Verification and exit

- Run `test_chan_m3b_worker.py`, M3B-A/A2, M2, M3 persistence, workspace jobs, and relevant R4A tests.
- Retain exact CZSC 1.0.1 worker integration on Windows Python 3.12.10 and Linux Python 3.12.14; frozen worker semantic digest must remain `66b8092b122ffb1819d18e45963b3f708fca0581550fb062395efc96023096bd`.
- Rerun the disposable PostgreSQL 16.15 retry/chronology/head-retention integration, full Windows repository pytest, M2/R5 Windows/Linux validators, Ruff, compileall, Node syntax, scoped secret scan, and diff-check.
- Push the tested code and documentation, verify exact GitHub head/tree, release bounded C2C evidence, and request remote exact-head review.
- Until remote PASS, keep M3B-C/M4/main/production false. Deployment remains `NOT_DEPLOYABLE_SUBSTAGE`; real data remains `UNKNOWN`; `actionable=false`; no auto-trading.

## Local execution record — 2026-09-30

All R1 code/test gates pass. Code/test commit is `ec473eb40d3e28bc7c51a74c3a0a91f7679296f8` / tree `c8f705eec059538d97f635a6b3f886bd5d77faa0`, parent `e28766ad4dc5d186b335d4cca5cecb3ec3930f10`; documentation commit, push, and remote review remain.

- Enforced the persisted `Instrument.kind` gate in the same short session as `freeze_chan_input()`. Missing instruments return `instrument_missing`; non-ETF/LOF instruments return `unsupported_instrument_type`. Both exit before freeze/CZSC/publisher. ETF and LOF continue through the ordinary service path. No other application file changed.
- Confirmed RED first: the two scope regressions failed before the gate because the service proceeded to freeze; after the change, missing/non-ETF/LOF blocked and ETF/LOF path tests passed.
- Historical correction worker test uses the same D as_of, mutates a persisted historical bar's quality hash, and proves the same stream receives a new input hash/observation/sequence while the previous observation/revisions/transitions remain and the head advances.
- Failure-isolation test proves a successful code's committed observation survives another code's controlled publication failure; the failed item has only `publication_failed`. A second injected failure after the existing publisher stages a later write proves transaction rollback keeps the previous head/history intact and leaves the attempted observation absent.
- New worker suite: 24 collected; repository Python 3.13.14: 21 passed / 3 environment skips; Windows Python 3.12.10 and Linux Python 3.12.14: 23 passed / 1 PostgreSQL-fixture skip each. Exact D/W/M CZSC digest remains `66b8092b122ffb1819d18e45963b3f708fca0581550fb062395efc96023096bd` on both platforms.
- Focused A2/M2/M3/workspace/R4A group: 100 collected; 99 passed; 1 environment skip; 0 failures/errors. R4A corporate-action behavior remains included.
- Disposable PostgreSQL 16.15 retry/idempotency/chronology/head-retention gate passes. M2 digest `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac`, R5 history `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9`, and R5 semantic `0f4ae0322b5d390c41e618da4c342abea66baac30bce4ccfe4a5f0d713cff76f` remain frozen; collisions are 0 and weak-ID injection is detected.
- Final Windows repository pytest: 1,374 collected; 1,352 passed; 22 skipped; 0 failures; 0 errors; 35 warnings; 1,514.182 seconds; exit 0.
- Ruff, compileall, Node syntax, scoped secret scan, and diff-check pass.

Evidence is under `E:/Claude_allow/Download/ETF_R4C_M3_20260929/` and `iteration69-linux/`. The disposable PostgreSQL container was removed after the run. No real data, Provider, production DB, deployment, or trading was used.
