# v0.5.0 Local Validation Execution Plan

## v1.0.1：本地真实数据接入（2026-09-06，进行中）

- [x] RED：为来源就绪状态写测试；状态只能公开能力、依赖和资格，绝不回显 Tushare Token。
- [x] GREEN：提供 `/api/workspace/data-sources`；解析运行时配置后的有效来源，不发起网络调用、不触发模型。
- [x] RED：为本地初始化器写测试；它必须显式拒绝 Mock、禁止自动 fallback、要求仓库外 SQLite 数据库。
- [x] GREEN：实现 1–3 只 ETF 的受限本地初始化命令，通过现有 `WorkspaceDataJob → TaskService` 链路入库，并输出脱敏结果。
- [x] 验证：以 AKShare 对 3 只 ETF 执行小样本真实日线初始化；不将盘后/无资格 quote 标为实时，不启用模型或自动交易。
- [x] 发布：更新版本记录为 v1.0.1，完成专项测试、类型构建、迁移和数据源资格检查；全量 pytest 在既有校准顺序阻塞处未完成，记录后提交、标记并推送。

## Multi-user security remediation (2026-09-01, active)

### Browser identity / regression / deployment handoff repair (2026-09-02, in progress)

- [ ] RED: prove a valid legacy Bearer can use only compatible safe reads and is never reported as a browser identity by `/api/auth/me`.
- [ ] RED: make the global review mutation use an enrolled database-admin session, retain an explicit Bearer 401 assertion, and isolate the SSE/backfill rows from suite-wide state.
- [ ] GREEN: expose a current-admin self-disable action only when a second active admin is listed; preserve the backend last-admin guard and clear the revoked browser session after self-disable.
- [ ] GREEN: replace obsolete production/browser single-account configuration instructions with database-auth bootstrap requirements; distinguish historical migration evidence from current head `2c3d4e5f6a7b`.
- [ ] Review: run focused suites, then full pytest sequentially with the project venv, plus compileall, Node syntax, and diff checks; record explicit exit codes. No commit/deploy.

### CLI / report-list consistency remediation (2026-09-02, in progress)

- [x] RED: auth-disabled `holding-set` was rejected for missing `--username`; an owned external `.json` was listed (`2 failed`, exit 1).
- [x] GREEN: `holding-set`/`holding-delete` now use `user_id=NULL` only with `Settings.auth_enabled=false`; auth-enabled mode rejects missing/disabled accounts and uses the explicit active owner's ID. Direct regression also proves another active user cannot delete that owner's holding.
- [x] GREEN: `GET /api/reports` now injects `Settings` and applies strict candidate resolution plus `relative_to(settings.reports_dir.resolve())`; it exposes only owned, safe, regular in-root `.html`/`.json` files after filtering.
- [x] Review: final new regressions `2 passed` (exit 0); auth/ownership modules `42 passed, 1 skipped` (exit 0); sequential full pytest exit 0; `python -m compileall -q backend/app`, `node --check backend/app/static/app.js`, and `git diff --check` each exit 0. Only pre-existing third-party deprecation/CRLF warnings were emitted. No commit/deploy.

### Report artifact stale-file regression (2026-09-02, complete)

- [x] RED: temporary restoration of the prior SQL-limited list returned the newer `unsupported-system.txt` instead of the valid JSON (`test_multi_user_ownership.py -k stale`, exit 1).
- [x] GREEN: retain owner/session filtering; only expose existing `.html`/`.json` artifacts under their safe basename, and apply `limit` after filtering valid rows.
- [x] Review: focused stale regression passed (1 passed/9 deselected, exit 0); sequential ownership/API/optimizer/ETF-1430 suites passed (31 passed, exit 0); `compileall`, Node syntax, and `git diff --check` each exited 0. No commit/deploy; diff check emitted only existing CRLF notices.

- [x] RED: prove shared signal persistence is independent of all user holdings.
- [x] RED: prove members and legacy Bearer cannot perform global mutations while admins can.
- [x] GREEN: isolate shared signal generation and add explicit active-admin authorization for global controls.
- [x] GREEN: bind private reports/SSE/optimizer to an authenticated owner; make ownership migration portable and rollback-safe.
- [x] Review: run focused tests, migration checks, compileall, Node syntax, and diff check; record outcomes.

### Follow-up security/UI review fixes (2026-09-02, complete)

- [x] RED/GREEN: bind each long-lived SSE iteration to its original database session and stop after revocation, expiry, reset, or account disable.
- [x] RED/GREEN: serialize active-admin disable checks through the existing database guard and prove a two-session race retains one active admin.
- [x] RED/GREEN: render the current authenticated identity and admin-only account lifecycle controls without exposing credentials or controls to members.
- [x] Review: focused suites passed separately: auth 21 passed/1 safe PostgreSQL skip, ownership 13 passed, password/static 27 passed, API 11 passed, and migration/optimizer/ETF1430 9 passed. The single combined-order run has one pre-existing report-artifact 404 after the ownership suite; `test_api.py` passes alone. Compileall, Node syntax, and diff checks are recorded below.

### Multi-user remediation review (in progress)

- [ ] Final spec review: prove an admin may self-disable only while another active admin remains, and that the current database session is revoked.
- [ ] Final spec review: make blank login credentials reach the generic 401 path, then update migration-head references without erasing historical chain context.
- [ ] Final spec review: run focused auth/ownership/API/static/migration checks plus compileall, Node syntax, and diff validation; record exact exit codes.

- P0 focused red/green: `test_global_mutations_require_an_active_admin_session` first failed because a member received 200 from `POST /api/demo/load`; after explicit `require_admin`, it and `test_shared_signal_refresh_is_independent_of_every_users_holdings` pass (2 passed).
- P0 implementation: scheduled shared refresh no longer queries `Holding` or persists holding/current-weight evidence or input hashes; user overlays remain a read-path concern. Global mutation gates cover decision-board refresh, Demo load/reset, board fund management, runtime settings/probe, task execution/history, and global analysis review mutations/reads.
- Current checks: `python -m compileall -q backend/app`, `node --check backend/app/static/app.js`, and `git diff --check` passed. Existing line-ending warnings were emitted only.
- P1 completion: database-backed lifecycle is admin-only (`/api/admin/users` and hidden-prompt `auth-*` CLI), disable/reset revoke all sessions, and disabled-session reactivation requires a fresh login. Auth-enabled reports/downloads/SSE require a database session; per-user reports, ETF 14:30 artifacts, and portfolio optimization reports carry `user_id`, while deliberate auth-disabled/system artifacts remain `NULL` and are never exposed to authenticated users.
- P1 verification: `test_multi_user_auth.py`, `test_multi_user_ownership.py`, `test_migration_schema_parity.py`, `test_portfolio_optimization.py`, `test_etf_1430_workbench.py`, and `test_api.py` passed in the focused rerun (one existing skip). The migration test also creates two owners for one instrument and proves downgrade to `0a9b1c2d3e4f` aborts. Ruff on changed P1 files, compileall, Node syntax, and `git diff --check` passed.

> **For agentic workers:** REQUIRED SUB-SKILL: use `subagent-driven-development` task by task. Every task is implemented or executed by a fresh Luna/xhigh agent, followed by a fresh specification reviewer and then a fresh code-quality/evidence reviewer. The main agent controls scope, resolves blockers, integrates results, and performs final verification.

**Goal:** Audit and validate the current v0.5.0 ETF/LOF research system using the actual local working tree, then produce an evidence-backed `deployment_reports/local-v050-validation.md` without exposing secrets or overstating Mock/unavailable results.

**Architecture:** Treat all existing tracked modifications as owner work and preserve them. Validation is read-only except for this task ledger, generated local artifacts, and the final report; any code fix must first reproduce the failure with a test and follow red-green-refactor. External/provider outputs are untrusted and must be classified by provenance, freshness, and availability.

**Tech stack:** Python 3, FastAPI, SQLAlchemy, pytest, Node.js syntax checking, PowerShell, optional Bash, Tushare/AKShare provider adapters, deterministic indicator/backtest/forecast services.

---

## Safety and provenance boundary

