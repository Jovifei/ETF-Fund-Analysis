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


## Local reception round 1 and remote correction

Local acceptance receipt commit `ea6f584` tested exact `7b7748921cd989c2f8128539aafa31a23e70f1c8`: 21 focused tests passed and one existing method-version length regression failed. The receipt also independently demonstrated that changing `boll_std` changed derived Bollinger values while the first repair's SR `config_hash` stayed unchanged.

Remote correction:
- shortened the distinct persisted method identity to `support-resistance-v5-indicators` (32 characters) and checks both existing persisted columns;
- SR `config_hash` now binds support-resistance config, complete indicator config and indicator version; the payload also records indicator config/version hashes. A stale snapshot identity is rejected when either Bollinger/indicator configuration or indicator version changes;
- compact Vue chart surfaces now open the application dialog directly by mouse or keyboard, while interactions inside the already-open dialog are ignored by the opener;
- Legacy `chartCanvas` likewise enlarges on compact-canvas click while keeping the explicit button;
- new Chromium coverage exercises Detail, Overview index, global-search-to-Detail and Legacy entrypoints and records the first real chart canvas/pane height before and after enlargement, including 390x844 and 320px Detail viewports.

Remote tests remain NOT_RUN by design; local Codex owns exact-SHA execution.


## Iteration 77 algorithm hardening

Local receipt `16495ed` reported 116 PASS / 2 FAIL on source `67f0e25`: the full synthetic panel produced 474 rather than 480 OOS rows because the test windows were built from global dates that still included feature rows whose forward labels had not matured; the default-run-id test also inherited a previously persisted validation report and therefore exercised duplicate rather than the intended no-report skip path.

The correction does not weaken either assertion:
- each horizon now builds its four OOS windows from that horizon's dates with actually matured labels, then still enforces the per-sample `label_end_date < test boundary` rule; the complete six-instrument fixture therefore has 480 evaluated rows while sparse instruments remain individually purged;
- no-report UUID behavior is tested with an isolated empty repository stub, while the existing create/idempotence path separately retains duplicate coverage.

Calibration governance is tightened beyond the local failures. Aggregate means can no longer hide a bad formal horizon: each configured horizon has its own instrument/sample/metric gate. Probability-style metrics must be finite and within [0,1]. Empty horizons fail. Obvious mock/fixture/demo/test/synthetic source labels and malformed lineage digests fail. Most importantly, holdout/PIT eligibility is code-controlled: the current `forecast-validation-v0.8-research-only` contract is explicitly non-qualifying and the eligible-contract allowlist is empty. A JSON report cannot promote itself by setting holdout/PIT/calibration flags to true. Qualification therefore remains UNKNOWN and calibration remains blocked.


## Iteration 77 chart interaction hardening

Static review found four interaction defects after the first modal implementation:
- the first-class support/resistance toggle only removed PIVOT while BOX and other SR-derived method groups could remain;
- the custom Tab boundary omitted native `summary` controls and counted controls hidden inside collapsed `details`;
- each chart instance independently saved/restored `body.style.overflow`, so overlapping dialogs could unlock one another;
- Legacy collapse changed CSS geometry without redrawing the canvas at compact dimensions.

The correction makes the SR action own every SR level group (BOX/PIVOT/MA/BOLL/ATR/FIB/DERIVED/MACD/KDJ/RSI) while leaving CHAN independent. Dialog focus calculation includes visible summaries and excludes collapsed-detail descendants. Body locking uses a shared token-counted `modal-scroll-lock` class so the last dialog owns unlock. Legacy expand/collapse redraws on both geometry transitions; overlay close suppresses only the pointless hidden redraw. Browser acceptance now cycles focus repeatedly, rejects hidden-focus states, requires summary participation, and verifies lock release plus compact redraw.


## Next-stage execution: overlapping-label confidence

The supplied forecast audit also showed a separate credibility issue that was not one of the three hard failures: raw nearest-neighbor count can substantially overstate independent evidence when forward label windows overlap. This stage closes that item without changing point forecasts.

`similarity_forecast` now records the raw neighbor count, a conservative maximum count of non-overlapping forward-label windows, the union of future label steps and a label-step overlap ratio. The confidence sample factor uses the non-overlapping count and is capped by the former raw factor, so this change can only reduce or preserve the sample contribution to confidence. Expected return, p_up, weighted neighbors and quantiles are unchanged. A frozen regression reproduces the audit example: 60 consecutive horizon-20 neighbors cover 79 unique future steps but only three non-overlapping label windows.

Because confidence semantics changed, the candidate forecast identity is advanced to `similarity-corridor-v0.7.5-overlap-aware`. Persisted older forecasts remain incompatible through the existing version contract. Calibration remains `not_calibrated`; this diagnostic is not an OOS/PIT qualification.
