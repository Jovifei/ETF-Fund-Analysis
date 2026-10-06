# S4-U08 support/resistance direction display compatibility

## Accepted baseline and bounded defect

Remote baseline: `8c7f34209726862451b6a5379669b35cf134c593`, tree `6f604eb9fe3ef1ece3fe6cf71d1550034c10dcc6`, on the existing `codex/post-release-indicator-audit-20261004` branch. Its three exact workflows passed before this batch. The preceding classification and public-minute-documentation batches remain accepted separately in [their publication receipt](ORIGINAL_BRANCH_PUBLICATION_CLOSURE_20261005.md).

`SupportLevel` permits the canonical `kind` and compatibility `type` fields. The chart adapter used `kind ?? type`, while the legend and evidence text used only `kind`. A `type: support` level therefore drew a green support line but was labelled resistance below the same chart. Both paths also treated unknown input as a definite side: unrecognized values fell into resistance, while strings containing `support` could become support.

Before changing runtime code, 17 new targeted cases produced **11 failures / 6 passes**. The failing type-only support and expanded-dialog cases showed the exact incorrect resistance label. Unknown and substring cases separately reproduced unsafe directional labelling. No current production payload or live account was inspected; this is a reproducible supported-input defect, not a claim about its production frequency.

## Shared display contract

- `levelDirection` is the one parser used by canvas overlays, the price legend and evidence text. It recognizes the exact values `support` and `resistance`; all other values are `unknown`.
- Null/undefined `kind` is absent and may use `type`. An explicitly present empty, invalid or unknown `kind` does not borrow a definite direction from `type`. A recognized `kind` wins any conflict.
- `levelDirectionLabel` provides the same text at all three surfaces. Unknown is labelled `方向未知`, uses neutral canvas color `#94a3b8`, and does not acquire the legend's directional bull/bear classes.
- Unknown direction retains the original numeric price and zone geometry. It does not infer direction from whether price is above or below the last close.
- Existing snapshot/price-basis gates, raw/research selection, groups, nearest-price sorting, 12-level cap, prices, source methods and evidence remain unchanged.

Only display interpretation changes. No support/resistance calculation, pivot/indicator formula, clustering tolerance, versioned strategy, backend contract, persisted snapshot, data refresh or qualification is modified. There is no schema or dependency change.

## Verification at the frozen source

- New component/adapter integration suite: **18/18 passed**. Includes canonical values, type-only values, both conflict directions, nullish fallback, invalid/unknown/substrings, unchanged zone prices, blocked drawing, raw→research→raw and expanded-dialog layer toggles.
- Complete frontend suite: **190/190 passed in 23 files**. Actual TypeScript check and production build passed.
- Independent reviewer: no blocking issue; **54/54 passed in 7 files**, actual typecheck and diff check passed. Runtime numeric/grouping/qualification behavior was inspected and remains unchanged.
- Related backend support/resistance, zone and chart-research regressions: **14/14 passed**. Python compilation and legacy app.js syntax passed. A complete backend run is not claimed from these focused cases; the exact-commit hosted workflow supplies that separate gate.
- Current cloud Chromium: **2/2 real-browser cases passed**, at 1440px and 390px, using isolated mock data. Cases cover compact-chart entry, one expanded dialog, support/type compatibility, field precedence, explicit unknown, hide/show, Escape and scroll unlock.
- Both local evidence screenshots were visually inspected: all three direction labels and exact prices are readable without clipping. These are evidence-card screenshots, not a pixel-level proof of every canvas line. Canvas values/colors/geometry are checked through the real adapter with mocked KLineCharts in the integration suite.

The extra raw/research regression uses the real EtfChart and ChartAdapter and mocks only KLineCharts. It is more specific than the older chart-basis test's adapter mock. Browser fixtures do not establish real-data, PIT or production acceptance.

## Reproducibility identities

SHA-256:

- `frontend/src/lib/format.ts`: `9cc97cd02c4313d452b3a639ce4e3ff34ddfd7043cdcdad3a901914853e7bdd0`
- `frontend/src/lib/chartAdapter.ts`: `b660c619e8caf2ce109b0d512f7a84d8d2a495a50b6f025044b4caf06b9d77a8`
- `frontend/src/components/EtfChart.vue`: `ef5542c6d34bc6fbdef4d33187b5214872158bd14638a8fb8af3b51494217dba`
- `frontend/tests/chart-level-direction.test.ts`: `bad5dfe2c4b0e21325fcb4a0d43d3e3dd4b2bd826bc301e5e650ff91ec4c101a`
- `frontend/e2e/chart-level-direction.spec.ts`: `0f7b3943577c2203f7dae64a46e811a83ce9e399e7fb41472bb3ffb868974b97`
- RED JUnit: `86209b9dc57c29c0804937480aed6e37a10897ebe6c6cfc33a901963aee1329d`
- Final targeted JUnit: `2900f712a369a22adf245c9daab7992a60a8858901ebc01280194e74beba2c6a`
- Full frontend JUnit: `9212ecdb30e2c0dbe2348c486c89da06355347b40e9083aeeab729a9a1a91aed`
- Independent JUnit: `e97a0ce3b082bfccf9f84afd61a5062c9b5c273390b71dae2cdb9d5f2f7b8c3b`
- Backend focused JUnit: `341384737a4d49ced1acb1e2e6f8da61f96c8247bb09c6873cd4b28483c21805`
- 1440px evidence screenshot: `53ddd9efe115090c8d8fd4e448bf4a565570bb390ae8af091b09c0fbb836d29a`
- 390px evidence screenshot: `a67d47fc205326f24eadbc2f030e424b818ffb5ffedbbdc4a118d3fbee3cc5ae`

## Publication and remaining gates

The owning commit is found with `git log -1 -- frontend/tests/chart-level-direction.test.ts`; the documentation identity is independently queryable through `git log -1 -- docs/PROJECT_PROGRESS.json`. Publish only by non-forced advancement of the same branch, checking actual remote parent and tree. Hosted CI must be read for that exact remote SHA; neither the baseline's green workflows nor local counts establish the successor's result. Preserve failed/blocked attempts and distinguish local SHA from remote SHA if commit metadata changes.

No merge to main, deployment, provider request, account probe, purchase or production data refresh is part of this batch. Real-data qualification remains UNKNOWN, actionable=false, calibration_status=not_calibrated. Existing normal-user live acceptance and Windows root-doc/hub synchronization remain separate.

## Lesson for later work

A compatible payload must use the same interpretation for chart graphics, labels and evidence. Avoid substring matching for an enumerated financial direction, avoid defaulting unknown to an affirmative side, and test all visual surfaces with the same input. Preserve price values and qualification gates while fixing presentation; do not turn a display repair into a new support/resistance algorithm.
