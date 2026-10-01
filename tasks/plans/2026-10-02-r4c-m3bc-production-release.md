# R4C M3B-C production release — iteration 71

Authority: the bound ChatGPT conversation's iteration71 R1–R12 plan, subsequent namespace/backup clarification, R5–R7 acceptance and R8 conditional GO; Jovi explicitly authorized unused-remnant cleanup and continuing rehearsals/deployment. Latest state: code deployed; normal authenticated live acceptance pending.

## Objective and boundaries

Deploy exactly reviewed source `3a13575f58ae6f8aad0face1a8e42391d2356518`, tree `70c5ea87fc84ed027202c8df0622f5e44f717a9e`, while keeping Chan producer disabled, real data UNKNOWN, actionable=false and no trading. Owner main and original C-drive checkout are preserved. Execution and documentation remain in the E-drive project-local clone; clean release checkout is `.local/etf-r4c-m3bc-release`.

No application/test/migration/config source edits in this iteration. Post-release documentation changes are separate from the deployed code SHA. Existing production environment/secrets, provider ordering, auth, OCR-disabled state, data volumes, reports/backups, network and service roles are preserved. No source build on the server, real-data refresh or Chan enqueue for acceptance.

## Executed gates

1. R1: freeze clean exact source/GitHub tip/tree — PASS.
2. R2: fresh live discovery; reconcile owner-accepted prior source3069ab72/image config2f3115 while keeping historical approval UNKNOWN — PASS.
3. R3: immutable off-host artifact — PASS. OCI index761530, platform manifestaf22df, configuration547533, archive046708 are distinct identities. Labels and archive hashes must match at transfer/load/runtime.
4. R4: namespace isolation and new backup — PASS. Remove only owner-authorized unused diagnostics after routing/role/mount checks. Use reviewed backup-only script via fully buffered stdin; explicit destination, no retention deletion. Preserve final archive/sha/mode and prior backups.
5. R5: restore that exact backup to local PG16.15 with network none/no ports, 1CPU/1GiB; verify baseline e609200001 and upgrade/current/check to h9c0d1e2f3a4 — PASS.
6. R6: candidate actual process and packaged static/auth smoke, database-session private D/W/M reads, producer guards, 0 SQL DML and unchanged evidence/job/provider counts; worker idle startup and dormant scheduler startup — PASS. No provider/model connectivity from rehearsal.
7. R7: load exact old production archive and prove its configuration2f3115/source3069ab72 despite Docker-store normalization, then run old API on upgraded restored DB. Health/auth/read/static PASS; IMAGE_ONLY rollback demonstrated.
8. R8: remote conditional GO/final operator checklist passed, candidate loaded without build, exact source/tree labels checked, new image-reference-only override hashed, production migration/current and switch PASS. Preserve a ready rollback before every mutation.

Receipts: `docs/audits/R4C_RELEASE_DIAGNOSTIC_CLEANUP_20261002.md`, `docs/audits/R4C_RELEASE_R5_REHEARSAL_20261002.md`, `docs/audits/R4C_M3B_C_PRODUCTION_RELEASE_20261002.md`.

## Remaining live gates

R9 platform is PASS: candidate configuration digest547533 on all three services; API/worker healthy, scheduler running with bounded logs/no restart loop; public health/root/static/private anonymous401 and Alembic h9c0d1e2f3a4 verified. Scheduler has no healthcheck; do not invent one.

R9 private is PENDING normal login. Jovi's login request is already pending. Keep the website and original remote chat available. Never request or inspect passwords, Cookie/Token/session values, create production test users or bypass authentication. A URL-only check may determine whether the normal login completed; do not inspect a password-entry form. Once logged in, use the existing browser session to navigate to `/api/workspace/instruments/510300.SH/chan?interval=D`.

R10: immediately before that authenticated GET, capture only aggregate counts for the four Chan evidence tables, total WorkspaceDataJob, queued/running jobs, Chan jobs and ProviderAudit. Capture safe GET result/flags and repeat same aggregate query immediately afterward. Require unchanged counts and provider/engine/models/qualification/actionable flags false. Snapshot_missing is valid while the producer stays dormant. If concurrent scheduled activity changes unrelated counts, record the attribution and return for remote review; do not silently claim equality.

R11: immediately use the rehearsed IMAGE_ONLY recovery for a candidate identity/schema/health/auth/worker/scheduler regression, GET mutation/enqueue/provider/model/engine execution, unexpected runtime activation or actionable promotion. Recovery uses the retained original three Compose inputs including `deploy-v113-3069ab7/release-images.yml`, `up -d --no-build` for API/worker/scheduler, and exact prior image config2f3115. Keep upgraded schema; no improvised Alembic downgrade, volume removal or backup cleanup. Verify recovery health/auth/process identities.

R12: record switch timestamp, exact deployed code/tree/config and service IDs, backup/hash/mode, production schema, platform checks, normal authenticated GET and same-request before/after proof, and rollback mode. Push documentation-only evidence and prove final docs delta does not change deployed source. Return the readable receipt through C2C records and request remote final iteration71 review at the exact documentation head. If only private login remains pending, report DEPLOYED/PENDING_PRIVATE_LIVE_ACCEPTANCE; do not mark final acceptance PASS.

## Next phase

M4 and main integration remain NO-GO until remote final R12 acceptance. After PASS, ask the same remote conversation for the next detailed product phase and technical-route review, then continue local execution/tests/GitHub/remote review and deploy each deployable phase through its gates. Backend deployment alone does not mean the complete project or real-data qualification is finished. Keep the relay active until the final project goal and final remote review are achieved.