- [x] Confirm repository root: `E:\project\ETF-Fund-Analysis`.
- [x] Confirm HEAD: `ae755dfd89549abeaf772ac8c34152e80391210d` (`feat: add v0.5.0 indicator and strategy engine`).
- [x] Confirm current branch: `main` tracking `origin/main`.
- [x] Detect a dirty working tree and preserve all pre-existing tracked/untracked content.
- [x] Verify the dirty tree includes substantive user changes in 16 files in addition to line-ending noise.
- [x] Do not reset, clean, stash, checkout, stage, commit, pull, push, or rewrite owner files.
- [x] Do not read or emit `.env`, tokens, cookies, passwords, account data, public IPs, or signed URLs.
- [x] Only report whether `TUSHARE_TOKEN` is configured or missing; never print its value.
- [x] Never label daily-close fallback as realtime, Mock as real, or `not_calibrated` as calibrated.
- [x] Do not modify strategy thresholds/formulas merely to improve validation output.

## Task 1: Repository and implementation audit

**Inputs:** `AGENTS.md`, `STATUS.md`, `HANDOFF.md`, `VALIDATION.md`, `CODEX_DEPLOYMENT_TASKS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/STRATEGY_AND_VALIDATION.md`, `docs/GITHUB_RESEARCH.md`, the eight core service/source files named in the handoff, related tests, `config/watchlist.json`, `config/strategy.json`, and `scripts/provider_smoke.py`.

- [x] Read the required documents and source/tests without opening secret files.
- [x] Record current provider, strategy, indicator, forecast, and schema/version identifiers.
- [x] Reconcile stale 0.4.0 documentation claims against the v0.5.0 code and current working tree.
- [x] Inspect the 16 substantive dirty files and attribute them as pre-existing owner work.
- [x] Inventory commands, outputs, report paths, and prerequisites for Tasks 2-6.
- [x] Luna implementer/auditor self-review complete (`DONE_WITH_CONCERNS`: effective runtime is v0.4 and ablation is not wired).
- [x] Luna specification review confirms full audit scope and no secret exposure.
- [x] Luna quality/evidence review approves findings with required pre-execution fixes recorded below.

### Task 1 durable evidence

- Current HEAD is the requested v0.5 commit, but the actual dirty working tree reports app `0.4.0`, `signal-v0.4.0`, `indicator-v0.2.0`, and `similarity-v0.2.0`; runtime task/indicator wiring uses the v0.4 services.
- v0.5 modules and direct strategy-engine tests exist, but the current task service does not register `backtest_ablation`; calling it through the current CLI reaches `UnknownTaskError`.
- The 16 substantive pre-existing dirty paths are: `.gitignore`, `README.md`, `STATUS.md`, `THIRD_PARTY_NOTICES.md`, `VALIDATION.md`, `backend/app/core/config.py`, `backend/app/services/indicator_service.py`, `backend/app/services/task_service.py`, `backend/tests/test_backtest.py`, `backend/tests/test_indicators.py`, `backend/tests/test_pipeline.py`, `config/strategy.json`, `deploy/.env.production.example`, `docs/GITHUB_RESEARCH.md`, `pyproject.toml`, and `vendor/manifest.json`. This is path attribution only; author and intent are unknown.
- `tasks/todo.md` is the only current-turn file at this checkpoint.
- Existing repository reports are historical Mock/v0.4 artifacts and are not current validation evidence.
- Baseline pytest isolates its SQLite database but not its report directory. Task 2 must set explicit temporary `DATABASE_URL` and `REPORTS_DIR` before imports.
- Provider/live execution is gated pending regression-tested exception redaction plus explicit realtime and trade-calendar provenance. A smoke exit code of zero is not sufficient proof of execution-grade realtime data.
- `FILE_MANIFEST.txt`, `SOURCE_INFO.json`, and example artifacts are stale relative to HEAD/current v0.5 files; they remain owner work and will be labeled, not silently regenerated.

## Task 2: Complete local baseline verification

**Commands:**

```powershell
pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
```

If Bash exists:

```powershell
bash -n deploy/aliyun/bootstrap_host.sh
bash -n deploy/aliyun/deploy.sh
bash -n deploy/aliyun/update.sh
```

Secret scanner:

```powershell
python codex/skills/fund-research/scripts/check_no_secrets.py .
```

- [x] Capture Python, OS, Node, Bash availability and exact pass/fail results.
- [x] If a failure occurs, reproduce and diagnose before any fix; do not delete tests or weaken gates.
- [x] Any required fix follows TDD and touches only the minimal files.
- [x] Luna implementer self-review complete (`DONE_WITH_CONCERNS`: initial environment blocked; isolated rerun passed with one deprecation warning).
- [x] Luna specification review passes after correcting DB-isolation and bytecode-attribution overclaims.
- [x] Luna quality/evidence review passes; baseline uses an external Python 3.12 venv and explicit Git Bash.

### Task 2A: Windows pytest fixture lifecycle fix (TDD)

**Modify:** `backend/tests/conftest.py`

- [x] **RED:** In a clean Python 3.12 venv and disposable working-tree copy, run `<venv-python> -m pytest -q`; all 10 test progress markers complete, then session teardown fails at `backend/tests/conftest.py:32` with `PermissionError: [WinError 32]` while unlinking SQLite.
- [x] **RED evidence for report isolation:** The disposable copy's repository `reports/` receives two files because the fixture does not set `REPORTS_DIR` before settings import.
- [x] Import `get_engine` with the existing delayed `app.db.session` import and dispose the engine in a `finally` block before unlinking `TEST_DB`.
- [x] Create a session-owned `TemporaryDirectory` for reports before settings import, set `REPORTS_DIR` to it, and clean it in the same fixture teardown.
- [x] Copy only the updated fixture into the existing isolated source copy and rerun `<venv-python> -m pytest -q`; observed: 10 passed, exit 0, no teardown error.
- [x] Verify the source-copy repository `reports/` receives no new current-run files and the original repository's explicit status path list changes only at `backend/tests/conftest.py` plus `tasks/todo.md`.
- [x] Re-run compileall, Node syntax, three explicit Git Bash syntax checks, and the scoped secret scanner in the isolated copy.
- [x] Luna implementer self-review complete.
- [x] Luna specification review passes.
- [x] Luna quality/evidence review passes; one non-blocking defensive cleanup-order Minor remains documented.

### Task 2 evidence

- Allowed run root: `E:\Claude_allow\Download\etf-v050-baseline-20260828-010724-5733a2a2a57a4769bb639ada797e2cfb`.
- RED: Python 3.12 dependencies installed in an external venv; 10 tests executed but session teardown failed with Windows `WinError 32` because the pooled SQLite engine retained the test DB handle. The RED run also wrote two reports inside the disposable source copy.
- GREEN: fixture now sets a session temporary `REPORTS_DIR` before settings import and disposes the engine before deleting SQLite. Isolated rerun: `pytest -q` exit 0 with 10 passed; compileall, Node syntax, scoped secret scan, and all three explicit Git Bash `bash -n` checks exit 0.
- Green teardown removed the SQLite DB and fixture report directory; no green `reports/` directory remained. Historical RED artifacts remain under the allowed run root for evidence.
- Python 3.12.10 matches CI's major/minor. Local Node 24 differs from CI Node 22. Pytest emitted a non-failing Starlette/httpx deprecation warning.
- Scoped secret scan excludes Git history, env files, vendor, reports, backups, caches, and is not proof those excluded areas are clean.

## Task 3: Provider capability and ETF universe validation

- [x] Inspect `scripts/provider_smoke.py` before execution for output/redaction safety.
- [x] Check only whether `TUSHARE_TOKEN` is configured/missing.
- [x] Run a non-persistent safe provider capability path where prerequisites permit; preserve only whitelisted provider, operation, success/failure, record count, latency, fields, and error class. Direct `provider_smoke.py` was not used because it can emit raw exception/degradation text.
- [x] Build separate Tushare and AKShare capability matrices covering implemented instrument, daily-history, spot, news, and trade-calendar paths.
- [x] Mark unavailable/configuration/single-run/unverified results literally; do not synthesize realtime capability.
- [x] Inspect `config/watchlist.json`; report total/enabled counts, ETF/LOF counts, duplicates, required-field coverage, themes, markets, benchmarks, and obvious demo entries.
- [x] Do not rewrite the universe in this phase.
- [x] Luna implementer self-review complete (`DONE_WITH_CONCERNS`).
- [x] Luna specification review passes after persisting the sanitized evidence JSON.
- [x] Luna quality/evidence review passes with a No-Go for real provider ingestion/history validation.

