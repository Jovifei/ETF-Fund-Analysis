# R4C M3B-C — persisted read model and private GET

Date: 2026-09-30
C2C task: `c2c_a1d7`, iteration 70
Plan base: `f6ac2af15373be38797fb57dd6b2aff15b353fa2` / tree `d866390ca5a0fcb852b574b1855a1ad35494e1e8`

## Remote review and gates

Iteration 69 exact-head review returned `M3B_B_DECISION=PASS`, retaining the route and accepting the R1 scope, corrected-history, and publication-failure evidence. Remote authorized `M3B_C_IMPLEMENTATION_GO=true`, with `M3B_C_RELEASE_GO=false`, `M4_GO=false`, `MAIN_INTEGRATION_GO=false`, and `PRODUCTION_GO=false`.

M3B-C is the first coherent user-visible backend product slice. Implementation is authorized; deployment is `DEPLOY_REQUIRED_AFTER_REMOTE_PASS`, but this plan does not authorize production deployment. After implementation is pushed and remote exact-head review returns PASS, a separate release-gate control message must open the backup/restore rehearsal, rollback, and live-smoke work. Until then, production remains untouched, real-data qualification is `UNKNOWN`, and `actionable=false`.

## Objective

Expose only the latest already-persisted R4C observed-revision evidence through one strictly read-only private workspace GET. Reuse the M3 observation/revision/transition/head contract and remove the competing GET-time legacy `chanlun` computation.

Canonical path:

`persisted Chan stream head → verified latest observation → verified structure revisions/transitions → bounded private GET/read model`

The GET must never freeze input, execute CZSC, enqueue jobs, call a Provider/model, or write database state.

## C1 — canonical persisted read service

Add `backend/app/services/chan_read_service.py` with a latest-evidence method, approximately `read_latest(db, code, interval)`. Allow only D/W/M. Return latest persisted evidence; do not add `as_of` or imply historical point-in-time visibility because the schema has no publication-time dimension to prove that contract.

Return an explicit semantic label such as `view_semantics="latest_persisted_observed_revision_not_historical_pit"`.

## C2 — deterministic stream selection

Consider only stream heads matching the requested instrument/interval and the accepted engine namespace: CZSC 1.0.1 and `r4c-observed-revision-v1`. Resolve each candidate's latest observation and verify the head's sequence/ID link.

Multiple heads may exist because price-basis/config namespaces legitimately differ. Select the candidate with the greatest valid `cutoff_at`; use sequence/cutoff only as same-stream consistency checks, not cross-stream chronology. If distinct heads tie at the maximal cutoff and no reviewed deterministic namespace winner exists, fail closed with `available=false, reason_code="ambiguous_stream_head"`. No matching head returns `available=false, reason_code="snapshot_missing"`. Never enqueue to fill a missing head.

## C3 — reuse persisted-evidence integrity checks

Add public read-only wrappers in `backend/app/services/chan_observation_service.py` around the existing private validators, e.g. `verified_observation_payload(row)` and `verified_structure_payload(row, observation_row)`. Do not change publisher behavior or identity formulas.

The read service verifies:

- head stream/sequence/observation ID matches the immutable observation row;
- denormalized observation columns match the verified immutable payload and `payload_hash`;
- every returned revision payload/hash, canonical `structure_key`, and `revision_id` agree;
- the current observation's revision set matches its immutable structures payload.

Any mismatch returns `available=false, reason_code="persistent_evidence_corrupt"`; no partial/tampered structures may leak.

## C4 — bounded response

Return persisted evidence fields only: availability/reason, instrument/interval, stream/observation IDs, sequence, settlement status, cutoff/time, price-basis/adjustment/revision/input hashes, engine identity/confirmation/application status, per-kind counts, structures, and faithful transition/reappearance summary. Side-effect flags are always false: `provider_called`, `engine_called`, `models_called`, `qualification_changed`, `actionable`.

Do not return full OHLCV history, raw exceptions, Provider material, job internals, or action authority. `OBSERVED_ABSENT` may appear in a bounded transition summary but is not a current structure. Empty verified structure sets are valid (`available=true`, zero counts, empty list).

## C5 — private workspace GET

Add a read-model wrapper in `backend/app/workspace/read_model.py` for ETF/LOF validation and presentation mapping. Add one authenticated private GET in `backend/app/workspace/api.py`, preferred contract:

`GET /workspace/instruments/{code}/chan?interval=D`

Allow D/W/M and set `Cache-Control: private, no-store`. No POST, refresh, enqueue, or `as_of`. Missing/non-ETF instruments use the existing workspace instrument-not-found boundary.

## C6 — remove competing GET-time legacy engine

`KlineStabilizationService._chanlun_state()` currently imports the third-party `chanlun` package, rebuilds K-lines during GET, coerces missing volume to `0.0`, and returns independent counts. Make its compatibility `chanlun` field derive only from the canonical persisted R4C read service.

Remove or make unreachable from GET `_chanlun_importable()`, `_chanlun_state()`, legacy GET-time import/engine execution, and missing-volume-to-zero shim. Preserve compatibility count keys as projections of persisted R4C counts, but keep `segments=None` because no reviewed segment structure is published. Add `source="persisted_r4c_observed_revision"`, observation ID, settlement status, `engine_confirmation="unknown"`, and bounded reason. The full canonical evidence remains available through the private GET.

