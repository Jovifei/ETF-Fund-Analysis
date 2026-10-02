# WU2 persisted Chan calendar-to-candle projection repair — 2026-10-03

## Scope and identity

- Existing branch: `codex/remote-stage-s8f0-s2-20261002`.
- Code baseline: `b7990877cac4f79ef7e2530ed0f94b55b943f533`.
- Concurrent docs closure preserved by fast-forward to publication parent
  `c61e4935ae3cc5ce62e29ba9ce09f3ec27f48e76`; its nine changed files are
  documentation only. No earlier closure commit was republished or overwritten.
- This is the bounded WU2 acceptance repair from
  [the next-stage plan](../planning/NEXT_STAGE_REMOTE_EXECUTION.md), covering
  existing S4-U01 evidence coordinates / S4-U04 zhongshu display. It does not
  complete the full S3/S4 stage or introduce another Chan algorithm.
- Only runtime edit: `frontend/src/lib/chartAdapter.ts`. Backend projection,
  geometry values, source identity, price basis, qualification, fallback policy,
  versions, Provider calls, schema, and trading behavior are unchanged.
- No deployment, production login, production database writes, real-market
  probe, or Chan activation. Real-data qualification remains UNKNOWN;
  actionable=false; no automatic trading.

## Reproduction and fix

The existing backend projection forwards persisted structure timestamps such
as `2026-09-01 15:00:00`. The frontend's `chanZone()` forwarded that timestamp
as box origin, but `box()` compared it with date-only candle keys. An origin
inside the loaded range therefore failed lookup and the zhongshu vanished,
even though the persisted note reported one available zone. Earlier frontend
fixtures contained only `YYYY-MM-DD` and did not exercise this boundary.

A synthetic shared fixture now contains both persisted evidence and the exact
backend-projected chart payload. A Python contract test compares the stored
observation with `project_persisted_chan()`; the frontend consumes that same
payload. This is synthetic test evidence, not a claim of production access or
real-market qualification. The first 23-case frontend run on unchanged runtime
code reproduced **8 failures / 15 passes**, including the missing persisted zone.

The adapter now validates a supplied calendar-day key consistently for box
origin, end, confirmation, and candle lookup. Date-only, space timestamps and
ISO-T timestamps use the date written in the source, including offset-bearing
strings; the browser does not shift source dates into UTC or another day. The
actual coordinate is taken from an existing candle through the unchanged
`projectBars()` projection. Missing trading days are not invented or snapped to
nearby candles. Invalid Gregorian dates/times and missing endpoints are omitted.
Visible bounds and confirmation splits are clipped to available candle bounds,
so a future confirmation does not extend a candidate beyond the loaded range.
No financial prices or indicators are recomputed.

## Verification

Author-run in the isolated dot cloud checkout (Python 3.12.14, Node 24.19.0):

- 29 new frontend projection/boundary cases: PASS. Coverage includes exact
  backend payload, date-only/space/ISO-T forms, explicit offsets crossing UTC
  midnight without source-day conversion, matching timestamped candles, viewport
  clipping, before/after bounds, same-day/reversed spans, invalid calendar/time
  input, leap day, missing bars, empty chart, and pre/post-window confirmation.
- Complete Vue suite: **102 passed in 19 files**; typecheck and production
  frontend build: PASS. Existing build/router warnings are unchanged.
- Explicit `TZ=America/New_York` projection + existing chart suite:
  **41 passed**; coordinates remain those of the supplied candles.
- Backend projection contract (without bootstrap-dependent route): **5 passed**.
  The fixture read explicitly uses UTF-8 for Windows portability.
- Complete final backend suite: **1495 collected, 1484 passed, 11 existing
  skips, zero failures/errors**, exit 0, 556.370 seconds (JUnit). The
  first recovered aggregate is retained as a failed clock-sensitive test
  baseline below; it is not relabelled PASS.
- 27 legacy browser-JavaScript tests, JavaScript syntax, Python compileall,
  scoped Ruff, committed-secret scan, and diff whitespace: PASS.
- Browser test discovery: PASS for the new regression and the existing daily
  box regression. New test checks actual KLineCharts canvas rectangle drawing,
  repeated CHAN off/on toggles, and a narrow viewport, rather than trusting only
  the explanatory text.