### Task 3 evidence

- Sanitized artifact: `E:\Claude_allow\Download\etf-v050-baseline-20260828-010724-5733a2a2a57a4769bb639ada797e2cfb\evidence\provider-capability-sanitized.json`; SHA-256 `c556af27ab344eb899540e05e8d56e457ca061d05947e01a8592e34ed1fcf3ee`.
- Tushare: `TUSHARE_TOKEN missing`; provider was not initialized or called, so permissions/capabilities are untested rather than failed.
- AKShare single-run observation: instruments 5, daily bars 32, spot quotes 3 with 3 adapter-classified non-degraded records, news 0, calendar unverified. Spot latency was about 25.6 seconds.
- Composite without Mock: instruments and spot succeeded; daily bars failed with `ProviderError`; news empty; calendar unverified. Independent AKShare daily success does not establish Composite stability.
- The spot run occurred outside market hours; AKShare adapter assigns local call time and `is_realtime=True` to matched rows. It is not verified exchange-time freshness or stable realtime capability and cannot support actionable signals.
- Universe: demo 10, enabled 9, disabled 1, ETF 9, LOF 1, SH 9/SZ 1 derived from suffix, no duplicate code/symbol, themes populated, benchmark 4/10, no explicit market field.
- Real provider-backed ingestion and real history/indicator validation are blocked. Task 4 may continue only with isolated Mock/local deterministic evidence.
- Known product gaps remain: raw exception strings in provider smoke/audit/log paths, no verified calendar provenance, and no safe persisted runner/command manifest. These require a separately approved design before behavior changes.

## Task 4: Historical data quality and v0.5 indicator validation

- [x] Identify available local database/artifacts without reading credentials or mutating production databases.
- [x] Report per-instrument Mock history coverage, row counts, date bounds, duplicates, non-monotonic dates, missing/invalid OHLCV, future dates, non-positive prices, volume/amount anomalies, and provenance.
- [x] State the real-five-ETF blocker and never substitute Mock proof: Tushare unconfigured and Composite daily failed in the single capability run.
- [x] Run current deterministic indicator tests plus active v0.4 and direct dormant-v0.5 calculations for the named metric families; RPS app comparison remains unavailable/unverified.
- [x] Cross-check public result-frame outputs against separate local NumPy/Pandas formulas and document tolerance/initialization differences; no external trusted indicator library was installed.
- [x] Keep `volume_profile_approx` explicitly estimated, never real shareholder-chip data.
- [x] Luna implementer self-review complete (`PASS_WITH_LIMITATIONS`).
- [x] Luna specification review passes after adding direct RSRS and observed boolean counts.
- [x] Luna quality/evidence review passes after converting helper comparisons to public-frame end-to-end checks and eliminating vacuous success paths.

### Task 4 evidence

- Sanitized artifact: `E:\Claude_allow\Download\etf-v050-baseline-20260828-010724-5733a2a2a57a4769bb639ada797e2cfb\evidence\task4-mock-history-indicators-sanitized.json`; SHA-256 `F9916837181E9792A3EA95336E6B3E96E57B1A3AF7367BD525052032E434359D`.
- Mock bootstrap: 10 instruments, 9 enabled, 2709 bars; each enabled instrument has 301 rows from 2025-07-04 through 2026-08-28. Recorded duplicate/date/future/OHLC/volume/amount anomaly counts are zero; source is Mock only.
- Active effective-v0.4 indicator chain created 9/9 snapshots. Direct dormant-v0.5 calculation succeeded for five Mock histories.
- Public result-frame outputs match separate local reference formulas for OBV, MFI14, CMF20, ADX14/+DI/-DI, and RSRS beta/R2/raw/z-score at declared `1e-9`/`1e-8` tolerances; these are local duplicate-formula checks, not an external library validation.
- Warm-up/default/computed counts are recorded as MFI 13/288, CMF 19/282, ADX-DMI 13/288, RSRS beta/R2/raw 17/284, z-score 46/255. Quality review notes these counts are recorded but not runtime-asserted in the harness (Minor).
- RPS closed-form reference self-check passes but no current public app comparison exists; RPS remains `UNVERIFIED`. `volume_profile_approx` is estimated and the named profit metric is unavailable.
- Focused indicator/strategy-engine tests: 3 passed. All Task 4 conclusions remain Mock-only; real provider validation is blocked and forecast status remains `not_calibrated`.

## Task 5: Rotation, ablation, and forecast validation

- [x] Determine safe local task invocation and database/report isolation before execution.
- [x] Run `backtest_rotation` and `validate_forecasts`; record current `backtest_ablation` as `UnknownTaskError` and directly exercise dormant v0.5 ablation only as module evidence.
- [x] Capture Mock provenance, input window/universe, output artifact paths/hashes, and failures.
- [x] For rotation, verify `decision_at=close_t`, `execution_at=open_t_plus_1`, feature dates, lot sizes, and Mock provenance; fees/slippage/hysteresis/caps/market gate are source+config evidence rather than exhaustive per-trade assertions.
- [x] For ablation, compare all four actually implemented variants under the same observed non-factor controls/execution engine; answer whether `full_v050` beats `momentum_baseline`. Do not claim cryptographically identical inputs because dataset/effective-weight hashes are absent.
- [x] For forecast validation, report 1/5/20-day `directional_accuracy`, Brier, MAE, 80% interval coverage, calibration bins, samples, and `not_calibrated` state.
- [x] Distinguish Mock engine execution proof from real performance evidence.
- [x] Luna implementer self-review complete.
- [x] Luna specification review passes after exact metric naming, turnover deltas, and dormant-service semantics were corrected.
- [x] Luna quality/evidence review passes for bounded `MOCK_ONLY_ENGINE_EXECUTION_PROOF`; report wording fixes are recorded below.

### Task 5 evidence

- Sanitized summary: `E:\Claude_allow\Download\etf-v050-baseline-20260828-010724-5733a2a2a57a4769bb639ada797e2cfb\evidence\task5-mock-backtest-forecast-sanitized.json`; SHA-256 `1335de0015bffa07bc21baf3c319a71f1b368b9f7acae94af7c092cf661fcb3b`.
- Current effective-v0.4 rotation (Mock): 36 decisions, 134 trades, total return -9.6336%, benchmark -22.1640%, excess +12.5304 percentage points, maximum drawdown -10.7584%, Sharpe -2.3948, turnover 11.6597x. All 36 decisions pass close-t feature timing and t+1-open execution; all trades use 100-share lots.
- Current `backtest_ablation` task is unavailable and returns `UnknownTaskError`.
- Direct dormant `RotationBacktestV05Service` uses `strategy_config_version=signal-v0.4.0` and is not sealed/runtime-wired v0.5. Four variants run; `full_v050` loses `momentum_baseline` on total return, Sharpe, maximum drawdown, and turnover. Turnover deltas versus baseline are 0.0000, +1.1707, +1.2976, and +0.3871 for baseline/volume-flow/breakout-structure/full respectively. Requested A-H variants are not implemented.
- Common-input wording is limited to the same observed non-factor controls and execution engine with factor weights varied; no dataset hash or serialized effective-weight map proves cryptographic identity.
- Forecast Mock diagnostics: horizons 1/5/20 have samples 225/216/189; directional accuracy 48.89%/42.59%/48.68%; 80% interval coverage 78.67%/76.85%/69.31%; Brier 0.2530/0.2652/0.2837. Per-instrument samples are sparse (25/24/21); no simple forecast baseline or significance analysis exists. Model `similarity-v0.2.0` remains `not_calibrated` for all 27 snapshots.
- Backtest realism remains bounded: no full runtime assertions for caps/fees/slippage/hysteresis and no suspension/no-volume/limit-up-down/exchange-specific lot/LOF premium/cash-yield/independent-engine reconciliation.

## Task 6: Validation report

**Create:** `deployment_reports/local-v050-validation.md`

- [x] Include Git commit/branch/dirty-boundary, Python version, OS, tests, Tushare matrix, AKShare matrix, universe counts, history coverage, anomalies, indicator validation, rotation backtest, ablation, forecast validation, incomplete items, and 3-5 prioritized next steps.
- [x] Answer the ten first-stage questions from the handoff using only current evidence.
- [x] Redact secrets and omit public IPs/account identifiers/signed URLs.
- [x] Label every conclusion as confirmed, partial, unavailable, Mock-only, or unverified where appropriate.
- [x] Do not claim provider stability from one smoke run or local success as ECS/production proof.
- [x] Luna report author self-review complete.
- [x] Luna specification review passes after metric availability, rotation/ablation completeness, forecast count, and absent-vs-null semantics were corrected.
- [x] Luna quality/evidence review passes after final wording hardening.