## C7 — update only the completed read-model blocker

In `config/chan_research.json`, remove only `USER_FACING_READ_MODEL_NOT_INTEGRATED` after the private GET and persisted Kline compatibility path are implemented. Preserve `enabled=false`, `qualification_status=BLOCKED`, `selection_status=SELECTED_DISABLED`, and `RUNTIME_INTEGRATION_DISABLED`. No runtime activation, scheduled producer, or real-data promotion.

## C8 — prove zero side effects

For the read service, workspace GET, and Kline compatibility GET, prove before/after counts are unchanged for observations, revisions, transitions, stream heads, `WorkspaceDataJob`, and Provider audit rows. Fail tests if GET calls `freeze_chan_input`, `ChanAdapter.observe`, `enqueue_chan_structures`, `TaskService`, Provider construction, or the model gateway. Reads must work from persisted evidence only.

## Required tests

Add `backend/tests/test_chan_m3b_read_model.py` for:

- no head → `snapshot_missing`, no enqueue/write;
- verified D, W temporary, W settled, and M empty-observation reads;
- intact observation/revision/head consistency;
- tampered observation payload/hash, tampered structure payload/hash, or head/observation mismatch → `persistent_evidence_corrupt`;
- multiple stream namespaces choose the later cutoff; equal maximal cutoffs fail with `ambiguous_stream_head`;
- faithful transition/reappearance mapping; response excludes raw input history and raw exception text;
- private route auth, invalid interval 422, and zero DML/enqueue/CZSC/freeze/Provider/model effects;
- Kline compatibility uses persisted R4C counts only; missing snapshot is unavailable, never a legacy compute fallback;
- config removes only the read-model blocker while retaining disabled runtime state.

## PostgreSQL 16 vertical-slice gate

Use a fresh disposable PostgreSQL 16 database at the existing Alembic head. Seed synthetic ETF history, publish one observation through the accepted M3B-B worker, then read it through the M3B-C service/private route. Prove the GET returns verified structures/revisions, performs zero writes, and a second GET creates no `WorkspaceDataJob`. Corrupt a disposable evidence copy or fixture and prove fail-closed integrity behavior. No production DB.

## Required regression gates

Because this changes shared API/read-model/Kline runtime code, run on the exact final candidate:

- M3B-C read tests, M3B-B worker, M3B-A/A2, M2 contract, M3 persistence, workspace API/jobs, Kline stabilization, and relevant R4A tests;
- full Windows repository pytest;
- M2 exact-CZSC Windows/Linux validators and R5 Windows/Linux validators; frozen digests/collisions unchanged;
- Ruff, compileall, Node syntax, scoped secret scan, and `git diff --check`.

## Authorized files

Primary: new `backend/app/services/chan_read_service.py`; read-only wrappers in `backend/app/services/chan_observation_service.py`; `backend/app/workspace/read_model.py`; `backend/app/workspace/api.py`; `backend/app/services/kline_stabilization_service.py`; `config/chan_research.json`; new `backend/tests/test_chan_m3b_read_model.py`.

Conditional tests: workspace API, Kline, M3 persistence, and `backend/tests/test_chan_m2_contract.py`. Remote iteration-70 `PLAN_UPDATE`s also authorize (1) only the exact config-reason assertion update in the M2 test, with all M2 identity/replay/adapter/digest tests and implementation untouched, and (2) a semantics-preserving Ruff baseline cleanup in `api.py`: convert only the reported chart `as_of` `Query` default to `Annotated`, and add narrow `# noqa: E402` to the intentionally deferred journal/AI router imports. Do not reorder imports or change route behavior. The exact base `f6ac2af15373be38797fb57dd6b2aff15b353fa2` was proven to have the same four findings. Documentation: new M3B-C receipt, B receipt, `STATUS.md`, `HANDOFF.md`, `tasks/todo.md`, `tasks/lessons.md`, and this plan.

Do not modify `chan_input.py`, adapter, contract, `chan_structure_service.py`, worker, data_jobs, protocol/Chan job contract, M3 migration/schema, Provider implementations, or frontend without stopping for remote review.

## Exit and release gates

M3B-C code/test handoff may return for remote review only when the canonical read service, private GET, integrity fail-closed behavior, zero-side-effect contract, legacy Kline path removal, config blocker update, full Windows suite, PG16 vertical slice, M2/R5 frozen gates, and static checks pass. Push the exact candidate and request remote review.

M3B-C is `DEPLOY_REQUIRED_AFTER_REMOTE_PASS`; the current plan does not authorize deployment. After implementation push and remote exact-head PASS, issue a separate release-gate plan/control message covering candidate SHA/tree/image digest, full tests, fresh production PostgreSQL backup/integrity, restore to disposable PG16 and upgrade on restored production lineage, candidate smoke on the restored copy, rollback rehearsal, off-host immutable image build, and live health/auth/worker/Alembic/private Chan GET smoke. If production has no Chan observations, `available=false, reason_code="snapshot_missing"` is valid. Any GET-side write/enqueue/Provider/engine call triggers rollback. M4 remains NO-GO until code review and release/live verification both pass.
