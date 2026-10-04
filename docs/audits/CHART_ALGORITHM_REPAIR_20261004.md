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


## Local Chromium reception and final dialog correction

Local receipt `dc4a82b` validated exact `29c25d7`: focused backend 138 PASS, Vue 172 PASS, typecheck/build/compileall and 11 Node tests PASS. Real Chromium launched successfully but the six modal entrypoint cases still required correction.

Five shared-Vue entry cases had already opened the dialog and passed real canvas height checks. Their common failure came after pointer pan/click: browser focus could transiently remain outside the explicit dialog tab sequence before the test recorded state. The component now focuses the chart host on pointer interaction while expanded, and the Tab trap also recovers from any outside active element to the first/last visible dialog control. The browser test records containment after each Tab key, which tests the actual focus-trap contract while still rejecting collapsed-details descendants.

The sixth failure was a test-contract error, not a missing iframe overlay. The embedded original decision board intentionally handles `.decision-data-row` with `navigateEtf`, which posts `etf-board:navigate` to the Vue parent; `OriginalDecisionBoard.vue` then routes to `/etf/<code>`. It does not open the legacy `#detailOverlay` inside that embedded frame. Chromium acceptance now follows that real path and then verifies the shared compact-chart dialog. The standalone legacy static shell remains covered by its Node/static contract; no hidden test-only production route was added.


## Iteration 78 full-regression reconciliation

Local acceptance receipt `96957fa` validated exact `ef777ad0`: modal Chromium 6/6 PASS, persisted-fractal Chromium 3/3 PASS, Vue 172 PASS, typecheck/build PASS, focused backend 138 PASS, compileall and Node 11 PASS. The complete backend suite collected 1689 tests and produced 1665 PASS / 23 SKIP / 1 FAIL in 809.386 seconds.

The sole failure was a stale test assertion in `test_postdeploy_board.py` that hardcoded `support-resistance-v4-structure` even though the accepted service contract intentionally advanced to `support-resistance-v5-indicators`. Production backend/config bytes were unchanged between `29c25d7` and `ef777ad0`.

The test now imports the production `METHOD_VERSION` for the current-version assertion instead of duplicating a version literal. A separate regression explicitly mutates a persisted snapshot to the prior v4 identity and requires `SupportResistanceService.latest()` to return None without adding or dirtying ORM state, so old-snapshot rejection is preserved rather than weakened. Existing assertions in the same postdeploy case continue to cover initial GET no-write behavior, confirmed structure boxes, actionable=false, source/input identity, as-of hiding, weekly interval blocking and intraday read semantics.

This commit is test/audit-only; application and configuration bytes remain identical to `ef777ad0`.


## Iteration 79 hosted responsive reconciliation

Exact `fd88fc7` local acceptance passed the affected postdeploy/SR suite (35 PASS) with runtime application/frontend/config bytes unchanged. Hosted `audit-platforms` succeeded. The exact workspace workflow reached its responsive browser step and reported 16 PASS / 2 FAIL; artifact `workspace-evidence-37184595254` (ID `11296946319`, SHA-256 `5cc32d88cc2a97c61ac7c0875b9a9fcaa40d6cc5dd01d20c0d88aa810d5f8353`) preserved the traces and reports.

The first failure was a stale expectation: volume is deliberately opt-in after the chart UX repair, so the responsive indicator test now requires initial `aria-pressed=false`, verifies one click enables it, and a second click returns it to false while the original candle canvas instance and no-write contract remain intact.

The second failure exposed a real interaction ambiguity. A compact-chart drag could be followed by a browser click event, causing the new click-to-enlarge handler to open the dialog before the explicit enlarge button; the test then clicked the button and correctly closed it. The component now distinguishes a simple click from a drag with an 8px pointer-movement threshold. Compact drag/pan stays compact; a simple compact click still opens the dialog; expanded pointer interactions retain focus and never reopen it. The responsive test explicitly requires the dialog to remain absent after the drag before using the enlarge button. This preserves both intended UX invariants instead of weakening either test.


## Iteration 80 Linux CI report-selection repair

Exact `fd88fc7` full CI exposed seven calibration negative-test failures that did not reproduce on local Windows. The failures were not gate regressions: each test received a stale `duplicate`/other result without `gate_results` because `CalibrationService.create_candidate()` selected the latest validation artifact by `as_of_time DESC`.

That ordering is unsafe across the supported SQLite test/runtime contract. `ReportArtifact.as_of_time` is semantic report time and SQLAlchemy's timezone-aware datetime can be stored as a naive SQLite value. A pre-existing application timestamp expressed in Asia/Shanghai can therefore sort eight wall-clock hours ahead of a newly inserted UTC fixture even when the latter was appended later.

Calibration now selects the most recently appended validation artifact by monotonic `ReportArtifact.id DESC`. The test helper uses the same append-order contract. A dedicated regression inserts an older artifact with a deliberately larger wall-clock `as_of_time`, then appends a newer artifact with a smaller UTC-style wall clock; candidate creation must select the later insertion and expose its four-horizon contract. No calibration threshold or negative gate was removed or weakened.


## Next-stage execution: walk-forward evidence identity

The remaining preprocessing audit found no learned scaler or normalization fitted outside a fold in `GlobalModelResearchService`: the optional LightGBM/CatBoost benchmark fits each model directly on that fold's `train_x` and predicts only its `test_x`. No runtime scaler was introduced merely to imitate another framework.

A real audit gap remained in reproducibility. The report recorded fold dates and sample counts but did not content-address the exact rows consumed by each fold, so a later reviewer could not prove which instrument/date/label/feature panel produced a metric. Each fold now records ordered SHA-256 identities for its train and test rows, the lineage column list, and distinct instrument counts. The report also binds strategy config hash and git commit and explicitly states that PIT qualification is false, costs/slippage are not included, this is not a strategy backtest, and qualification remains UNKNOWN. These are evidence fields only; model training, predictions, split boundaries and metrics are unchanged.
