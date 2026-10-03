# S4-U05 Chan observation-input settlement display

Recovery date: 2026-10-03 Asia/Shanghai. The recovery baseline was
`587b13611ed4e37e8cf20200c80ac67d4611ed00` on
`codex/remote-stage-s8f0-s2-20261002`.

## Scope and frozen contract

This is a bounded S4-U05 display repair, not full S4 or production acceptance.
The backend already hashes and stores observation/input-level `settlement_status`
and forwards it unchanged. Daily inputs are settled-only; weekly/monthly inputs
may be temporary or settled. No backend runtime, schema or price-field contract
is changed. CZSC 1.0.1, application `observed`, `engine_confirmation=unknown`,
immutable revisions, latest-observation/non-historical-PIT semantics,
`qualified=false` and `actionable=false` remain unchanged.

The previous visible text was **已保存中枢**, not “已确认”. A rendering shortcut
constructed a daily box with `confirmed_at=origin` to obtain solid Chan edges.
Chan zones now use the same clipped source-day coordinates directly, without
inventing a daily-box state or confirmation time.

- `settled`: 输入已结算, solid strokes and complete zone outline
- `temporary`: 输入暂定, dashed strokes and complete zone outline
- Missing/null/unrecognized status: 输入结算状态未知, dashed, never promoted
- The visible note says the status applies to this observation's input and that
  engine confirmation is unknown. Narrow-screen notes retain the same wording
- A single outlined rectangle avoids overlapping edge figures. Daily-box
  confirmation segmentation, clipping, prices and simplified-fallback styles
  stay unchanged
- Status-only replacements refresh note/style; repeated toggles remove the
  research group. Blocked/corrupt observations cannot become a simplified
  fallback through this change, and persisted settlement is not inherited by
  fallback geometry

## Recovery provenance

The former checkout and staged patch were unavailable after environment replacement.
The separate frontend-only build-context copy survived. All six changed frontend
files were recovered and verified against the original reviewed Git blob manifest.
The backend-test addition was reconstructed from the recorded patch and matches
its original blob too. Therefore all seven runtime/test files match exactly:

| File | Git blob |
| --- | --- |
| frontend/src/lib/chartAdapter.ts | 086c1686baaf027f7414f2b92c7705e5e1fd4fc4 |
| frontend/src/lib/types.ts | ba97bedbf9313389e92794647f4e33b1b8f6b8d3 |
| frontend/tests/chan-projection.test.ts | 52d736dd456b3b1f24e3d9f9915c484c87acd77f |
| frontend/tests/chart.test.ts | eb51d6471f29caf02cb960ad4785ab0e9696853a |
| frontend/tests/chan-settlement.test.ts | efcdd18232798e3e21c31b0cf581705051405d7e |
| frontend/e2e/chan-settlement.spec.ts | d437ede5abafb21fcdb86e0957d825298816f1d2 |
| backend/tests/test_chan_chart_overlay.py | f09899be3e64d5fd081bf9c7c081a02f3c676c10 |

`frontend/src/lib/chartAdapter.ts` SHA-256: `f27b2d65b1da25bb3299b9c54d274c94a2e1e4f4a3fa779cb6062c30e6337d8c`.
STATUS/HANDOFF historical entries were recovered from uploaded content-addressed
blobs. The remaining receipt/progress files are reconstructed and reviewed anew;
the old full 15-file staged tree is not claimed recovered. No prior test run is
used as a substitute for fresh validation of this candidate.

## Fresh recovery validation

Before restoring runtime changes, the new suite again reproduced **13 failures /
1 pass** against baseline 587b136. The recovered candidate then passed:

- Actual Vue typecheck and production Vite build
- **116 Vue tests / 20 files**; independently rerun by the reviewer
- **55 chart/projection/settlement tests** in America/New_York; the independent
  reviewer also passed the same 55 in Asia/Shanghai and Pacific/Honolulu
- **11 focused backend projection tests**, excluding the chart-route fixture
- **27 JavaScript tests**, Python compile, JS syntax, committed-secret scan
- Three new Playwright cases discovered: weekly temporary, weekly settled and
  monthly unknown; canvas dashes, toggle cleanup and desktop/mobile screenshots

First fresh aggregate: **FAILED**, 1501 collected / 1488 passed / 11 skips /
2 failures, 574.512 seconds. Both failures were provider-registration assertions:
Sina HTTPX client construction raised an ImportError because the cloud SOCKS
proxy requires `socksio`, absent from the new venv. No market request was made to
reproduce it. Failed-run JUnit SHA-256:
`bd9f05638c2082b862c3ab3105e73482ff1353300c3c3f76f3747c0b5647fcbb`.

