# Iteration 71 restored-production release rehearsal

Status: R3/R4 PASS locally; R5 transfer/preparation in progress; R6/R7 and production switch NOT_RUN.

Exact candidate source: `3a13575f58ae6f8aad0face1a8e42391d2356518`; tree `70c5ea87fc84ed027202c8df0622f5e44f717a9e`. Clean detached checkout: `E:\project\ETF-Fund-Analysis\.local\etf-r4c-m3bc-release`.

## Distinct artifact identities

- OCI index digest / local Docker 29 image ID: `sha256:761530129368e58d9c6e55a1bae324528c4c240376e7be438dc30e8c6d90e5d9`
- Linux/amd64 OCI manifest: `sha256:af22dff26f605f44a74e91d3e5a2d8218d54cb0664b3fa1348065efa2ef76291`
- Image configuration digest: `sha256:547533c55296a808f6fcda8e8c25097a25d3d50284936d4951949227757480db`
- Exported archive SHA-256: `046708ed613ce862b7b9cf1d45a76fe5a3faf493117e8a8dae0424ba57dc2343`

Archive OCI index explicitly maps the preserved tag to the same `761530...` index. The `547533...` number previously recorded is the configuration digest, not the OCI index. There is no candidate drift. Revision/tree labels match the exact reviewed source. Offline `pip check` PASS. Candidate `alembic heads`: `h9c0d1e2f3a4`.

## Backup and isolation

Fresh production archive: `/opt/china-fund-decision/backups/fund_decision_20261002_002706_pZSmts.sql.gz`; 341436962 bytes; mode 0600; SHA-256 `4f5fbc458cefcfa5176326f0e70df88934a09c2cabac4c8248c62e71bd79de53`. Gzip/checksum verification PASS; PostgreSQL source 16.15. Retained on production. Copy to designated local download directory is in progress; no restore acceptance before exact full local hash verification.

Local disposable PG16 container `etf-r4c-r5-20261002`: network `none`, no published ports, 1 GiB memory limit, 1 CPU. Ready check PASS. Only this disposable database may be restored/migrated; no production database writes.

## Connection repair

Read-only diagnosis established the saved ETF bridge PID was absent and its saved endpoint answered for the Tesla workspace. Removed only the proven stale ETF runtime metadata through the C2C runtime API, then started the normal ETF bridge with the existing fixed domain/auth/chat binding. Doctor now confirms ETF workspace, bridge, unauthenticated MCP 401, OAuth and tunnel PASS; no connector recreation or Tesla service mutation. Session task/chat remains `c2c_a1d7`, iteration 71.

Jovi authorized unused-diagnostic cleanup; three old v106 diagnostics removed, production namespace conflict cleared and health OK. See `R4C_RELEASE_DIAGNOSTIC_CLEANUP_20261002.md`.

Next: verify downloaded backup hash; restore to the isolated copy, record baseline Alembic, run exact candidate upgrade/check; candidate smoke and zero-side-effect GET; exact previous-production-image rollback proof. No production switch until all R1-R7 gates PASS. M4/main remain false; real data UNKNOWN; actionable=false; no trading.

## R5 result — PASS

Downloaded archive hash equals the production checksum. Restore into the disposable local PG16 exited 0. Restored public base-table count: 38; baseline Alembic `e609200001`; database ready. The initial migration invocation exited 1 before database migration because the rehearsal environment lacked the production-required OCR private temporary directory. Retained as a configuration preflight failure; no candidate source edits. With the checked-in Compose contract's private OCR tmpfs, candidate upgrade exited 0, current is `h9c0d1e2f3a4`, and `alembic check` exited 0 with no new operations. Public base tables after upgrade: 43. Network remains `none`, no published ports.

## R6 result — PASS

Exact candidate API runs healthy in the disposable PG network namespace. Packaged Vue deep links, CSP, static assets, private unauthorized requests and 404 semantics PASS.

Actual database-backed session authentication was exercised with a new test-only admin identity in the disposable copy; no real account credential was used or output. Anonymous private reads returned 401; authenticated ordinary holdings read returned 200. D/W/M Chan GET and repeated GET returned HTTP 200 with `available=false`, `reason_code=snapshot_missing`, `Cache-Control: private, no-store`, and all producer/model/qualification/action flags false.

Before/after counts: observations/revisions/transitions/heads each 0, WorkspaceDataJob 3, ProviderAudit 27208. SQL instrumentation saw 0 INSERT/UPDATE/DELETE/REPLACE/MERGE/COPY. Fail-on-call guards covered freeze, CZSC observe, Chan enqueue, TaskService, Provider construction and model/legacy Chan imports.