## Task 7: Final controller verification and review

- [x] Re-run `pytest -q`.
- [x] Re-run `python -m compileall -q backend/app`.
- [x] Re-run `node --check backend/app/static/app.js`.
- [x] Re-run Bash syntax checks if Bash is available.
- [x] Re-run secret scan and ensure the final report contains no sensitive values.
- [x] Verify exact changed-file attribution using an explicit file list, not broad ownership assumptions.
- [x] Dispatch final Luna/xhigh reviewer across the full task and resolve all Critical/Important findings.
- [x] Add a Review section below with commands, evidence, limitations, and final status.

## Review

### D3 release/docs/validation review (2026-08-29)

- Changed only the D3-owned semantic paths in this section: `backend/app/core/config.py`, `pyproject.toml`, `deploy/.env.production.example`, `deploy/Caddyfile.example`, `deploy/nginx.conf.example`, `README.md`, `QUICKSTART.md`, `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_MATRIX.md`, `STATUS.md`, `HANDOFF.md`, and this ledger. Other dirty snapshot paths remain pre-existing owner work; no stage/commit/reset/clean/push was performed.
- Release assertions: `Settings(_env_file=None).app_version == 0.6.0`; `pyproject.toml` package version is `0.6.0`; `APP_VERSION=0.6.0` is in the production example. `config/strategy.json` remains `signal-v0.4.0`; no strategy/indicator/forecast formula or version was changed. `OCR_MAX_IMAGE_BYTES` is accepted with legacy `OCR_MAX_BYTES` compatibility.
- `E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m pytest -rA`: **323 passed, 2 skipped, 14 warnings, exit 0**. Skips are host symlink privilege limitations; warnings are existing Starlette/httpx and Python 3.12 SQLite datetime deprecations.
- `python -m compileall -q backend/app`: exit 0. `node --check backend/app/static/app.js`: exit 0.
- `with_server.py --help` was run first from `C:\Users\Admin\.codex\skills\webapp-testing\scripts\with_server.py` (the worktree has no helper). Git Bash/WSL was unavailable: WSL relay reported `/bin/bash` missing and `C:\Program Files\Git\bin\bash.exe` was absent. Shell syntax is therefore a deployment gate.
- `docker` exists, but `docker compose config` was not run with a generated `.env`: Compose requires the server-local `.env` referenced by services, and no `.env` or secret was created/read. This is an explicit Compose gate; no image build or network/model download occurred.
- Mock bootstrap used a disposable SQLite/report root and `MARKET_PROVIDER=mock`, `AUTH_ENABLED=false`, lookback 180: succeeded; 10 instruments, 1,170 bars, 9 indicator snapshots, 9 degraded/mock quotes, six configured context cards with zero eligible proxy requests, and a generated report. Forecast failures due intentionally short history were retained as non-calibrated/unavailable.
- Mock HTTP on isolated `127.0.0.1:38123` through `with_server.py`: `/api/health` returned version `0.6.0`, `/api/bootstrap` returned six context cards and nine instruments; helper stopped the server cleanly.
- Headless Chromium smoke used the locally existing Playwright-capable Python 3.12 interpreter with a generated nonsecret local token, isolated port/temp DB/reports/OCR environment, and Mock provider. After attempting `networkidle` (the app keeps an authenticated SSE stream open), assertions passed: six context cards, code-first identity, exact distinct `FORECAST · 非实际结果` labels, PORTFOLIO INPUT dialog and image accept types, mobile tabs, console errors 0. No upload or provider call was made; server/browser cleaned up.
- Secret scan: `check_no_secrets.py .` returned two fixture-only matches at `backend/tests/test_api.py:164` (`market-context-test-token`) and `backend/tests/test_news_analysis.py:137` (`test-key-not-a-real-secret`); both are pre-existing test literals, not credentials. No `.env`, token, cookie, password, account number, or signed URL was read or emitted.
- Real PostgreSQL, Tushare/AKShare/news/OpenAI endpoint qualification, ECS/HTTPS, real Paddle Python 3.12 wheel/model and `paddle-local-v1` manifest, six proxy qualification, forecast calibration, and production backup/restore remain gates. Final D3 status: **DONE_WITH_CONCERNS** (implementation and local/Mock evidence complete; deployment and real-provider evidence intentionally pending).
- Controller follow-up (2026-08-29): the two environment gates above were closed from the main checkout — `bash -n` passed on `deploy/aliyun/bootstrap_host.sh`, `deploy/aliyun/deploy.sh`, `deploy/aliyun/update.sh`, `scripts/backup_postgres.sh`, `scripts/restore_postgres.sh`, `scripts/smoke_http.sh`; `docker compose config` passed with a throwaway placeholder `POSTGRES_PASSWORD` (temp `.env` deleted, no secret created). Full pytest re-run independently: 323 passed / 2 skipped, exit 0; Alembic full-chain upgrade → downgrade base → upgrade passed (head `b3c4d5e6f7a8`). QUICKSTART backup/migration order corrected to backup-first per spec review.

### Fresh controller verification

- Verification copy: `E:\Claude_allow\Download\etf-v050-baseline-20260828-010724-5733a2a2a57a4769bb639ada797e2cfb\final-controller-20260828-041026-2f32cf89664e4734baef7b0861dbdb47\source-copy-final`.
- Python 3.12 isolated editable install: exit 0.
- `pytest -q`: exit 0, 10 passed; one non-failing Starlette/httpx deprecation warning.
- `python -m compileall -q backend/app`: exit 0.
- `node --check backend/app/static/app.js`: exit 0.
- Explicit Git Bash syntax checks for `bootstrap_host.sh`, `deploy.sh`, and `update.sh`: all exit 0.
- Scoped working-tree secret scanner: exit 0, `no obvious committed secrets found`; its exclusions remain documented and it is not a Git-history/env-file proof.
- Final report: 219 lines, 17 required sections, forbidden secret/URL/IP assignment pattern count 0, SHA-256 `DBA42A6AC1FB25AC92B1CACE921174A177F811C191C1AFFB5870B1D589C5AEFC`.
- Approved evidence hashes rechecked: Provider `C556AF27AB344EB899540E05E8D56E457CA061D05947E01A8592E34ED1FCF3EE`; Task 4 `F9916837181E9792A3EA95336E6B3E96E57B1A3AF7367BD525052032E434359D`; Task 5 `1335DE0015BFFA07BC21BAF3C319A71F1B368B9F7ACAE94AF7C092CF661FCB3B`.
- Original repository status-path list before/after final verification: delta 0.

### Exact current-turn file attribution

- Modified: `backend/tests/conftest.py` — Windows SQLite engine disposal and test report isolation only.
- Created: `tasks/todo.md` — this execution ledger.
- Created (Git-ignored by project rule): `deployment_reports/local-v050-validation.md` — final validation report.
- The 16 other substantive dirty paths listed in Task 1 pre-existed this turn and remain owner work; no author or intent is inferred.

### Final review and status

- Fresh final Luna/xhigh global review found no Critical or Important issue. One non-blocking defensive teardown Minor remains: if `get_engine().dispose()` itself raises, later cleanup may be skipped.
- Final result: `PARTIAL / NOT READY FOR REAL STRATEGY SEALING OR PRODUCTION PROVIDER CLAIMS`.
- Completed scope: repository audit, fresh local baseline, safe single-run Provider capability observation, demo-universe audit, Mock history/indicator validation, Mock rotation/direct dormant ablation/forecast validation, and reviewed report.
- Blocked/unverified scope: Tushare permissions, stable Composite history, exchange-time realtime freshness, five-real-ETF quality cross-check, real-data indicator validation, RPS app comparison, calibrated forecasts, A-H ablation, complete transaction constraints, and independent second-engine reconciliation.

---

# v0.6.0 Multi-Model, Market Context, and Portfolio OCR Active Plan

**Isolation:** `E:\Claude_allow\Download\ETF-Fund-Analysis-worktrees\multi-model-market-context-ocr` on `codex/multi-model-market-context-ocr`.

