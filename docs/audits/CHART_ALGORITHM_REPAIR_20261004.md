# Chart and algorithm repair audit — 2026-10-04

Branch: `codex/chart-algorithm-repair-20261004`
Base: `a6c2368d490587670f1c5381f03a6b4c5e00ea86`
Runtime baseline audited by the handoff: `425f048ca58af0422837b00110e9f8cfb4a1d7ce`

This receipt records a bounded engineering repair. Remote ChatGPT wrote source and tests through the approved GitHub repository, but did not run the repository test suite. Local Codex must validate the exact pushed SHA. Nothing in this batch promotes real-data qualification, forecast calibration, Chan qualification or actionable status.

## Fixed confirmed defects

| Area | Audit classification | Repair |
| --- | --- | --- |
| RSI 6/12/14 | CONFIRMED_FIXED_PENDING_LOCAL_TEST | One canonical Wilder-style project contract now drives base/v05 frame values, scalars and scoring: mature all-gain=100, all-loss=0, flat=50; warm-up/missing/non-finite current values stay neutral 50. Indicator, feature-schema and forecast versions are bumped so old snapshots fail closed instead of being relabelled. |
| Persisted support/resistance | CONFIRMED_FIXED_PENDING_LOCAL_TEST | The sole explicit persistence compute path enriches its already-frozen research-price frame with the same canonical indicator calculation before the SR builder. MA/BOLL/TD9/MACD/KDJ/RSI contributions can no longer disappear merely because the persistence frame omitted columns. Unknown volume/amount stay missing. METHOD_VERSION is bumped; GET still does not rebuild. |
| Global-model split | CONFIRMED_FIXED_PENDING_LOCAL_TEST | Factor rows now carry instrument-specific `label_end_date_h`. Walk-forward training requires every label end to be strictly before the embargo-adjusted test boundary. Global calendar distance remains diagnostic, not the leakage proof. |
| Forecast validation input | CONFIRMED_FIXED_PENDING_LOCAL_TEST | Validation reuses `ForecastService._frames`, therefore corporate-action research prices, history qualification/truncation, missing quantity and cross-sectional construction share one path. Validation reports bind current config, git identity, horizon contract and input-lineage hash. |
| Calibration governance | CONFIRMED_FIXED_PENDING_LOCAL_TEST | Fixed default UUID call. Candidate provenance comes from the original report rather than current config substitution. Non-finite metrics, missing formal horizons, mock source, absent independent holdout, absent PIT qualification, hash/config/code drift and tampered reports fail closed. Approval rereads and rehashes the original report and recomputes gates. Current validator explicitly reports independent_holdout=false and pit_qualified=false, so it cannot create a false approved calibration. |
| Chart enlargement | CONFIRMED_FIXED_PENDING_LOCAL_BROWSER | Shared Vue chart no longer calls the browser Fullscreen API. It opens an application dialog with Escape, Tab trap, background-scroll lock, focus return and resize. Default auxiliary panes are opt-in (MA only, volume off); support/resistance has a first-class control. Detail, Overview and search-to-detail share this component. Legacy detailOverlay gains an explicit in-modal K-line enlarge control and redraws at the enlarged geometry. |
| Persisted CZSC fractals | CONFIRMED_FIXED_PENDING_LOCAL_TEST | Selectively ported only the reviewed runtime/type/test/fixture pieces from the untrusted intake. Explicit saved `fx` marks are projected only from verified persisted evidence with matching price basis, strict finite geometry and exact source-candle mapping. They render as neutral top/bottom rings, never trading arrows or invented confirmation timestamps. Corrupt/mismatched/fallback evidence cannot leak markers. |

## Definition differences — not silently rewritten

- MA/BOLL/CCI/Williams %R/ROC/MFI comparisons in the supplied audit are consistent enough with the selected reference windows to retain their current project definitions.
- ATR, MACD, ADX/DMI and OBV show initialization or seed differences versus the supplied TA-Lib comparison. They remain **DEFINITION_DIFFERENCE**, not automatically bugs. This repair does not rewrite them.
- KDJ, CMF, RSRS and TD9 remain project-defined algorithms. Their formulas and tests are auditable, but they are not labelled as TA-Lib-equivalent standards.
- `chan_zone_approx`, `chan-structure-simplified-v1`, and persisted CZSC 1.0.1 observations are separate algorithms/evidence classes. This repair does not let one certify another.

## Still unqualified / unknown

- Real ETF 5m/15m entitlement, license/storage, publication-time and PIT guarantees remain UNKNOWN.
- Current forecast validation is not an independent holdout and does not prove PIT qualification. Therefore calibration remains `not_calibrated`.
- Mechanism fixes and synthetic/local regressions do not prove predictive reliability, OOS profitability, statistical validity or trading suitability.
- `actionable=false`; no provider activation, purchase, production deployment, automatic model promotion, broker connection or auto-trading is part of this branch.

## Local exact-SHA acceptance required

Local Codex should receive the exact branch tip into an isolated worktree without touching the owner dirty tree and run at least:

1. focused RSI/SR/time-split/global-model/validation/calibration/Chan-fractal regressions;
2. complete backend `pytest -q`, `compileall backend/app`, required Node/static syntax/tests and progress consistency checks;
3. Vue tests, typecheck and production build;
4. Chromium coverage for the chart dialog on Detail and Overview/search-to-detail, support/resistance toggle, period switching/resize, Escape/focus return/background lock, plus 390×844 and 320px; measure the actual main candle pane rather than only the outer chart container;
5. persisted fractal desktop/narrow rendering and layer-off / unsupported-period disappearance.

Any local failure returns to remote review as a defect on this exact SHA. Do not deploy this repair merely because source was committed.
