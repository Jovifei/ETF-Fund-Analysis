# CI price-structure median performance correction

Date: 2026-10-03 Asia/Shanghai (2026-10-02 UTC).
Baseline: `67d1a648efa549b3c52743ce5c839ccc527cfec9` on
`codex/remote-stage-s8f0-s2-20261002`.

## Verified failure and cause

- [Full CI run 37029499272](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/37029499272), job `110912471874`, completed with `cancelled` in the Python test step. The log starts pytest at `2026-10-02T15:48:37Z`, last prints 29% at `15:56:12Z`, and reports cancellation at `16:23:13Z`. The workflow has a 35-minute job budget. Compile, JavaScript, migration, shell, image build and smoke steps were skipped; the attempted audit upload had no files. This is not a completed full-CI pass.
- The existing session-scoped pytest database retains the 420-day bootstrapped watchlist. Many board tests legitimately capture support/resistance for every enabled instrument. A tail-history test took 47.761 seconds in the earlier complete local aggregate but 0.63 seconds when profiled alone with an empty database. These are different fixture workloads, not a like-for-like speedup claim.
- A direct, deterministic 250-bar mock replay of `510300.SH` made 68,199 NumPy median calls. These consumed 1.210 of 1.569 profiled seconds, approximately 77%. The historical-cutoff/pivot-cluster loop repeatedly constructs NumPy arrays for very small lists of Python floats. No provider retries or network requests are involved in this reproduction.

## Minimal correction and unchanged contract

The five median expressions in `backend/app/utils/price_structure.py` now use
Python's `statistics.median` on the same lists. `_normalize` already converts
prices to finite positive Python floats and rejects invalid OHLC before cluster
calculation. Odd medians and the mean of the two middle even observations retain
the same arithmetic. No window, threshold, rounding, lifecycle, identifier,
qualification, strategy version, database schema or provider behavior changes.

No tests are disabled or omitted, no fixture is shrunk, and the CI timeout and
all downstream gates remain unchanged. This is a computation-cost correction;
it does not certify market data, enable Chan, promote `actionable`, or deploy.

## Reproduction and exact-output evidence

1. The new no-NumPy-dispatch regression failed on the original code before the
   implementation edit, at `_clusters` calling `np.median`.
2. Three fixed full-payload cases compare the scalar implementation with the
   legacy NumPy expression: a window-roll/expiry case, a failed-breakout/new-box
   case, and a seeded noisy 250-bar case. Comparison includes all fields,
   structure IDs and lifecycle events.
3. Boundary tests cover odd/even counts, repeated prices, subnormal values,
   adjacent floats, the largest finite float and identical numeric overflow results.
   NaN, positive/negative infinity and nonpositive prices remain rejected before
   median evaluation. NumPy warning/global-`seterr` side effects are not an
   equivalence claim; production does not depend on them.
4. An unprofiled benchmark uses the committed baseline module and the patched
   module in the same process, fixed mock dates `2025-08-08`–`2026-10-02`, the
   latest 250 bars, and three runs each. Baseline: 0.7164/0.6989/0.7094 seconds;
   scalar: 0.1232/0.1219/0.1215 seconds. Median speedup: **5.82×**, with exact
   complete-payload equality. This is a local hot-path benchmark, not a promised
   end-to-end CI runtime.
5. A separate fixed-date differential run covers all 35 enabled mock instruments
   at 250 bars each: every complete payload matches exactly. Total baseline
   replay time was 42.7945 seconds; scalar replay time was 6.9457 seconds (6.16×).
   Environment: Python 3.12.14, NumPy 2.5.3, pandas 2.3.3.
6. Independent review found no blocking code issue. It independently passed the
   three new regressions, 10,005 exact-bit float-cluster comparisons, 12 complete
   payload comparisons across normalized numeric types/random OHLC, and 40
   invalid-field cases. These are reviewer-reported checks, separate from the
   author-run suites above.

## Shared test-state isolation correction

The initial selected 111-case run finished in 245.905 seconds with 108 passed
and three failures. Every structure/median and decision-board assertion passed;
the failures were the two v103-history snapshot-read assertions and the
cross-surface KDJ assertion. All three passed when isolated (7.171 seconds).

The producer `test_snapshot_marks_old_verified_quote_stale_and_keeps_anomaly_visible`
left a snapshot dated nine minutes after the bootstrap quote and deleted an
indicator in the shared session database. Shorter execution makes that future
snapshot overshadow later tests; the missing indicator changes the KDJ display.
A four-test sequence consisting of this producer and the three failures
reproduced **1 passed / 3 failed on the unchanged baseline commit**, confirming
an existing ordering/time dependence rather than a changed median result.

The producer now keeps all existing assertions inside `try/finally` and rolls
back its transaction, including on an assertion failure. This restores the
snapshot, quote and indicator test mutations. The same four-test sequence now
passes all four cases in 53.405 seconds. Independent review also checked the
transaction boundaries and both baseline/corrected XML receipts and cleared
the isolation change. No runtime database behavior is changed.

## Validation status