**Approved design:** `docs/superpowers/specs/2026-08-28-multi-model-market-context-ocr-design.md`.

**Implementation plans:**
- `docs/superpowers/plans/2026-08-28-analysis-gateway.md`
- `docs/superpowers/plans/2026-08-28-market-context.md`
- `docs/superpowers/plans/2026-08-28-portfolio-ocr.md`
- `docs/superpowers/plans/2026-08-28-dashboard-integration.md`

## Baseline

- [x] Current owner working snapshot copied without secrets into the isolated worktree.
- [x] Baseline `pytest -q`: 10 passed; one existing Starlette/httpx deprecation warning.
- [x] Baseline compileall and Node syntax: exit 0.
- [x] No implementation task has started before plan completion.

## Subagent-driven task gates

- [x] A1 contracts/config: implementer self-review, spec review, quality review.
- [x] A2 direct adapters/gateway: implementer self-review, spec review, quality review.
- [x] A3a persistence/review records: implementer self-review, spec review, quality review. PostgreSQL trigger smoke remains a deployment environment gate.
- [x] A3b1 news/signal/Dashboard integration: implementer self-review, spec review, quality review.
- [x] A3b2 review API/task integration: implementer self-review, spec review, quality review.
- [x] B1 market registry/contracts/schema: implementer self-review, spec review, quality review.
- [x] B2a market registry sync/provider observations: implementer self-review, spec review, quality review.
- [x] B2b market task/scheduler/payload: implementer self-review, spec review, quality review.
- [x] C1 OCR contracts/image validation/schema: implementer self-review, spec review, quality review.
- [x] C2 OCR service/private API: implementer self-review, spec review, quality review.
- [x] D1 market/identity/forecast UI: implementer self-review, spec review, quality review.
- [x] D2 Portfolio OCR review UI: implementer self-review, spec review, quality review.
- [x] D3 release/docs/end-to-end: implementer self-review, spec review, quality review.
- [x] Final global review has no open Critical or Important issue. (Controller-dispatched independent reviewer, two rounds; see "Final global review evidence" below. Not the Luna runtime — same gate, different reviewer.)
- [x] Main controller verification and exact file attribution complete. (Controller independently re-ran full pytest, Alembic full-chain roundtrip, `bash -n` on 6 scripts, `docker compose config` with placeholder env, compileall, `node --check`; D3 file attribution verified against actual diffs by the spec reviewer.)

### Final global review evidence (2026-08-29)

- Round 1 (controller-dispatched independent reviewer over the full uncommitted tree): VERDICT PASS, no Critical. Findings: 1 Important — `ReportService.generate()` never passed `market_context` to `report.html.j2`, so generated reports always rendered the six placeholder cards; Minors — scheduler `refresh_market_context` did not catch `TaskBusyError` (advisory-lock starvation), OCR `_resolve_line` ran `_instrument_maps` per row, `task-snapshots/` not gitignored, `!deploy/.env.production.example` negation dropped, `canonical_json` path-lookalike pattern overly broad, analysis orphan-flag validation absent.
- Fix round (fix agent): report render wired via `market_context=payload.get("market_context") or []` with new discriminating test `test_report_service_generation_wires_bootstrap_market_context` (verified to fail without the fix); scheduler catches `(TaskExecutionError, TaskBusyError)`; `_instrument_maps` hoisted out of the candidate-row loop (`_resolve_line(by_symbol, by_name, ...)`); `.gitignore` restored negation + added `task-snapshots/`. Gates after fixes: full pytest 324 passed / 2 skipped exit 0, compileall clean, `node --check` clean.
- Round 2 (same reviewer): all five fixes verified OK, no regressions, VERDICT PASS. Test isolation sound (rollback in `finally`, artifact under ignored path).
- Deferred non-blocking follow-ups (recorded deliberately, not lost): (1) `backend/app/utils/canonical_json.py` path-lookalike pattern rejects ordinary `A/B` strings in free-text fields — consistent with DB checks, blunt but safe; narrow in a future release if operator notes need slashes. (2) `backend/app/core/config.py` analysis orphan flags (e.g. `ANALYSIS_CODEX_ENABLED=true` without `ANALYSIS_ENABLED`) are silently ignored rather than rejected; add fail-closed validation in a future release.

### D3 release/docs/validation execution checklist

- [x] Set authoritative application/package release to `0.6.0`; retain strategy/indicator/forecast versions.
- [x] Document one-primary analysis configuration, market-context defaults, OCR operator/deployment gates, and no-actionable-data boundaries.
- [x] Align production env example, reverse-proxy upload limits, migration/rollback order, and Docker Paddle behavior.
- [x] Run isolated SQLite migration, Python/JS checks, shell syntax, Compose/secret checks, Mock HTTP, and browser smoke where dependencies permit.
- [x] Record exact commands/results/limitations and explicit D3 file attribution in the review below.

### B2a review evidence

- [x] Disabled/unverified registry rows remain visible but never expose historical snapshots as current observations.
- [x] Eligible rows without a successful snapshot are explicitly unavailable; registry verification remains separate provenance.
- [x] Registry order reconciliation is safe under immediate uniqueness constraints, including historical rows and configured order `10000`.
- [x] Observations bind to `source_symbol`; A-to-B symbol changes preserve A history without relabeling it as B.
- [x] Mock observations remain explicitly unverified/degraded/non-actionable; non-Mock unverified observations are rejected.
- [x] Composite capability-unavailable traces remain `unsupported`; provider failures are sanitized and cannot leak raw exception text.
- [x] SQLite/PostgreSQL conflict-safe inserts preserve snapshot idempotency and the outer transaction.
- [x] ORM and Alembic constraints/unique keys are aligned; clean SQLite upgrade/downgrade/upgrade passed.
- [x] Controller verification: `test_market_context.py` 49 passed; full suite 236 passed; compileall, Node syntax, scoped Ruff, and diff check passed.
- [x] Fresh Luna/high specification and quality reviews found no open Critical or Important issue.

### B2b review evidence

- [x] `refresh_market_context` task, coherent run/event identity, private endpoint, bootstrap payload, and partial-pipeline behavior are implemented.
- [x] Scheduler isolates market-context failures, continues independent tasks, and throttles by last terminal attempt without relabeling failure as success.
- [x] Current-run counts come from an immutable service-owned outcome; no Provider monkeypatching or historical-count leakage remains.
- [x] Forecast provenance uses authoritative stored fields only; unsupported `data_cutoff` remains null and diagnostics cannot spoof it.
- [x] Existing v0.5 signal/backtest wiring, `backtest_ablation`, and indicator assertions were restored and regression-tested.
- [x] Controller verification: focused B2b tests 68 passed; full suite 252 passed; compileall, Node syntax, scoped Ruff, and diff check passed.
- [x] Fresh Luna/high specification and quality reviews found no open Critical or Important issue.

### C1 review evidence

- [x] PNG/JPEG/WebP validation enforces MIME/magic/decode/bytes/dimensions/pixels/trailing data and does not mutate Pillow globals.
- [x] Paddle remains optional, local-only, manifest/hash bound, executed in a killable spawned process with bounded output and hard timeout cleanup.
- [x] Image metadata is revalidated at the adapter boundary; forged `ValidatedImage` instances cannot bypass decoding and hash checks.
- [x] Import-session/candidate persistence excludes image bytes, raw OCR, user filenames, and sensitive fields; safe text is validated on bind/read and by portable structural constraints.
- [x] SQLite-specific NUL triggers cover ORM `create_all` and Alembic; PostgreSQL text NUL rejection and dialect-specific backslash DDL are documented/compiled.
- [x] Opaque tokens, consent/terminal/selection state coherence, indexes, defaults, TypeDecorators, ORM and migration parity are covered.
- [x] Controller verification: C1 37 passed/2 platform skips; full suite 289 passed/2 skips; SQLite Alembic roundtrip, PostgreSQL DDL compile, compileall, Node, Ruff, and diff check passed.
- [x] Real PostgreSQL constraints and real Paddle package/model qualification remain deployment gates; no network/model download occurred.
- [x] Fresh Luna/high specification and quality reviews found no open Critical or Important issue.

### C2 review evidence

