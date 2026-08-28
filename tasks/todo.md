# v0.5.0 Local Validation Execution Plan

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
