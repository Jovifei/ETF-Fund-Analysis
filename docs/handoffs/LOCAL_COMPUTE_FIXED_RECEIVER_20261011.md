# Fixed local Codex receiver — 2026-10-11

Jovi authorized local implementation with webpage GPT review. Receive implementation commit `f514a6ec889d79109df12314947c8e77ed1948be` on `codex/local-execution-20261011`, source tree `ba18dbfe20117afb46469f6b7b0b2b4a4fd150a0`, [Draft PR45](https://github.com/Jovifei/ETF-Fund-Analysis/pull/45). Phases:017c313 sector evidence/current summary guard; b393225 disabled shadow synchronization;1595fcf research helper horizon/time-axis contract and primary-source OSS assessment; d6dd03a HMAC authentication;178bb43 storage fault tests;8e0f9e7 offline collection/checkout/byte-budget hardening;f514a6e explicit scheduled working directory. Receipt/docs-only successors must not replace this implementation identity without inspecting the actual tree.

## Receive and validate
Read AGENTS.md/STATUS.md/HANDOFF.md. Fetch and check commit/tree; protect Owner untracked files, environments, users, holdings and databases. Create an independent clean worktree; do not reset/clean/stash/switch another writer's checkout. Prefer existing Python3.12 and Node>=22.18.0. Only if missing dependencies, use dedicated venv and project pyproject extras; optional market dependencies are needed for complete provider-candidate tests, not permission to call live markets. No GPU/model packages required.

Run in the received worktree:
```
npm ci --ignore-scripts --prefix frontend
npm run test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
python -m pytest -q --junitxml=local-results.xml
python -m compileall -q backend/app scripts
node --check backend/app/static/app.js
```
Use the isolated interpreter for every Python command. Do not relax assertions/skips when dependencies are absent; document the environment and original failures. The real database-login/offline shadow test is backend/tests/test_shadow_export.py::test_export_https_transport_real_cookie_same_manifest; storage/type/auth tests are test_shadow_bundle.py, test_shadow_input_types.py and test_shadow_api.py; sector cutoff/current digest and research helper tests remain required. frontend/tests/shadow-chart-consumer.test.ts verifies public projection interoperability, not physical mobile or DPR quality.

## Storage, jobs and receiver boundary
Raw data and deterministic computation belong in a dedicated local SQLite directory outside source/production, e.g. E:/ETF_Data/ETF-Fund-Analysis. The code requires an ownership .shadow-local marker plus existing research.sqlite3; no production connection string, holdings/user DB or private dotenv is imported. Current executable jobs enforce offline Mock. Preparing actual licensed datasets/provider mode is a separate reviewed integration; do not fake that by copying production DB. Do not create a new empty production database to satisfy the guard.

scripts/shadow_local_job.py runs existing audited Mock collection/indicator/forecast/signal/board tasks and exports a read-transaction generation. scripts/shadow_snapshot.py supplies offline export/publish/compare. Optional HTTPS upload goes through a dedicated write-only producer credential (environment input; do not print/copy into Git or use a user/admin credential). Ordinary authenticated website sessions read shadow data; producer credentials cannot read portfolios or users.

Optional Windows registration is explicit via scripts/register_shadow_task.ps1 with Python/workspace/root/database/fixedCodeSha and optional HTTPS SyncUrl. Default slots14:30,14:45,14:50,14:55,15:00,15:15; calendar-valid market days only, no machine timezone changes, no Codex-chat dependency. A real temporary one-time offline Windows task at8e0f9e7 completed with result0 and was unregistered; this is not permanent registration, logoff/reboot acceptance, or validation of all registrar triggers. Fixedf514a6e CLI and local verified TLS upload/restart replay rejection also passed. Public WAN upload, live providers and persistent production jobs remain NOT_RUN; don't enable them silently.

SHADOW_SYNC_ENABLED defaultsfalse. Receiver code/config must match exact producer identity. Bounded content-addressed blobs/manifest, atomic latest pointer and retained previous protect partial/out-of-order/replay/expired input. Managed GC is confined to this new store; do not apply it to existing reports/backups/database/images. A crash-owned publisher lock requires operator inspection rather than blind stale-lock deletion.

The manifest supports1d only. Public indicators, SR references and raw/research price basis travel together; cost overlays/private holdings are excluded. Market source timestamps can remain unknown. No calibrated/actionable/source-license qualification is promoted. Canonical Vue/API and production scheduler/database stay on the previous path until explicit reviewed cutover; this is not yet full remote-compute retirement or all-period migration. HMAC uses separate producer signing and bearer credentials; never reuse account/admin credentials. See the recovery contract and nonce lifecycle in the architecture document.

## Return evidence and remote review
Return exact tested SHA/tree, env versions, command exitcodes, actual PASS/FAIL/SKIP/NOT_RUN, source/code/config/input hashes and sanitized offline receipts. GitHub receives source and sanitized review evidence only, never raw licensed quotes, holdings, credentialed result packages, cookies or private datasets. Ask webpage GPT in the same fund project to inspect PR45/full source, address concrete findings and choose the next complete stage. Do not deploy this shadow architecture merely because local tests/CI green; require exact release recommendation and production activation authorization/backup/rollback. Real-provider/PIT/OOS, privateR10, phone, and existing DPR2/collision gates remain independent.
