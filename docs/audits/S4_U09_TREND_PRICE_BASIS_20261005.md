# S4-U09 trend-line price-basis projection repair

## Local-only scope and identities

This is an isolated local candidate based on `b3b6b4a23207273c8bfb1eb7666ab2dc94d27323` (tree `c66660bc6c5b929c4a8c7d798b1d3aa543d224c2`). The existing source worktree and its direction-display candidate are preserved. The coordinating task's current remote observation is `8c7f34209726862451b6a5379669b35cf134c593`; this candidate does not advance that remote. The prior direction-display publication block remains in effect. There was no push, publication retry, merge, deployment, production-data change, provider call, or new execution task in this batch.

The owning candidate commit is queryable with `git log -1 -- frontend/tests/chart-basis.test.ts` in the isolated worktree. Local verification is not exact-remote CI and does not establish production acceptance.

## Reproduced defect

`backend/app/workspace/candle_periods.py::transform_chart` computes `studies` from `research_series`. The raw view already discarded research indicators, horizontal support/resistance, price boxes, and Chan geometry when `raw_overlay_allowed` was false. However, it left `studies.trend_lines` in the projection. Selecting DERIVED or opening all studies caused ChartAdapter to draw the research endpoint prices on unadjusted candles.

Before changing runtime code, the updated chart-basis suite ran through the real EtfChart and ChartAdapter, mocking only KLineCharts. It produced **3 failures / 4 passes**. The modeled split-price fixture has raw closes 10/12 and research closes 5/6, at matching candle dates. All three failures recorded a segment with endpoint values 5 and 6 on raw candles: DERIVED selection, open-all selection, and return from research to raw. This is a supported-input reproduction; no claim is made about a live instrument's production occurrence.

## Minimal repair and retained behavior

The only runtime change clears `trend_lines` alongside `chan_structure` in the existing mismatched-raw projection. The source payload is not mutated. Raw OHLC, volume, amount, and the separately allowed cost overlay remain intact. Switching to research uses the original research studies, preserving exact endpoint dates, prices, and dashed line styling. Returning to raw applies the projection again.

ChartAdapter remains unchanged deliberately:

- `raw_overlay_allowed` describes the raw chart, and the research projection inherits it. Guarding all adapter trend drawing with that field would incorrectly suppress valid research trends.
- `sr_overlay_allowed` also depends on whether horizontal levels exist. It must not be used to require horizontal levels before drawing valid trend geometry.
- Same-basis raw charts retain their existing behavior, including older payloads where `raw_overlay_allowed` is absent.

No indicator or support/resistance formula, backend payload meaning, corporate-action adjustment, input identity, data source, grouping, qualifier, or strategy threshold changes. Existing strategy `signal-v0.7.4-temporal-causality`, indicators `ind-v0.7.6-maturity-mask`, and forecast `similarity-corridor-v0.7.7-maturity-mask` remain unchanged. Real-data qualification stays UNKNOWN; actionable and calibration gates are not promoted.

## Verification

- Focused chart-basis suite: **7/7 passed**, after the recorded RED result. Covers actual unequal prices, DERIVED/open-all, two complete research-to-raw round trips, positive research lines with no horizontal levels, hide-all/reopen-all, same-basis raw allowed/missing-flag compatibility, exact endpoints, indicators, cost, volume, and payload immutability.
- Complete frontend suite: **196/196 passed in 23 files**. The existing single chart-basis test was retained and upgraded from an adapter mock; six cases were added.
- Actual Vue/TypeScript check and production build: **passed**. Existing Vite mixed static/dynamic import warning is unchanged.
- Python compilation, legacy app.js syntax, and etf_1430_workbench.js syntax: **passed**.
- Complete backend suite: **1,773 collected / 1,762 passed / 11 existing skips / 0 failures / 0 errors**, 1,059.611 seconds. This includes the existing corporate-action split-price daily/weekly/monthly contract regressions. No backend tests were skipped beyond their existing conditions or weakened to shorten this run.
- Independent review: **PASS, no blocking findings**. The reviewer independently ran **138/138 cases across 9 chart/Chan files**, actual vue-tsc, and git diff checks. An additional direct execution of the production display projection covered **30 combinations** of raw/research view, false/true/absent raw flag, and missing/empty/present study geometry. UNKNOWN/actionable=false, null amount/volume, and payload immutability were preserved. These reviewer checks are separate from the author's full frontend result.
- Git whitespace check: **passed**.

This batch changes no layout or visible copy. The canvas library is mocked for exact drawing-call assertions; no new real-browser or screenshot acceptance is claimed. Hosted exact-commit CI and deployment were intentionally not run. The Windows project-hub reporting CLI is not present in this Linux worktree; no hub report or root-document synchronization is claimed.

## Reproduction commands

From frontend, with the existing locked dependencies installed:

- `npm test -- tests/chart-basis.test.ts`
- `npm test`
- `npm run typecheck`
- `npm run build`

From the repository root, in the existing Python environment:

- `python -m pytest -q`
- `python -m compileall -q backend/app`
- `node --check backend/app/static/app.js`
- `node --check backend/app/static/etf_1430_workbench.js`
- `git diff --check`

The isolated worktree reused the existing local dependency installation for execution; it added no dependency or lockfile change.

## Lesson

A price-basis gate must cover every geometry channel that consumes research prices, including sloping trend lines, while retaining unrelated display data. Test with genuinely unequal raw/research prices and the real projection plus adapter; equal-price fixtures or a mocked adapter can hide the leak. Pair negative raw assertions with positive research and same-basis assertions so that a blanket hide-all fix cannot pass.

## Evidence hashes

- `frontend/src/components/EtfChart.vue`: `17d08a3c5d7e8a493af1bc53835ee49304f709ab4179117322907de3970441f7`
- Unchanged `frontend/src/lib/chartAdapter.ts`: `b660c619e8caf2ce109b0d512f7a84d8d2a495a50b6f025044b4caf06b9d77a8`
- `frontend/tests/chart-basis.test.ts`: `70a5f381b183a06ac86a61334d98dbf2f90703c987f08ab9e48a50836242afa8`
- RED JUnit: `27d9eab571e372cb5e7b5b2f64290a5fd9b3b9192fa5edf244731c5c86058c07`
- Focused GREEN JUnit: `fb8d56ee1e875f089efe8e40ac06387a2259e146c369acf487584567826971bf`
- Full frontend JUnit: `f58f44d2d294ff117fd2581f6199be6f5eed423e056557e2d1b2a98143c257f6`
- Independent focused JUnit: `881dc7152fba2bf0211a38b2a3a380b1969214aceb40ae005b132e664223e391`
- Full backend JUnit: `16f3669d75b4f7ffead228f21b05f97a1659fd9bc43dcec1782d872a58dc6e3d`