Installing `httpx[socks]==0.28.1` restored this environment capability without
changing proxy settings, repository dependencies, runtime code or assertions.
All **11 tests in the two affected provider modules pass**. The first failed
run is retained separately. Final full fresh backend rerun: **PASS**, exit 0, **1501 collected / 1490 passed /
11 existing skips / 0 failures / 0 errors**, 554.135 seconds. Fresh JUnit SHA-256:
`9d47b6cb133c75502de538c0e7c4fafd3e19c54f74a1cfc508dd589570bb110e`.
The aggregate includes the chart-route contract excluded from the focused run. Frontend-only packaging recheck:
**PASS**, actual typecheck and production build in a source context without
`backend/tests`. The shared fixture remains under `frontend/tests/fixtures`. Independent source and complete 15-file receipt/progress review: **PASS**.
The reviewer independently reran typecheck, 116 Vue tests, the 55 chart cases in
three timezones, 11 focused backend tests, parsed the final JUnit, and verified
that all 11 skipped testcase identities match the retained 587b136 CI. No blocking
findings; exact new-head hosted browser/CI remain separate gates.
At recovery validation, exact new-head hosted CI/browser execution was pending
publication. It is now closed by the exact-head hosted receipt below.

A fresh Chromium launch check in this replacement environment again fails before
navigation with `socket() failed: Operation not permitted (1)`. This is current
blocked evidence, not a browser PASS. No screenshots, production login or real
market-data fetch are claimed from that attempt.

Environment installation: the optional legacy `chanlun` package has no compatible
CPython 3.12 Linux wheel; its source build tried to install Rust into a read-only
home cache and failed. Core/dev dependencies plus tushare, akshare and feedparser
were installed for the actual regression. No project dependency or lockfile was
changed. Optional exact-engine/platform skips must be reported from the new JUnit.

## Publication boundary

The predecessor 587b136's three workflows are terminal SUCCESS; its verified
closure is preserved in the WU2 receipt. After fresh aggregate validation and
independent review, publish an ordinary fast-forward on the same branch, preserving
587b136. Verify the exact new tree and all workflow results, including the three
new browser cases. No forced update, deployment, registry publication, production
login, migration, runtime activation or qualification promotion is authorized by
this display batch. Real data remains UNKNOWN; predictions remain not calibrated.
Windows hub/root-doc synchronization is pending its local environment; no success
is claimed for that separate operation.

## S4-U05 exact-head hosted closure — 2026-10-03 17:59 Shanghai

The reviewed 15-file candidate was published by ordinary fast-forward on the
existing branch `codex/remote-stage-s8f0-s2-20261002`:
commit `422c5c403d7336d1f7f01307bb99d5b8f2e6f25e`,
tree `9b37aae610ffbbc12f7a6146195bebead57f60c2`,
parent `587b13611ed4e37e8cf20200c80ac67d4611ed00`.
The remote ref and archived source identity were reverified. All 15 changed
source-archive blobs match the reviewed commit.

- [Full CI](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/37113897750):
  SUCCESS at 2026-10-03 09:57:05 UTC. Downloaded JUnit: 1501 collected,
  1490 passed, 11 existing skips, zero failures/errors, 700.910 seconds.
  Skip identities match the fresh local candidate run.
- [Workspace CI](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/37113897752):
  SUCCESS. Backend contracts 283 passed / 1 skip; actual Vue typecheck,
  116 Vue tests and production build passed. Chromium 31 smoke cases,
  5 authenticated journeys and 18 responsive cases passed.
  All three new settlement cases passed canvas dash, status wording,
  repeated overlay cleanup and desktop/390px assertions.
- [Platform audit](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/37113897764):
  SUCCESS for disposable PostgreSQL concurrency/migrations and Windows bridge/NTFS.

Downloaded workspace ZIP digest:
`e755c1a839c9765bfc4d4dc73c6f5cc3f7d53c80449cacd9ff4b6aa85b34b6ee`.
Desktop and 390px screenshots for temporary/settled/unknown inputs were inspected:
dashed/solid/dashed boundaries and explicit unknown engine-confirmation wording
are visible. Temporary hidden-overlay screenshot was also inspected; all three
hidden-overlay canvas assertions passed. This is synthetic-fixture evidence,
not production data or live-account acceptance.

Downloaded full audit ZIP digest:
`5902a2e09777d69d3bd94078071331896fd17d6743ea4c1b9d7b3c9e18de370b`.
JUnit SHA-256:
`739ad754b32e16fa6e884d61cb27a90ac0ecdb64a17a288e1ab729ce1f32b2b2`.
Inventory SHA-256:
`fbc31c2f6fa373e55204355af0e91839bdefb9749dc46869954027ed943a4b74`.

Migration/static/secret/Compose checks, image build, isolated PostgreSQL image
smoke, source/image inventory and CI image export all passed. Inventory binds the
exact commit/tree, with clean tracked worktree and zero untracked application
files. It correctly records `production_deployed=false`,
`registry_image_digest=null`, `data_qualification=not_asserted`.
`release_inventory_complete=false` because the image is an isolated CI artifact:
the sole missing item is `published_image_digest_missing`. The large image
archive's metadata was checked but the image ZIP was not downloaded or deployed.

This closes the bounded S4-U05 implementation and hosted regression gates.
It does not complete full S4, live private acceptance, production deployment or
data qualification. Engine confirmation remains unknown and actionable remains false.