- Python compileall for `backend/app` and `scripts`, all eight CI JavaScript
  syntax checks, 27 browser JavaScript tests, committed-secret scan, Ruff for the
  performance utility/regression file, generated-progress consistency and
  `git diff --check`: PASS.
- Additional support/resistance-zone and chart-research-layer suite: 6 passed.
- Initial selected structures/board/history/cross-surface suite: 108 passed /
  3 pre-existing shared-state failures, diagnosed and reproduced as above.
- Isolated victims: 3 passed. Corrected producer/victim sequence: 4 passed.
- Complete aggregate of the reviewed F0 batch plus this performance/isolation
  correction: **1493 collected / 1482 passed / 11 existing skips / 0 failures or
  errors**, exit 0, **569.823 seconds (9m30s)**. Code/test files were frozen for
  the entire run. JUnit SHA-256:
  `327d76124b732b43b4a077ecb7c6c7468cd123b6489c35afa7ae4c9b5e933703`.
- The separate stable F0-only aggregate was 1490 collected / 1479 passed /
  11 skipped / 0 failures, 1684.152 seconds. The combined local run was about
  66% shorter (2.96× faster), despite its three additional regression tests.
  This measured local comparison is separate from the exact pushed-commit CI
  evidence below.
- Independent performance and test-isolation code reviews: PASS. Reviewed F0
  files were integrated with matching hashes and published by normal fast-forward
  to the existing branch. Exact remote tree equality and CI are verified below.
  No production deployment is claimed.

Frozen code/test SHA-256s:

- `backend/app/utils/price_structure.py`: `ce58ee3125ad49975027ca6d1ea234719a3ba62ac7cca2216a3ac8f18a989668`
- `backend/tests/test_price_structure.py`: `f27383be8ec63936f19a2cd07709df316a3de98c27289a3e88f73072625641a1`
- `backend/tests/test_decision_board.py`: `c60ca4b99744a67a9de542f8a6f9eb99256d3b9fa25fc555916021ed2c46adbf`
- The unchanged F0 runner/test hashes are recorded in the [F0 orchestration receipt](S8_F0_OFFLINE_ORCHESTRATION_20261002.md).

The Windows-only bound project-hub reporter and local root-doc synchronization
are unavailable in this cloud checkout. They remain a handoff item; no local
reporter execution or hub acceptance is claimed. Shared progress/status records
were reconciled with the F0 terminal evidence for this combined candidate.

## Exact-commit remote CI closure

The existing branch was updated without force to
[`b7990877cac4f79ef7e2530ed0f94b55b943f533`](https://github.com/Jovifei/ETF-Fund-Analysis/commit/b7990877cac4f79ef7e2530ed0f94b55b943f533),
parent `67d1a648efa549b3c52743ce5c839ccc527cfec9`. The returned remote tree
`439b15f6eddf2c2dc0d5c0daba604105a3e6a5a0` exactly matched the independently
reviewed 17-file staged candidate. The remote head was re-read after publication.

All three exact-head workflows are terminal SUCCESS:

- [Full CI 37038405848](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/37038405848): `2026-10-02T17:05:57Z` through approximately `17:20:49Z` (14m52s), within the unchanged 35-minute budget
- [Workspace CI 37038405866](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/37038405866): backend contracts, high-severity dependency gate, TypeScript, Vue tests/build, isolated browser smoke, authenticated journeys and responsive/chart acceptance
- [Platform audit 37038405846](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/37038405846): temporary PostgreSQL concurrency/migration contracts and Windows bridge/ACL/environment checks

The full-CI JUnit was downloaded and inspected: **1493 collected, 1482 passed,
11 existing skips, zero failures/errors, 651.036 seconds**. JUnit SHA-256:
`1a24633d9f52ac34f28bb6af7bfd97c74b8255a19c5dc419d60662e224989eda`.
Every downstream full-CI step succeeded, including Python compilation, JavaScript
syntax/tests, secret scan, clean Alembic migration, shell/Compose validation,
production image build, PostgreSQL-backed image smoke, inventory, image export
and artifact uploads. These steps had not run on the timed-out baseline.

Verified artifact identities:

- `audit-ci-37038405848`, artifact `11242825264`: downloaded ZIP SHA-256 matches the GitHub digest `70c0a2dde3d1b9b513f36c4c62b74be7f2e7ff964d8224b7a3e00c5d66cf0e77`
- `production-image-37038405848`, artifact `11242795241`: 397,930,548 bytes; GitHub artifact digest `2ae859e6a849a7e70da6b9e514de8a51630b870fe76f8403843c93d5d776221f`; expires 2026-10-09
- Downloaded release inventory binds the source SHA/tree above to local CI image ID `sha256:04416daea509677fc1c0faf3eb03321cc806f0bcad6d0695027aab53bd4ab0c9`, migration head `f0e1d2c3b4a5`, matching app/frontend versions 1.0.5, a clean tracked source and zero untracked application files

The inventory explicitly says `production_deployed=false`, qualification
`not_asserted` and `published_image_digest_missing`: no image was published to a
registry and no production release completeness is asserted. No real-provider
probe or production action was performed. This section binds its verdict to
`b799087`; a later documentation-only head must be checked independently.