- [x] Private multipart upload, review/edit/reject, confirm/cancel, expiry cleanup, and consent-only cloud status endpoints are implemented with no image retrieval route.
- [x] Durable `processing` precedes file creation; terminal state commits precede deletion; cleanup retries until `storage_key` is cleared.
- [x] Mutations use service-owned sessions and fail closed on caller transactions or in-memory SQLite; CAS states protect edit/confirm/cancel/expiry races.
- [x] Unknown exchanges and non-exact names never silently resolve; bbox OCR cells are assembled by row and x-order without numeric pollution.
- [x] Holding writes occur only after explicit confirmation through `HoldingService.upsert`, in deterministic code order, with idempotent confirmation.
- [x] Storage uses contained opaque token directories and fail-closed 0700/0600 permission checks; no raw screenshot/OCR/path is exposed.
- [x] Controller verification: full suite 318 passed/2 platform skips; Alembic roundtrip/current head, compileall, Node, Ruff, diff, and targeted secret scan passed.
- [x] Fresh Luna/high specification and quality reviews found no open Critical or Important issue.

### D1 review evidence

- [x] Six market-context cards remain visible through deterministic fallback merge; no proxy code or observation is fabricated.
- [x] Code-first identity and today-change-first observed hierarchy are implemented across Dashboard and report.
- [x] Forecasts use a distinct `FORECAST · 非实际结果` surface with null-safe provenance and explicit calibration state.
- [x] Quote `is_mock`, freshness, source and timestamps are displayed per observed item; Mock/degraded cannot appear as verified normal state.
- [x] Dynamic UI/report text is escaped; report autoescape and minimal-payload rendering are covered.
- [x] Responsive report/table behavior, explicit Asia/Shanghai time handling, bars cancellation/debounce, modal/keyboard/focus accessibility and contrast are implemented.
- [x] Controller verification: focused D1 11 passed; full suite 321 passed/2 skips; Node, compileall, Ruff and diff check passed.
- [x] Fresh Luna/high specification and quality reviews found no open Critical or Important issue.

### D2 review evidence

- [x] Portfolio screenshot upload uses FormData without multipart `Content-Type` corruption and keeps Authorization header-only.
- [x] Candidate review exposes only allowed fields, code-first alternatives, confidence/status warnings, explicit edit/reject/confirm/cancel and no raw/path/hash data.
- [x] Import generation, AbortControllers, serialized PATCH queue, pending-save flush and durable cancel prevent stale async responses and lost edits.
- [x] Client numeric bounds/precision mirror backend validation; 0/decimals are preserved and unresolved/duplicate/error states block confirmation.
- [x] Lock/auth generation clears sensitive in-memory review state; no import state is persisted to localStorage; cloud review remains disabled with no egress.
- [x] Mobile tabs remain accessible; modal, live status, focus, reduced-motion and responsive candidate layout are implemented.
- [x] Controller verification: test_api 10 passed; full suite passed with 2 platform skips; Node, compileall, Ruff and diff check passed.
- [x] Fresh Luna/high specification and quality reviews found no open Critical or Important issue.

## Authorization and provenance

- [x] No automatic commit, push, PR, provider credential read, production DB write, broker action, or threshold tuning is authorized.
- [x] Pre-existing snapshot differences remain owner work; each task records only its explicit file list and semantic diff.
- [x] Models/agents remain text-analysis candidates with no tools or numeric decision authority.

---

# FTShare + Safe Demo Active Plan

- [x] Current staged owner snapshot copied into isolated worktree without `.env`, databases, `.zcode`, or reference screenshots.
- [x] A. Configure and verify FTShare MCP plus pinned user-level Skill; no business DB access.
- [x] B. Implement disabled-by-default FTShare Provider, qualification script, provider ordering, audit and contract tests.
- [x] C. Implement isolated DemoService/API; fix 30-calendar-day root cause and status semantics.
- [x] D. Implement system-page demo/free/complete UX, provider probe matrix and source badges.
- [x] E. Update docs/config examples, run full regression, live read-only FTShare qualification, browser smoke and final review; schema parity is now green.
- [x] Every implementation task has a fresh delegated implementer (Luna/Terra high as requested), specification review and quality review with no open feature Critical/Important issue.
- [x] No real credential read, production DB write, broker action, or Mock-to-production fallback; commit/push only after Jovi's explicit authorization.

## Task B implementation checklist (FTShare provider)

- [x] RED: add isolated MockTransport contract tests for settings, mappings, validation, errors, and factory order.
- [x] GREEN: implement disabled-by-default FTShare settings, fixed-endpoint provider, factory ordering, and qualification probe.
- [x] Verify focused tests, full pytest, compileall, node check, and diff check; record evidence below.

### Task B review

- Focused FTShare contract tests: 63 passed; market-context focused suite and full pytest also passed (2 existing platform skips).
- Follow-up hardening covers exact row symbol/code matching, exact provenance allowlist, strict Beijing ISO timestamp/order/date parsing, explicit unadjusted bars, streaming response byte bounds, strict pagination parsing, production base URL policy, no Mock in new composite chains, sanitized factory/transport errors, integer share volumes, computed bounded pct units, unknown qualification pagination, and idempotent scheduler/provider lifecycle closure.
- `python -m compileall -q backend/app scripts/qualify_ftshare.py`: passed; `node --check backend/app/static/app.js`: passed.
- `git diff --check`: no FTShare/task-B whitespace errors; an existing owner change in `backend/app/static/app.css` reports a blank EOF line.
- Live FTShare qualification was run read-only after implementation and exits nonzero while daily/spot evidence is unavailable; the checked report remains unqualified and FTShare disabled.

### Task C review

- [x] DemoService uses a process-local SQLite `StaticPool` and a dedicated MockProvider; it never shares the production SQLAlchemy engine.
- [x] Demo load runs the existing sync/420+ bar/indicator/forecast/signal pipeline with `report=False`; demo reads include explicit `demo`, `is_mock`, `research_only`, and `actionable=false` provenance.
- [x] Private `/api/demo/load`, `/api/demo/bootstrap`, and `/api/demo/reset` endpoints accept no provider URL, tool, or shell controls; reset/disposal is lock-protected and idempotent.
- [x] Empty, insufficient, provider-unavailable, and indicator-failure states have mutually exclusive labels; API/UI refresh-bars default is 120 calendar days.
- [x] Focused demo regression: 8 passed; compileall and Node syntax checks passed. Full suite and independent spec/quality review remain parent-task gates.
- [x] Review hardening: demo settings forcibly disable analysis, LLM, Tushare, FTShare, RSS/news egress, and OCR cloud/local modes; injected HTTP transport confirms zero external calls.
- [x] Review hardening: pipeline stages classify provider fetch failures separately from core indicator failures; app lifespan disposes the demo runtime and injected provider exactly once.
- [x] Review hardening: recursive demo provenance flags cover nested dashboard/grade/board/audit data; readiness counts distinct latest indicator snapshots per instrument.

### Task D review

- [x] System page distinguishes isolated DEMO, free AKShare-primary, and complete Tushare-primary usage; FTShare state is visible without returning endpoint URLs or credentials.
- [x] Market probe returns bounded per-provider rows (`provider`, `operation`, `ok`, `status`, `records`, `latency`, `failure_class`, `qualification`) and persists only sanitized latest results.
- [x] Demo load/reset/exit controls switch the dashboard to `/api/demo/*`, disable formal task controls, show a persistent DEMO/Mock banner, and restore formal `/api/bootstrap` on exit.
- [x] Source badge is derived from observed quote/provider provenance; demo results remain research-only and non-actionable.
- [x] Focused market settings tests, Node syntax, and compile checks passed; full-suite verification remains the parent task gate.
- [x] Review hardening: FTShare factory inclusion requires both explicit enablement and `qualified`; unqualified/rejected sources are skipped.
- [x] Review hardening: DEMO blocks all formal mutation handlers and controls, including holdings, OCR, boards, reports, settings, coefficients, and tasks.
- [x] Review hardening: source badge reports `不可用` when no current quote or latest successful provenance exists; formal Mock is not relabeled as isolated DEMO.
- [x] Review hardening: exiting DEMO reloads formal settings before formal bootstrap and never re-enters DEMO on settings-read failure.
- [x] Quality hardening: mode transitions use generation tokens, abort in-flight reads/SSE/OCR work, and centrally track in-flight formal mutations with no counter leak on failure/abort.
- [x] Quality hardening: Node VM behavior tests cover pending-write refusal, successful DEMO retention, failed-enter SSE/timer restoration, and single formal SSE reconnect on successful exit.

