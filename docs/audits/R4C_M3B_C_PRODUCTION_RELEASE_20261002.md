# R4C M3B-C production deployment receipt — iteration 71

Release status: **DEPLOYED / PENDING_PRIVATE_LIVE_ACCEPTANCE**. R1–R7 and R8 switch passed; R9 platform checks passed. Normal browser login for the authenticated live Chan GET and R10 before/after proof is pending. This is not final release acceptance or project completion.

## Deployed artifact

- Code SHA: `3a13575f58ae6f8aad0face1a8e42391d2356518`
- Source tree: `70c5ea87fc84ed027202c8df0622f5e44f717a9e`
- Source branch: `codex/r4c-m3bc-relocated`
- OCI index: `sha256:761530129368e58d9c6e55a1bae324528c4c240376e7be438dc30e8c6d90e5d9`
- Linux/amd64 manifest: `sha256:af22dff26f605f44a74e91d3e5a2d8218d54cb0664b3fa1348065efa2ef76291`
- Configuration digest / server classic Docker image ID: `sha256:547533c55296a808f6fcda8e8c25097a25d3d50284936d4951949227757480db`
- Preserved archive SHA-256: `046708ed613ce862b7b9cf1d45a76fe5a3faf493117e8a8dae0424ba57dc2343`
- Staged archive: `/opt/china-fund-decision/release-preflight-r4c-20261002/candidate-3a13575.tar`; 369938944 bytes; 0600.

No production-host build. Server archive readback matched. Loaded image revision/tree labels matched the reviewed code. OCI index, platform manifest and configuration IDs are distinct, recorded explicitly; server runtime uses the verified configuration ID.

## Accepted prior baseline and backup

Prior production source `3069ab72d9bccd27f0fadeb3996ed445f6ce5446`, tree `ad224b0540a788a055afc33bee107c694dd1115d`, image configuration ID `sha256:2f3115b756a61b34bdad9f0a342526e246118c0ac6f3259f4837733928df3e73`. Jovi accepted it as the current reconciliation/rollback baseline; historical release approval remains UNKNOWN, not retroactively approved.

Fresh backup `/opt/china-fund-decision/backups/fund_decision_20261002_002706_pZSmts.sql.gz`; 341436962 bytes; 0600; SHA-256 `4f5fbc458cefcfa5176326f0e70df88934a09c2cabac4c8248c62e71bd79de53`; independent gzip and checksum-file verification PASS. All old backups retained. Backup restored and migrated on disposable PG16.15, network none/no ports; baseline e609200001/38 public base tables, upgraded h9c0d1e2f3a4/43 tables, Alembic check clean.

Exact old-image archive `previous-2f3115b7.tar.gz`, size 395139426 bytes, SHA-256 `e4f0fe3c7422981329170e2c2dad24c273780d6d0d974c33eb426945dd928ae8`, preserved privately. **IMAGE_ONLY** rollback demonstrated with this exact image on upgraded restored schema, actual healthy API, static and session-authenticated read/auth boundary PASS. No downgrade needed.

## Production migration and switch

Remote iteration71 accepted R5/R6/R7 and authorized R8 after the final checklist. Existing three Compose inputs retained and their hashes unchanged. New `/opt/china-fund-decision/deploy-r4c-m3bc-3a13575/release-images.yml` changes only API/worker/scheduler image reference plus `pull_policy: never`; SHA-256 `7455b8fa51e97afd837a6756c3ad3974e03147171d24df0d268d0946f4646d47`.

Existing environment/secrets, PostgreSQL volume, reports/backups, network topology and service roles preserved. Explicit accepted live settings retained: production, APP_VERSION=1.0.8, public_composite, OCR disabled, secure database authentication, auto-create false, mock fallback false, LLM/analysis false. Source defaults remain 1.0.5 in both prior and candidate code; the live display version is an existing environment override. Git proves prior live source is an ancestor of the candidate.

First SSH migration launch timed out before connection. The next invocation was rejected by old Compose's unsupported `run --pull` flag, exit16; independent check confirmed unchanged e609200001 schema and healthy old site. Corrected syntax retained the override's pull policy and applied the exact candidate Alembic upgrade with exit0. Independent current/head-match checks passed at h9c0d1e2f3a4. Failed-launch logs retained privately; no raw credential logs offered to the reviewer.

Switch initiated `2026-10-02T01:36:44+08:00`; `compose up -d --no-build api worker scheduler` exited0. No source checkout pull/build or other application mutation.

| Service | Container ID | Image config | Result |
| --- | --- | --- | --- |
| API | `6d9083a567747edaf6b64bee453307604dcbdd5fca5e574723dc95566be456d0` | `547533c5...` | running/healthy, restarts0 |
| Worker | `c312803a941f5c71fb8f45359fd328f343af12b7906515f4847441e7220ced5b` | `547533c5...` | running/healthy, restarts0 |
| Scheduler | `dd18365e064a1b1fde443551be0f4d78039cdc1c28bf14852727ce095d8055de` | `547533c5...` | running, restarts0, no configured healthcheck |

## Live checks

- Public `/api/health`: status ok, production, auth enabled, display version1.0.8, public_composite.
- Packaged Vue deep links, root, CSP, static assets, private anonymous boundary and 404 semantics: PASS on actual deployed API.
- Public anonymous Chan GET: HTTP401.
- Actual live Alembic current: h9c0d1e2f3a4.
- Bounded API/worker/scheduler logs since switch, last200 lines per service: 0 crash/error-loop markers.
- Disk after loading/switch: 3037164 KiB available. No rollback trigger observed.
- Chan configuration: enabled=false, qualification_status=BLOCKED, selection_status=SELECTED_DISABLED, reasons=[RUNTIME_INTEGRATION_DISABLED].

Initial live aggregate counts: each of four Chan evidence tables0, WorkspaceDataJob3, queued/running0, Chan jobs0, ProviderAudit27229. Metadata-only snapshot stored in `R4C_RELEASE_INITIAL_LIVE_COUNTS_20261002.json`. This is not the final R10 before/after comparison: refresh the baseline immediately before the authenticated live GET.

## Remaining gates

Jovi's normal login in the prepared website browser is pending. Do not create production test users, read passwords/Token/Cookie/session contents, or bypass authentication. After normal login, request `/api/workspace/instruments/510300.SH/chan?interval=D` through the normal browser session. Snapshot_missing is valid while runtime is disabled. Capture only safe response flags and compare same-request before/after aggregate evidence/job/provider counts.

Return completed R9/R10 and this receipt to the remote for final iteration71 acceptance. M4/main remain false until that review.

`CODE_DEPLOYED=true`; `R4C_BACKEND_RELEASE_DEPLOYED=true`; `R4C_RUNTIME_ACTIVATED=false`; `REAL_DATA_QUALIFICATION=UNKNOWN`; `ACTIONABLE=false`; `AUTO_TRADING=false`. `R9_PRIVATE=PENDING`; `R10=PENDING`; `R12_FINAL_ACCEPTANCE=PENDING`.