Worker `--once` exited 0 with no queued jobs and discovery/daily review disabled. Scheduler started without restarts in its supported `SCHEDULER_ENABLED=false` waiting mode and stopped gracefully with exit 0; no scheduler tick or provider run was performed in rehearsal. Job/provider/observation counts remained unchanged after process smoke. This is dormant-process startup evidence, not real-data qualification.

## Deployment compatibility facts

Git proves live source `3069ab72d9bccd27f0fadeb3996ed445f6ce5446` is an ancestor of candidate `3a13575...`. Both source versions default `app_version=1.0.5`; live deployment explicitly overrides `APP_VERSION=1.0.8`, explaining the health-display difference without code regression. Nonsecret live settings show OCR disabled, auth/cookie secure true, auto-create false, mock fallback false, analysis/LLM false, workspace UI true. Live provider selection is `public_composite`; preserve the owner-accepted live configuration per the release plan, and report this selection explicitly during remote release review rather than silently changing provider ordering. Initial isolated candidate probes used `composite`; no Provider was invoked.

Candidate archive staged on production in the dedicated preflight directory; SHA-256 readback matches `046708...`, size 369938944 bytes. Image not loaded and production not switched. Exact previous-production image exported privately, gzip PASS, size 395139426 bytes, mode 0600, SHA-256 `e4f0fe3c7422981329170e2c2dad24c273780d6d0d974c33eb426945dd928ae8`; local transfer pending.

R7 remains PENDING. Return complete R5-R7 evidence to the remote reviewer before production switch.

R6 read/auth/zero-DML probe was repeated with the accepted live nonsecret settings: `APP_VERSION=1.0.8`, `MARKET_PROVIDER=public_composite`, `OCR_MODE=disabled`, secure auth and disabled analysis/LLM. PASS with identical six table counts and 0 DML; no Provider invoked. Live provider selection is not silently changed. Candidate archive mode tightened to 0600 without changing its checksum.

## R7 result — PASS / IMAGE_ONLY

Exact previous-production archive fully transferred and SHA-256 verified against `e4f0fe...`. Docker29 normalizes the server image representation to local image ID `sha256:1e0c8c650ab8a6bc9ba9c2e17f199796c6ac5e4af3f01db36680746587336757`. Both the original server archive and a re-export of the local image contain configuration digest `sha256:2f3115b756a61b34bdad9f0a342526e246118c0ac6f3259f4837733928df3e73`; source revision `3069ab72d9bccd27f0fadeb3996ed445f6ce5446` and source tree `ad224b0540a788a055afc33bee107c694dd1115d` match. This is an image-store representation distinction, not a rebuilt substitute.

Stopped only the disposable local candidate API, then started this exact previous image against the already upgraded disposable database with the accepted live nonsecret configuration. Actual old API process is healthy, 0 restarts; packaged Vue/CSP/static/private unauthorized/404 smoke PASS. A new test-only identity on this isolated copy proved real database-session authentication and ordinary authenticated read; health/root/unauthenticated 401/authenticated 200 all PASS, 0 SQL DML during reads. Database remains `h9c0d1e2f3a4`.

`ROLLBACK_MODE=IMAGE_ONLY` demonstrated. No Alembic downgrade and no production switch occurred. PostgreSQL rehearsal runtime `16.15`; candidate Python `3.12.14`.

## Proposed production procedure for remote review

Preserve the current production base `production-v112-0038c43.yml` plus `freshness-825767c.override.yml`, environment/secrets, reports/backups and DB volume. Add only a last release-image override for API/worker/scheduler targeting the verified candidate, with pull policy never. Before any migration/load, recheck source labels, server artifact hash, disk/resource availability and old rollback image availability. Load the verified archive without building, reconcile server Docker image/config identity, run candidate migration through the established Compose environment, then switch only the three application services with `--no-build`.

Rollback: original three-file Compose set (including `deploy-v113-3069ab7/release-images.yml`) with `--no-build`, preserving upgraded schema and data; expect exact old config image `2f3115...`. Apply immediate rollback for any migration/image/health/auth/worker/scheduler/read-side-effect/runtime-activation failure per the remote R11 plan.

R1-R7 local preflight PASS; R8 switch remains pending remote review. Live authenticated HTTP smoke requires Jovi's normal login in the prepared private website browser; login request is pending. No real user password/session is read, no production test user is created. Public health/static and anonymous 401 smoke can be performed automatically; private live GET must use the browser's normal session after login. Final release acceptance and M4 remain pending until all live evidence is reviewed.