- **Cloud browser assertions NOT RUN:** the installed Chromium process aborted
  before navigation with `socket() failed: Operation not permitted`, including
  an approved outside-sandbox retry. No browser success or screenshot acceptance
  is claimed. The committed regression must pass the existing hosted
  `workspace-ci` Chromium gate on the exact publication commit.
- Independent recovery review: PASS with no blocking findings. Reviewer
  independently passed 44 focused frontend cases (29 new, 12 adapter, 3 layer),
  41 New York timezone cases, five backend projection contracts, TypeScript,
  Playwright discovery and diff whitespace. Runtime and test hashes matched
  the previously reviewed patch. The new browser assertion was checked against
  pinned KLineCharts 9.8.12: the matching Chan fill is set before rectangle
  construction and fill. It is not a substitute for actual hosted execution.
- Exact-commit hosted CI: PENDING.

The Windows-only bound project-hub reporter and local root-doc synchronization
remain pending an available local executor. This cloud batch does not claim a
hub update, Windows/phone acceptance, or production acceptance.

## Recovered validation identity

The prior complete-backend log ended without a terminal result or JUnit; it is
not counted as PASS. Recovery reruns use the same runtime/tests, after preserving
the concurrent documentation commit. Full Vue/typecheck/build, the 41-case
timezone suite, 27 legacy JavaScript cases and scoped static checks were rerun
successfully. No runtime edit was made during recovery.

Frozen SHA-256s:

- `frontend/src/lib/chartAdapter.ts`: `d1cbf6da048422e6f362984d212ad61a8887c41353d01861744aeaa9f49bb8ae`
- `frontend/tests/chan-projection.test.ts`: `c74c32bc35006f402797c138b9782ce124a7433f6d1827b4a392ff60f469273b`
- `frontend/e2e/chan-projection.spec.ts`: `c57571e6aa52d46b02448412bb108bdb83a5cd8c00c0c92e23ad32a401cb5cde`
- `backend/tests/fixtures/chan_chart_projection.json`: `4f80a626c95ac020cc779169317efe935a032d505cd35d4e212ef5b81e002952`
- `backend/tests/test_chan_chart_overlay.py`: `cda72d9409b5158705358d2fed8e37f4a27c4dc3003e3f132c91a9e16007f709`


## Pre-existing ownership-test clock boundary

The recovered aggregate completed 1494 cases with **1482 passed, 11 existing
skips and one failure** in 558.28 seconds. The failure was in unchanged
`test_shared_signal_refresh_is_independent_of_every_users_holdings`, not the Chan
adapter or projection. Between two signal refreshes, `theme_score` changed by
0.01 while ownership-independent hashes/weights were otherwise unchanged.
The existing `SignalService` evaluates news decay at `datetime.now()` for each
refresh. A full-evidence equality test must compare the same news age to isolate
the effect of changing user holdings.

A deterministic seed shows the existing behavior without any holdings: a news
item aged 32h4m35s with impact 1.0 yields 73.31, then 73.30 ten seconds later,
with exactly the same evidence title. The test-only correction wraps the original
`_news_theme_score` on the one tested service instance, fixing its evaluation time
while still calling its actual query and calculation. It does not cache or stub
the score, and all original equality assertions remain. Real snapshot creation
timestamps remain unique. An intermediate whole-service clock-freeze attempt
hit the existing snapshot uniqueness constraint and was discarded before the
final validation; no schema or production behavior was changed.

The ownership module passed **23 tests** after stabilization, followed by the
final ownership/boundary pair passing again. Independent review approved the
final test-only diff and independently reproduced the exact boundary through
in-memory SQLite with a datetime round-trip. Scoped Ruff and whitespace passed.
No financial formula, news-decay policy, runtime service, threshold, PIT rule,
qualification or version was changed.

Final test SHA-256:
`backend/tests/test_multi_user_ownership.py`:
`ebe11fb729059d81383b3f9b73d29ca10b77b03e53eeca4558849479c5fc6b7e`.

## Final local aggregate

The reviewed runtime and final test hash above passed the complete suite:
**1495 collected / 1484 passed / 11 existing skips / 0 failures / 0 errors**,
exit 0, 556.370 seconds. Final JUnit SHA-256:
`f205768e6f58b5cd6378c77fc8a869928588a2de5e9cb5f94978c59ec1e54824`. This is a local aggregate result; exact-publication
CI and actual hosted browser execution still require their own evidence.
