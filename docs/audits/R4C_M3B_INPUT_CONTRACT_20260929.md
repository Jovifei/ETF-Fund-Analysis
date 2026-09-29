# R4C M3B-A daily application input identity contract

- Date: 2026-09-29
- C2C task / iteration: `c2c_a1d7` / 64
- Status: local implementation and scoped verification complete; GitHub push and remote review pending
- Plan base: `003c19dcdbca5dc8ff6d08607aa23a477f3aac30` / tree `911d38d26ac635fa8aa87156b4c647cb1b1470f8`
- Test/code commit: `1fdcf5110d77a2a8eff3074d526273b0d181b2ee` / tree `6f03a3853c91ea21a93ee937540482299b14d130`
- Branch: `codex/r4c-pre-m4-regression-diagnostic`

## Iteration 65 R1 recovery addendum — 2026-09-30

- Remote iteration 64 correctly marked the original M3B-A submission `CHANGES_REQUIRED`; the blocker was future split evidence being applied to historical inputs while the bound price basis excluded that future event. Iteration 65 `PLAN_UPDATE` then explicitly authorized the two DecisionBoard cutoffs described below. The original chart parity assertion remains unchanged.
- `research_history_rows(..., effective_through=...)` now applies only events effective by the requested date. `chan_input.py` and historical R4A read-model calls pass matching dates. `DecisionBoardService._derive_provisional()` uses the Shanghai market date from `observed_at`; `_row()` uses the Shanghai market date from snapshot `generated_at`. Existing calculations and product rules are otherwise unchanged. This proves the causal event transformation at those callsites; it does not certify the entire historical DecisionBoard snapshot process as PIT complete.
- Two DecisionBoard regressions prove the split is excluded before its effective date and included on/after it, including UTC-to-Shanghai date normalization. The original historical provisional chart/DecisionBoard MA20 parity test passes without weakening it. The added fixed-symbol Chan fixtures now use isolated SQLite databases so they cannot leave rows in the shared suite DB. Initial full-run collision failures and the selected-order provisional-count assertion are retained as harness history; final module-order tests and full suite pass.
- Targeted evidence: original seven-module regression group 78/78; expanded R1 causal/Chan/M2/M3 group 80 passed / 4 environment skips / 0 failures; DecisionBoard selected regressions 7/7. JUnit and stdout are under `E:\Claude_allow\Download\ETF_R4C_M3_20260929`.
- Final Windows repository pytest: 1,335 collected; 1,316 passed, 19 environment skips, 0 failed, 0 errors, 35 warnings, 1,497.50 seconds, exit 0. JUnit: `r1-full-final-clean-20260930.xml`; full output ends with this result in `r1-full-final-clean-20260930.txt`.
- M2 Python 3.12.14 / CZSC 1.0.1: Windows 25/25 and Linux x86_64 / glibc 2.41 25/25. Adapter semantic digest stayed `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac`. R5.2.1 history digest stayed `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9`; validator semantic digest `0f4ae0322b5d390c41e618da4c342abea66baac30bce4ccfe4a5f0d713cff76f`; observation/structure/revision collisions 0/0/0 and injected weak-ID collision detected on both platforms. Linux commands ran in an isolated container with repository mounted read-only; package cache and outputs stayed under the evidence directory.
- Final static gates: Ruff, `compileall`, Node syntax, scoped `check_no_secrets.py`, and `git diff --check` pass. No new lint findings remain after tidying pre-existing one-line formatting in the already authorized read-model/test files.
- Route A remains accepted; no identity formula, corporate-action arithmetic, engine/dialect or migration changed. `DEPLOYMENT_DISPOSITION=NOT_DEPLOYABLE_SUBSTAGE`, `M3B_A_PRODUCTION_GO=false`, `PRODUCTION_CHANGED=false`, `REAL_DATA_QUALIFICATION=UNKNOWN`, `ACTIONABLE=false`. No Provider call, worker/API/UI integration, production write, deployment, main merge or trading change.
- Exact R1 application/test HEAD and GitHub branch tip are recorded in the subsequent delivery section after commit/push. Remote acceptance remains pending until the Project audits that exact head and these evidence records.
- R1 code, tests, plan and receipts are bound to commit `f6de8a6ec2f5dd2b4ea7c411afb50dc5a6dcbd10` / tree `5c1f2921602780bef6def9b4efaed0f538463b31`. `origin/codex/r4c-pre-m4-regression-diagnostic` was read back at the same commit after push. The code-tested commit is exact; a following docs-only handoff commit, if any, is identified separately and does not alter application files.