### Task E finalization evidence

- [x] Documentation/config examples updated for `FTSHARE_ENABLED=false`, `FTSHARE_QUALIFICATION=unverified`, fixed endpoint, timeout, page/row/date/response bounds, qualification workflow, independent data-service terms, safe DEMO workflow, 120-day refresh default, status semantics, pinned Agent Skill commit, and the separate Tushare plaintext-token security debt.
- [x] `scripts/qualify_ftshare.py` live read-only probe completed on 2026-08-30 for `510300.SH`; ETF list, daily bars, and spot operations all returned sanitized rejection (`CapabilityUnavailable`), so the qualification report remains `unqualified` and FTShare remains disabled. Evidence: `docs/ftshare-qualification-2026-08-30.json`.
- [x] Parent-controller evidence: `pytest -q` exited 0 (447 collected test nodes; 2 existing platform skips); `python -m compileall -q backend/app scripts/qualify_ftshare.py` passed; `node --check backend/app/static/app.js` passed; diff secret scan found no configured-secret patterns (environment files excluded). This child task does not relabel that controller run as its own full-suite result.
- [x] Isolated headless browser smoke on port 18988 with a worktree-pinned app and temporary SQLite: DEMO banner/load/status/source badge, formal task and portfolio locks, FTShare disabled status, DEMO exit, and zero external requests passed. Exact smoke processes and temporary SQLite artifacts were cleaned up; ports 18981-18988 verified closed.
- [x] Audited ORM/migration reconciliation: clean disposable SQLite passes `upgrade head`, `current`, full `downgrade base`/re-upgrade, and `alembic check` at `d5e6f7a8b9c0`. The metadata-only repair preserves historical review/analysis hash-check names, restores the separately named opaque import-session constraint, keeps nullable legacy calibration JSON, and removes only a redundant candidate-id index declaration covered by the existing UNIQUE constraint. Regression: `backend/tests/test_migration_schema_parity.py`; real PostgreSQL qualification remains a deployment gate.
## Unified decision-board backend plan (approved)

- [x] Inspect current models, private routes, task lifecycle, scheduler, and backend fixtures.
- [x] RED: add isolated decision-board service/API/scheduler tests for response semantics, storage isolation, slot eligibility/deduplication, and refresh concurrency. (Initial run was environment-blocked before functional execution; dependencies were then isolated under the permitted download directory.)
- [x] GREEN: add snapshot/provisional persistence migration and read-only snapshot service with explicit provenance/freshness state.
- [x] GREEN: wire the three private API endpoints, async refresh task, and Asia/Shanghai slot scheduler without changing strategy-grade logic.
- [x] Verify focused backend tests, compileall, migration chain/schema parity where practical; record exact outcome and blockers below.

### Unified decision-board backend review

- [x] `backend/tests/test_decision_board.py` (13) + signal-grade/workbench regression (7): 20 passed with isolated Python 3.12 dependencies.
- [x] Contract repair: snapshot rows now contain normalized wide-table `volume`/`ma`/`macd`/`kdj`/`td`/`rsi`/`chan`/`sector` objects; horizon selection rebuilds groups; details are snapshot-captured history, 10 scenario candles, support/resistance, Chan approximation and sort basis.
- [x] Contract repair: complete provisional OHLCV produces a temporary research-only derived view even with an unverified timestamp; it cannot be actionable and never writes `DailyBar`.
- [x] Contract repair: only decision slots fetch board quote input then capture provisional then materialize the board; queued API requests are consumed without an extra provider fetch; no decision-board news/AI side effect.
- [x] Corrected focused suite: `test_decision_board.py` + `test_signal_grade.py` + `test_market_context.py`: 80 passed. `node --test backend/app/static/decision_board.test.js` exited 0.
- [x] Spec review repair: `/workbench/1430` now 307 redirects to `/`; the legacy API remains compatibility-only.
- [x] Spec review repair: `previous_day_delta` is `today - previous confirmed DailyBar return` in decimal-ratio units; list/detail accept exact `snapshot_id`, unknown snapshots return 404.
- [x] Spec review repair: next slot uses `TradingCalendarService`, skips non-trading dates, and snapshots retain all entries for only the latest 20 trading dates.
- [x] Final sorting repair: all sortable technical columns expose numeric `sort_keys` with documented health priority; forecast key binds selected horizon expected return with confidence as a tie-break only and missing values last.
- [x] Sorting tie repair: volume ratio/direction, MA up-arrow count, and parsed TD9 setup count are packed into primitive numeric ties; actual persisted snapshot + API horizon tests verify `forecast` keys rematerialize for 1 versus 5 days.
- [x] Quality critical loop closed: the isolated Python 3.12 full suite completed with exit 0; the earlier shared SQLite lock was not reproduced.
- [x] Disposable SQLite Alembic `upgrade head`, `current` (`e6f7a8b9c0d1`), and `check`: passed; no new upgrade operations.
- [x] `py -3.14 -m compileall -q backend/app backend/tests`, scoped Ruff `I,F`, and scoped `git diff --check`: passed (Git only reported existing CRLF conversion notices).
- [x] Migration parity verified in the isolated Docker PostgreSQL service at head `f7a8b9c0d1e2`; `alembic check` reported no new operations.
- [x] Final frontend/API integration verified after the unified UI changes; the prior `marketContextSection` mismatch is no longer present in the active contract.

### Unified decision-board final release review (2026-09-01)

- Full pytest: exit 0; 2 existing platform skips and deprecation warnings only.
- `python -m compileall -q backend/app`, `node --check backend/app/static/app.js`, `node --test backend/app/static/decision_board.test.js` (11/11), and `git diff --check`: pass.
- Isolated Docker API/DB healthy; Alembic current/head `f7a8b9c0d1e2`; `alembic check`: no pending operations.
- Browser visual smoke: 37 rendered rows across six groups at 1440/1024/390 widths; grouped/global table, detail, forecast and responsive screenshots captured under `E:\Claude_allow\Download`.
- Final independent review: APPROVED. Mock data remains explicitly research-only/non-actionable; no credentials, production DB, or broker access was used.

## Free-tier provider fallback correction (2026-09-01)

- [x] RED: regression showed `public_composite` omitted a configured Tushare candidate and persisted UI tokens still bound tasks to direct AKShare.
- [x] GREEN: free/public execution now orders AKShare → configured Tushare → qualified FTShare; complete execution remains Tushare → AKShare → qualified FTShare.
- [x] Runtime probe and TaskService tests cover stored-token binding; no Mock fallback was introduced.
- [x] Focused Provider/settings suite and full pytest passed; Ruff, compileall, Node syntax and diff checks passed.
- [x] Independent Terra review: APPROVED after the persisted-token binding repair.

## Password-account browser authentication (2026-09-01)

- [x] RED: account login/session/CSRF/legacy/static UI regression tests (initial import failed as expected before implementation).
- [x] GREEN: Argon2id account auth, signed cookie session, CSRF and throttling.
- [x] GREEN: remove browser token persistence and document deployment setup.
- [x] Review: focused Python auth/API/holding tests, full pytest, Node decision-board tests, compileall, JS syntax, Ruff and diff checks pass; 2 existing platform skips only. Final specification and quality reviews approved the account/session/CSRF/legacy boundaries.

## Multi-user account and portfolio isolation (2026-09-01)

- [x] Review-fix plan: add RED regressions for private SSE, legacy ownership/backfill, self-lockout/session invalidation, production DB auth configuration, owner-specific overlays, and legacy NULL-owner uniqueness; implement the smallest service/router/model/Alembic fixes; run focused and full gates; record evidence and remaining production limitations.
- [x] See `tasks/plans/2026-09-01-multi-user-auth.md`; the single-account prototype is not deployed to shared users.
- [x] Task 1: add singleton bootstrap guard, `AuthUser`/`AuthSession`,
  database-backed Argon2id/session primitives, a hidden-prompt first-admin CLI command, and migration
  `0a9b1c2d3e4f` from `f7a8b9c0d1e2`; no holdings ownership change.
- [x] Task 1 focused evidence: 45 tests passed, with one explicit skip for an
  absent PostgreSQL test URL, across new auth models/service, legacy
  single-account compatibility, and Alembic SQLite round-trip parity.
- [x] Task 1 P1 regression: two competing SQLite sessions create exactly one
  admin; the other is rejected after database guard serialization.
