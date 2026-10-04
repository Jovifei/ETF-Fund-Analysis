# Historical classification point-in-time audit — 2026-10-04

Branch: `codex/post-release-indicator-audit-20261004`
Stage base: `a21cb958ca695e0f28f04c9d713f110ada197596`
Production remains frozen at `efc0898dd13d386b8b4d91854323e36ceffa0630`.

This stage audits historical use of current Instrument classification metadata. It does not purchase, infer, or backfill historical theme membership.

## Confirmed historical metadata leak

`Instrument.theme_l1/theme_l2` are current metadata fields. The repository has no effective-dated theme-classification history.

Two historical research paths used these current labels:

1. Factor analysis projected current theme labels onto every historical panel row for theme diagnostics.
2. Transaction backtest enforced `max_per_theme` at every historical rebalance date using each instrument's **current** `theme_l1`.

The second behavior changes historical transaction selection and therefore is a real look-ahead defect.

## Shared classification contract

A new contract is persisted:

`historical-classification-v1-current-metadata-only`

It states:
- current Instrument metadata is the source;
- effective-dated classification history is unavailable;
- theme point-in-time qualification is false;
- benchmark-membership point-in-time qualification is false;
- current labels may be projected over history for diagnostic grouping only;
- historical backtest theme constraints are not applied;
- qualification remains UNKNOWN.

This contract is separate from the survivorship/universe contract. Current membership and current classification are different evidence dimensions and have separate hashes.

## Factor and global research

Factor rows still carry today's `theme_l1/theme_l2` so users can inspect current-category diagnostics, but every `theme_analysis` block declares:

- `classification_basis=current_metadata_projected_over_history`
- `classification_point_in_time_qualified=false`

The panel carries `classification_contract`, and ReportArtifact metadata binds its hash.

Global-model research requires an explicit classification contract from the factor panel and persists the full contract plus its hash. No theme label is added to the numeric model feature templates by this stage.

## Transaction backtest

The configured `max_per_theme` value is retained for transparency, but it is **not applied** to historical selection while effective-dated theme history is unavailable.

Historical candidate selection is now rank/top-N based after the existing score and momentum gates. Current `theme_l1` cannot remove a historical candidate.

The report audit records:
- configured max-per-theme;
- `historical_theme_constraint_applied=false`;
- reason `effective_dated_theme_history_unavailable`;
- the full classification contract.

This removes the current-metadata look-ahead without pretending that historical theme diversification has been proven.

## Independent crosscheck

Crosscheck requires the primary classification-contract version and stores its hash alongside the universe-contract hash. It replays the primary decisions; it does not independently infer historical themes.

## Version isolation

Historical research/backtest semantics advance to:

- factor analysis: `factor-analysis-v0.2.3-classification-contract`
- global model research: `global-model-research-v0.2.3-classification-contract`
- transaction backtest: `rotation-v0.5.5-no-theme-lookahead`

Current signal, indicator and forecast formula versions are not changed by this stage.

## Tests

Regression coverage proves:
- classification metadata is explicitly non-PIT;
- two historical candidates with the same current theme are both eligible even when configured `max_per_theme=1`;
- Factor final panels carry the classification contract;
- Global reports persist/hash the contract;
- Backtest reports disclose the non-applied theme constraint;
- Crosscheck binds the primary classification hash.

## Resource boundary

A real historical-theme constraint would require an independently sourced effective-dated classification dataset. That remains a human/provider/resource decision and is not inferred here.

`REAL_DATA_QUALIFICATION=UNKNOWN`
`actionable=false`
`calibration_status=not_calibrated`


## Iteration 90 full-suite isolation reconciliation

Local concentrated acceptance and exact Linux full CI exposed two fixture-isolation classes plus three fresh-process SignalCenter positives. No production future/stale/PIT gate was relaxed.

- SignalCenter's synthetic helper previously did nothing when bootstrap already owned the same date/current Indicator identity. It now updates that synthetic row's values, scores, input hash and generated time, so the test's intended current evidence actually becomes the latest evidence.
- The mixed-source SignalCenter case removes pre-existing DecisionBoard snapshots before inserting its single-row canonical board. This preserves the original assertion that one instrument uses the board while the rest use SignalGrade fallback; it does not change production source precedence.
- The immutable DecisionBoard snapshot test temporarily mutates a 510300 DailyBar to prove saved payload immutability. It now restores the original close in `finally`, preventing that successful test from committing a corrupted benchmark into the shared suite database.
- v103 history fixtures now select an unused 59xxxx.SH code from the database instead of choosing from a 10,000-code random namespace that can collide in long shared suites.

Business gates remain unchanged: invalid benchmark history still fails the backtest, UNIQUE instrument identity remains enforced, and future/stale snapshots remain fail-closed.