## Iteration 66 M3B-A2 W/M identities — local verification

Remote authorized M3B-A2 from base `f854d6c9db0b774687f226cfb587cc03ddc814c5`: deterministic W/M aggregates from accepted causal D input using existing `aggregate_bars()`. No new calendar algorithm or chart/read-model oracle was added. The exact D identity ledger captured before implementation remains byte-identical.

- W/M are produced only after D freeze succeeds. Period identities bind contract versions, instrument, W/M interval, effective R4A price basis, adjustment version, period bounds, last observed constituent time, ordered D source IDs, period config and aggregate OHLCVA. Revision identity binds W/M logical series and ordered aggregate source IDs; M2 `prepare_research_input()` remains the sole input-hash implementation.
- `FrozenChanInput.constituent_source_bar_ids` is empty for D and contains ordered constituent IDs for every W/M aggregate. Incomplete calendar periods use `temporary`; closed periods use `settled`. No provisional/unsettled D rows enter.
- Final A2 focused suite: 96 collected, 92 passed, 4 environment skips, 0 failures/errors. It covers D ledger preservation, W/M aggregate parity, namespace and lineage, append/correction propagation, partial/closed periods, corporate-action transitions, unknown/zero quantities, and Provider/DB-side-effect boundaries. JUnit: `E:\Claude_allow\Download\ETF_R4C_M3_20260929\m3b-a2-final-focused-20260930.xml`.
- M2 Windows/Linux 25/25. Adapter semantic digest `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac`; R5 history digest `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9`; validator semantic digest `0f4ae0322b5d390c41e618da4c342abea66baac30bce4ccfe4a5f0d713cff76f`. Both platforms report 0/0/0 identity collisions and detect the injected weak-ID collision.
- Ruff, compileall, Node syntax, scoped secret scan and diff-check pass. No `candle_periods.py`, shared R4A runtime, persistence or schema change; the A2 focused gate is used instead of another full repository suite.
- A2 has no runtime consumer; `DEPLOYMENT_DISPOSITION=NOT_DEPLOYABLE_SUBSTAGE`, `PRODUCTION_GO=false`, `REAL_DATA_QUALIFICATION=UNKNOWN`, `ACTIONABLE=false`. M3B-B remains NO-GO until A2 remote PASS.
- A2 code/test commit `9992ba8ceb13cd45ba7132fd4d05d755e2ec74cd` / tree `536355297a6af1d65bc297e3e7fa448b76c27136` is pushed on the same branch; GitHub branch readback matched at push time. The following commit is documentation-only. A2 remote review remains pending; M3B-B stays NO-GO until A2 PASS.

## Iteration 67 A2-R1 remote-review follow-up — 2026-09-30

The iteration-66 exact-head review confirmed final GitHub head `8b5440142c183762d202bc8c0e5a69830f0a3635` / tree `59d954885a9df3785997dbcfdfb5cc922f714df2`, retained the technical route, and returned `M3B_A2_DECISION=CHANGES_REQUIRED` for two bounded gaps:

1. A W/M request blocked by its prerequisite daily freeze must not return D-series identity metadata (`logical_series_id`, `input_revision_id`, or `source_bar_ids`) as though a period identity had been constructed. The follow-up leaves those fields empty and preserves only the bounded blocker plus known price basis/as-of evidence.
2. Historical-correction lineage coverage exercised weekly aggregation but not monthly aggregation. A two-month regression now corrects one January daily constituent and `quality_hash`; only the January aggregate identity/lineage changes, the February identity/lineage and M logical/basis namespace remain stable, and M input revision/hash changes.

