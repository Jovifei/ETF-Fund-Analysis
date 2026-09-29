# R4C M3B-A daily application input identity contract

- Date: 2026-09-29
- C2C task / iteration: `c2c_a1d7` / 64
- Status: local implementation and scoped verification complete; GitHub push and remote review pending
- Plan base: `003c19dcdbca5dc8ff6d08607aa23a477f3aac30` / tree `911d38d26ac635fa8aa87156b4c647cb1b1470f8`
- Test/code commit: `1fdcf5110d77a2a8eff3074d526273b0d181b2ee` / tree `6f03a3853c91ea21a93ee937540482299b14d130`
- Branch: `codex/r4c-pre-m4-regression-diagnostic`

## Remote gate and boundary

Iteration 63 was independently accepted as `PRE_M4_DIAGNOSTIC=PASS`; remote review also reconfirmed `M0_TECHNICAL_GATE=PASS`, `M0_BASELINE_GATE=PASS`, and `ROUTE_A=RETAIN`. Iteration 64 authorized only `R4C_M3B_APPLICATION_INPUT_CONTRACT` / M3B-A:

- `M3B_A_INPUT_CONTRACT_GO=true`.
- `M3B_A2_GO=false`, `M3B_B_WORKER_GO=false`, `M3B_C_READ_MODEL_GO=false`, `M4_PAGE_IMPLEMENTATION_GO=false`, `MAIN_INTEGRATION_GO=false`.
- Real-data qualification remains `UNKNOWN`; actionable remains `false`; production is unchanged.

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

The required 26-minute repository-wide suite was not rerun: iteration 64 permits the bounded module, affected R4A/M2 regressions, cross-platform M2/R5 gates, and static checks when changes are isolated to the new module/tests/docs and no shared application behavior changes.

### Preserved environment/harness attempts

- The initial RED run failed because `chan_input.py` did not exist yet; this is the expected test-first signal. Output: `m3b-red-initial.txt`.
- The first Linux M2 attempt loaded the repository `conftest.py` inside a minimal container and stopped before collection because SQLAlchemy was not part of that adapter-only environment. The next isolated mirror omitted repository files that two source-contract tests read and produced 23 passes / 2 harness-path failures. Both failures are retained, not counted as product failures.
- The final Linux run mirrored the exact M2 test, `pyproject.toml`, selected source files, and config into an isolated `/tmp` tree to exclude unrelated database fixture setup while preserving the test bytes. It completed 25/25; adapter and R5.2.1 validators then passed with the same Windows digests.

Detailed command output is retained under `E:\Claude_allow\Download\ETF_R4C_M3_20260929` and will be released through the iteration-64 execution records. Key final files include `m3b-focused-final-iteration64-r2.txt`, `m3b-r4a-m2-windows-py313-final-iteration64.txt`, `m2-windows-py312-iteration64-detailed.txt`, `m2-linux-focused-iteration64-r2.txt`, both platform adapter-validator JSON files, and both platform R5-validator JSON files. The final M3B-A output SHA-256 is `d07df15a312259e1cd2a159778286dfa6f06806420c1c385381acbf2b89b81a`; the final combined R4A/M2 Windows output SHA-256 is `69a3ae9871062af883f402b11abbca8d29ccde17e6ed09ee1d8dbeda4dcd1eb3`.

## Not performed

No weekly/monthly aggregation, DB writes, Provider call, CZSC import/execution, worker, read model, API, frontend, main merge, deployment, or production DB change. Real-data qualification remains `UNKNOWN`, `actionable=false`, and automatic trading remains out of scope.