- [x] Task 1 quality regression: malformed/plaintext and pseudo Argon2id PHC
  hashes, including invalid base64 and empty salt/digest records, are rejected
  at ORM/service boundaries; optional PostgreSQL Alembic concurrency test is
  fail-closed skipped without an explicit test database.
- [x] Task 1 password-cost regression: ORM hash validation is structural only;
  a real Argon2 verify occurs only in credential verification, avoiding a
  second computation at account construction or bootstrap.
- [x] Task 1 PostgreSQL test safety: destructive auth-row cleanup requires all
  of `TEST_POSTGRES_URL`, `APP_ENV=test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=1`,
  and an unmistakable test/scratch/ci database suffix; otherwise no connection
  or delete is attempted.
- [x] Task 1 final regression/compile/diff check completed; current-user route
  conversion and user-owned portfolio tables are covered by the later Task 2 evidence below.

## Multi-user account and portfolio isolation — Task 2 (2026-09-01)

- [x] RED: add focused DB-session API and owner-isolation tests for login/revoke,
  holdings, OCR imports, legacy Bearer boundaries, and migration/backfill parity.
- [x] GREEN: replace the stateless browser session dependency with DB-backed
  current-user resolution and per-session CSRF; retain legacy Bearer for shared reads only.
- [x] GREEN: add nullable ownership FKs, per-user holding uniqueness, and a
  deterministic admin-only legacy-holding backfill command.
- [x] GREEN: propagate a resolved user through holdings, imports, bootstrap,
  signal center, and user-generated reports without changing strategy logic.
- [x] Review: run the focused suite, migration round trip/check, compileall,
  Node syntax check, and inspect the scoped diff before handoff. No commit/push/deploy.

### Multi-user final review evidence (2026-09-02)

- [x] Admin/member lifecycle, DB sessions, CSRF, revocation, SSE revalidation,
  owner-scoped holdings/OCR/reports/14:30/optimizer, shared-signal purity,
  nullable ownership migration, dynamic legacy uniqueness, safe downgrade and
  explicit backfill all passed independent specification and quality reviews.
- [x] Project venv full `pytest -q` exited 0 with 3 platform skips; focused
  auth/ownership/API/migration/holding-import/optimizer/ETF1430 suites also
  exited 0. `compileall`, `node --check`, decision-board Node tests and
  `git diff --check` exited 0.
- [x] Production configuration is fail-closed and documentation/templates now
  describe database authentication and migration head `2c3d4e5f6a7b` consistently.
- [x] No credentials, `.env`, production database, broker, or deployment target
  was accessed. Real PostgreSQL migration/backup/restore, ECS deployment, and
  provider qualification remain explicit gates.
- [x] The repository helper secret scan was run; its simple pattern checker
  reported only synthetic test fixture strings in test files (including legacy
  token/password labels), not configured credentials. `.env` and production
  environment files were excluded by the checker and were not opened.

### Multi-user HTTP OCR test-isolation repair (2026-09-02)

- [x] Reproduce the shared SQLite residue after the authenticated OCR HTTP ownership regression.
- [x] Add teardown scoped to only that test's created users, sessions, imports, candidates, holdings, and transient files.
- [x] Verify `test_holding_import.py` and `test_multi_user_ownership.py`, then `pytest -q`, compileall, Node syntax, and scoped diff.

#### Review evidence

- [x] Specification and code-quality reviews approved the test-only cleanup. A first review required moving client creation inside the protected `try`; the re-review approved the corrected exception-safe teardown.
- [x] Project venv `E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe`: `backend/tests/test_holding_import.py` = 68 passed, 2 skipped, exit 0; `backend/tests/test_multi_user_ownership.py` = 17 passed, exit 0; full `pytest -q` = exit 0 with 3 platform skips and existing deprecation warnings only.
- [x] `python -m compileall -q backend/app`, `node --check backend/app/static/app.js`, and `git diff --check` each exited 0. The only diff-check output was existing CRLF conversion notices. No commit, push, deployment, credential read, or production database access.

### Multi-user production auth config consistency (2026-09-02)

- [x] RED: add a self-contained production-settings regression proving that obsolete `AUTH_EMAIL` is rejected by database-backed authentication, while development settings continue to accept the compatibility field. Initial focused run exited 1 on the new production `AUTH_EMAIL` case as expected.
- [x] GREEN: include `AUTH_EMAIL` in the production-only obsolete compatibility configuration rejection without changing database-backed identity behavior.
- [x] Review: `backend/tests/test_password_auth.py` = 31 passed (exit 0); `backend/tests/test_multi_user_auth.py` = 21 passed, 1 skipped (exit 0); `python -m compileall -q backend/app`, `node --check backend/app/static/app.js`, and `git diff --check` each exit 0. The diff check emitted only pre-existing CRLF conversion warnings. Production-template and deployment documentation now list `AUTH_EMAIL` with the retired compatibility variables. No commit, push, deployment, dotenv read, or production database access.

### P1 production authentication fail-closed fix (2026-09-02)

- [x] RED: exact production `AUTH_ENABLED=false` regression failed as intended (`DID NOT RAISE ValueError`; exit 1); paired development/test assertions passed.
- [x] GREEN: production now requires explicit `AUTH_ENABLED=true`, PostgreSQL, disabled schema auto-create, a secure cookie, and no obsolete credentials; development/test offline/demo behavior remains available.
- [x] Review: `test_password_auth.py` = 34 passed (exit 0); `test_multi_user_auth.py` = 21 passed, 1 skipped (exit 0); `test_holding_import.py` + `test_ftshare_provider.py` = 133 passed, 2 skipped (exit 0); project-venv sequential `pytest -q` = exit 0 with 3 platform skips and existing deprecation warnings. `python -m compileall -q backend/app`, `node --check backend/app/static/app.js`, and `git diff --check` each exit 0; diff check emitted only existing CRLF conversion notices. No commit, push, deployment, dotenv read, or production database access.

### Multi-user report-route review fixes (2026-09-02)

- [x] RED: prove `POST /api/reports` generates a system-scoped report with `AUTH_ENABLED=false`, while enabled authentication and legacy unsafe Bearer remain rejected.
- [x] RED: prove report download resolves a single, exact registered artifact only: wildcard-like names, same-owner near matches, sibling directories, and another user cannot leak a path or file.
- [x] GREEN: use the existing optional current-user resolution for offline report generation; retain the database-session boundary for authenticated mode.
- [x] GREEN: replace wildcard SQL lookup with exact artifact selection plus regular-file, basename, allowed-extension, and reports-directory containment checks.
- [x] Review: RED regression exited 1 for the intended offline-session and wildcard-near-match failures; post-fix report pair, auth (21 passed, 1 skipped), password (31 passed), ownership (19 passed), and API (12 passed) each exited 0 in isolated project-venv processes. `compileall`, Node syntax, and `git diff --check` each exited 0; diff emitted only existing CRLF notices. A single combined module process exited 1 because its shared SQLite fixture leaves ownership accounts before auth tests that require an empty account table; separate module runs avoid that pre-existing ordering constraint. No commit, push, deploy, credential read, or production DB access.

### Multi-user report operational-detail isolation follow-up (2026-09-02)

- [x] RED/GREEN: inject global task/provider diagnostic sentinels; member report payload has empty `tasks`/`provider_health` and its HTML has no sentinels, while system and active-admin payloads retain both sentinels. Initial RED exited 1 for the intended member-task leak; GREEN passed.
- [x] Derive report operational-detail inclusion from the persisted owner: system and active-admin reports allow it; member, unknown, and inactive-owner private reports deny it.
- [x] Documentation: repair the HANDOFF migration chain with `e6f7a8b9c0d1` then `f7a8b9c0d1e2` before auth; align current strategy references to `signal-v0.7.0-research` in the related current-state architecture/implementation/deployment handoffs without changing labeled historical evidence.
- [ ] Review: ownership = 22 passed (exit 0); auth + password = 55 passed, 1 PostgreSQL safety skip (exit 0); compileall/Node/scoped Ruff/diff check = 0. One full project-venv pytest was started sequentially and completed, but this execution environment truncated its result and did not retain an exit code, so it is not claimed as passed. Full-tree Ruff exits 1 on 86 pre-existing cross-module violations; scoped Ruff for this change passes. No commit, push, deployment, dotenv read, or production database access.