The implementation changes only `backend/app/research/chan_input.py` (removes three D identity fields from the blocked W/M propagation) and `backend/tests/test_chan_m3b_input.py` (two blocked-result cases and monthly lineage regression). No identity formula, D ledger, calendar aggregation, corporate-action arithmetic, persistence, Provider, adapter, worker, API, UI, migration, main, or production code changed.

- RED evidence: `E:\Claude_allow\Download\ETF_R4C_M3_20260929\m3b-a2-r1-red-20260930.xml` contains two expected blocked-W/M identity failures; the monthly correction test passes against the generic implementation and locks the coverage gap.
- Final focused gate: 99 collected, 95 passed, 4 environment skips, 0 failures/errors. All 29 `test_chan_m3b_input.py` tests pass, including the two new gates. Full JUnit is `m3b-a2-r1-final-focused-20260930.xml` in the evidence directory.
- M2 Windows Python 3.12.10/CZSC 1.0.1: 25/25; M2 digest `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac`. The host has no 3.12.14 runtime available locally; Linux was rerun on Python 3.12.14 / glibc 2.41 and passed 25/25 with the same digest. Both adapter validators agree.
- R5.2.1 Windows/Linux: history digest `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9`; semantic digest `0f4ae0322b5d390c41e618da4c342abea66baac30bce4ccfe4a5f0d713cff76f`; observation/structure/revision collisions 0/0/0; injected weak-ID collision detected on both platforms.
- Static: Ruff, Python 3.13.14 compileall, Node syntax, scoped secret scan, and diff-check all pass. Shared R4A/calendar code stayed untouched, so the remote focused-gate exception applies; no full repository suite was run.
- Preserved harness attempt: the first isolated Windows M2 mirror omitted `backend/app/utils/hashing.py` and failed at import (23 failures/2 passes). The exact helper was added to the isolated mirror; the rerun passed 25/25. This was a harness omission, not a product assertion failure.

The code/test repair was committed as `9f935a864f5071debbd66b0f6d4cc40e68a73a2d` / tree `04294de8952b45f4245cd2bc0b3e569322fa9857`, parent `8b5440142c183762d202bc8c0e5a69830f0a3635`; it changes only `chan_input.py` and its tests. Final docs-only head `6166587d718992237908099b6b89ea83f3779d3d` / tree `f7a096be408ce908cb5e5c282b19025153ec0653` was pushed and read back from GitHub. Remote iteration 67 exact-head review returned `M3B_A2_DECISION=PASS`, retaining the route and authorizing iteration 68 `M3B_B_GO=true`.

## Iteration 68 M3B-B plan accepted — 2026-09-30

Remote plan: `R4C_M3B_B_AUDITED_WORKER_PUBLICATION`, plan base `6166587d718992237908099b6b89ea83f3779d3d`. It adds only an internal bounded `chan_structures` request and worker branch, reuses the audited workspace queue, accepted M3B-A/A2 input, CZSC adapter and M3 publisher, with freeze/compute/publish in separate short DB scopes. Public `DataRequest`, scheduler, UI, Provider, M3 schema, config activation, main, and production remain unchanged/forbidden.

M3B-B requires focused worker/data-job tests, exact CZSC 1.0.1 worker/service integration on Windows Python 3.12.x and Linux Python 3.12.14 using synthetic rows, and one disposable PostgreSQL 16 worker-style publication/idempotency/failure integration. Because shared worker/data-job runtime changes, the full Windows repository pytest is mandatory. Deployment remains `NOT_DEPLOYABLE_SUBSTAGE` / `PRE_RELEASE_RUNTIME_COMPONENT`; M3B-C is still false and is the first release-bearing read-only product slice. Detailed scope is in `tasks/plans/2026-09-30-r4c-m3b-b-audited-worker-publication.md`.

M3B-B local implementation and verification are complete; its execution receipt is `docs/audits/R4C_M3B_B_WORKER_PUBLICATION_20260930.md`. The implementation is not yet committed/pushed and awaits exact-head remote review. Production is unchanged, real-data qualification remains `UNKNOWN`, `actionable=false`, and no auto-trading is enabled.

## Remote gate and boundary

Iteration 63 was independently accepted as `PRE_M4_DIAGNOSTIC=PASS`; remote review also reconfirmed `M0_TECHNICAL_GATE=PASS`, `M0_BASELINE_GATE=PASS`, and `ROUTE_A=RETAIN`. Iteration 64 authorized only `R4C_M3B_APPLICATION_INPUT_CONTRACT` / M3B-A:

- `M3B_A_INPUT_CONTRACT_GO=true`.
- `M3B_A2_GO=false`, `M3B_B_WORKER_GO=false`, `M3B_C_READ_MODEL_GO=false`, `M4_PAGE_IMPLEMENTATION_GO=false`, `MAIN_INTEGRATION_GO=false`.
- Real-data qualification remains `UNKNOWN`; actionable remains `false`; production is unchanged.

This was the iteration-64 gate snapshot. It was superseded after iteration-65 R1 `PASS`; iteration 66 explicitly authorized M3B-A2.

Jovi added a standing requirement to deploy completed, tested, GitHub-pushed feature stages and verify them live. Remote reconciled this with iteration 64: `M3B_A_PRODUCTION_GO=false` and `PRODUCTION_DEPLOYMENT=NOT_APPLICABLE` because this substage adds an unused input contract without user-visible or runtime behavior. This is an explicit non-deployable substage, not a silently skipped release. Do not add worker, read-model, API, UI, Provider, runtime, production, or main-merge scope to make it deployable.

Remote set the standing disposition to `DEPLOY_REQUIRED` for future independently user- or runtime-observable stages. It described M3B-B as a pre-release worker component with no standalone production activation and M3B-C as the first coherent read-only application read-model/GET slice requiring deployment. Such a plan must include candidate-image identity, fresh verified production backup, production-backup restore and Alembic upgrade rehearsal on disposable PostgreSQL 16, rehearsed rollback mode, auth/health/read-only smoke checks, and sanitized post-deployment evidence. No production mutation is part of this receipt.

## Implemented contract

The new [chan_input.py](../../backend/app/research/chan_input.py) reads persisted `DailyBar` rows only. It does not use provisional quote rows, call a Provider, execute CZSC, publish database state, or use `chart_data()`'s content-bound chart `series_id`.

The input is daily (`D`) only. `as_of` uses the configured market timezone; a row dated on the `as_of` day is excluded before 15:15 and included at/after 15:15. Adjustment selection, official corporate-action research transformation, and `research_price_basis_id` reuse the accepted R4A contracts `research_history_rows()` and `research_price_basis()`. History failing `price_history_issue()` blocks preparation. Only documented volume/amount sources are accepted; missing values and undocumented units return explicit blocked reasons. Numeric zero is preserved.

Identity formulas are versioned and separate from presentation identity:

- `logical_series_id` binds `instrument`, `D`, `research_price_basis_id`, adjustment-contract version, and `r4c-price-series-v1`. It excludes input hash, current cutoff, indicator version, and chart UI contract.
- `source_bar_id` binds the instrument/date, stored adjustment/source/quality revision, research basis and adjustment version, and both stored and transformed OHLC/volume/amount values.
- `input_revision_id` binds the logical series and ordered source-bar IDs. Appending a bar or correcting one historical revision changes the input revision while leaving the logical series identity stable.
- `PreparedResearchInput` is built through the accepted `prepare_research_input()` function. Its returned `input_hash` remains the sole canonical hash; M3B-A defines no competing hash.

A result status of `prepared` means only that the M2 input contract validated. It does not enable or execute the engine. Unsupported weekly/monthly intervals, unavailable history, ambiguous basis, unverified units, and invalid source evidence return `blocked` with a reason code.

## Tests and verification

The new M3B-A suite has eight focused tests covering:

1. R4A research OHLC/volume/amount and price-basis parity, including the official split-research path.
2. Stable logical-series identity across repeated reads, cutoff advance, future-bar append, and historical correction.
3. Bar-revision identity changes only for the corrected bar; unaffected bar IDs remain stable.
4. `research_price_basis_id` or adjustment-contract version changes produce a distinct logical series namespace.
5. Indicator-version changes do not affect Chan logical-series identity.
6. The 15:15 settlement boundary and earlier-`as_of` future-bar exclusion.
7. Unknown/unverified volume and amount fail closed while true zero values survive.
8. Unsupported non-daily intervals block, and freezing performs no database DML.

| Gate | Result |
|---|---|
| M3B-A tests, Windows Python 3.13.14 / pytest 9.1.1 | 8 passed in 0.26 s |
| R4A `test_v103_history.py` + M2 contract regression, Windows Python 3.13.14 | 48 passed, 3 skipped, 5 existing warnings in 3.25 s |
| M2 focused contract, Windows Python 3.12.14 / CZSC 1.0.1 | 25 passed, 1 existing SQLAlchemy warning in 1.51 s |
| M2 focused contract, Linux x86_64 / glibc 2.41 / Python 3.12.14 / CZSC 1.0.1 | 25 passed in 1.74 s |
| M2 300-bar adapter semantic digest, Windows/Linux | `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac` on both |
| R5.2.1 history digest, Windows/Linux | `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9` on both |
| R5.2.1 collision gates, Windows/Linux | observation/structure/revision collisions `0/0/0`; injected weak-ID collision detected on both |
| Static gates | Ruff, compileall, scoped secret scan, and `git diff --check` passed |

The M2 adapter resource probe passed on both platforms. Windows measured 6.249 ms warm/300, 950.222 ms combined prefix preparation+sweep, and 139,862,016-byte peak RSS. Linux measured 6.254 ms warm/300, 893.107 ms combined preparation+sweep, and 222,973,952-byte peak RSS. Both are within the accepted M1 budgets. The R5.2.1 checker reported 281 observations, 6,604 records, 6,568 revisions, zero namespace collisions, and detected the injected collision on both platforms.

The iteration-64 submission used a bounded-only verification exception because it added only a new module and its tests. R1 changes shared application behavior, so the repository-wide gate above was required and was completed on the final candidate.

### Preserved environment/harness attempts

- The initial RED run failed because `chan_input.py` did not exist yet; this is the expected test-first signal. Output: `m3b-red-initial.txt`.
- The first Linux M2 attempt loaded the repository `conftest.py` inside a minimal container and stopped before collection because SQLAlchemy was not part of that adapter-only environment. The next isolated mirror omitted repository files that two source-contract tests read and produced 23 passes / 2 harness-path failures. Both failures are retained, not counted as product failures.
- The final Linux run mirrored the exact M2 test, `pyproject.toml`, selected source files, and config into an isolated `/tmp` tree to exclude unrelated database fixture setup while preserving the test bytes. It completed 25/25; adapter and R5.2.1 validators then passed with the same Windows digests.

Detailed command output is retained under `E:\Claude_allow\Download\ETF_R4C_M3_20260929` and will be released through the iteration-64 execution records. Key final files include `m3b-focused-final-iteration64-r2.txt`, `m3b-r4a-m2-windows-py313-final-iteration64.txt`, `m2-windows-py312-iteration64-detailed.txt`, `m2-linux-focused-iteration64-r2.txt`, both platform adapter-validator JSON files, and both platform R5-validator JSON files. The final M3B-A output SHA-256 is `d07df15a312259e1cd2a159778286dfa6f06806420c1c385381acbf2b89b81a`; the final combined R4A/M2 Windows output SHA-256 is `69a3ae9871062af883f402b11abbca8d29ccde17e6ed09ee1d8dbeda4dcd1eb3`.

## Not performed

No weekly/monthly aggregation, DB writes, Provider call, CZSC import/execution, worker, read model, API, frontend, main merge, deployment, or production DB change. Real-data qualification remains `UNKNOWN`, `actionable=false`, and automatic trading remains out of scope.
