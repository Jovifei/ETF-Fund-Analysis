# Research price basis and execution-basis audit — 2026-10-04

Branch: `codex/post-release-indicator-audit-20261004`
Stage base: `c460b42de2ed3540fc3e20dbff57c8bf43e0334b`
Production remains frozen at `efc0898dd13d386b8b4d91854323e36ceffa0630`.

This is a post-release code-only credibility stage. It does not deploy, does not purchase/activate providers, and does not promote data/PIT/model qualification.

## Confirmed inconsistency

The formal forecast/indicator/support-resistance paths already use the evidence-bound corporate-action research contract. Factor/global research and transaction backtesting did not use an equally strict price-basis policy.

- Factor analysis read every DailyBar directly and called `price_history_issue` on the raw rows. An official documented split therefore looked like an unexplained discontinuity and the instrument was excluded instead of using the same evidence-adjusted research view as formal forecast.
- Transaction backtest accepted all DailyBar adjustment variants, sorted by date/fetched_at and kept one row per date. Because the database intentionally permits one row per `instrument/date/adjust`, this could silently combine raw, qfq or hfq variants into a single return/execution path.
- Transaction backtest also treated adjusted prices as if they were executable opens, even though commission, minimum commission, round-lot sizing and position-share accounting are defined on actual transaction prices.

## Canonical research history

`canonical_research_history` now provides one shared research-basis selector:

- no rows -> `history_missing`
- mixed adjustment variants -> `ambiguous_price_basis`
- unsupported adjustment -> `unknown_price_basis`
- a single allowed basis is passed through the evidence-bound corporate-action research view
- the resulting series must pass `price_history_issue`
- the result carries source adjustment, stable `price_basis_id`, basis description, and whether an official corporate-action adjustment was applied

Factor analysis now uses this selector. Official split histories can therefore participate in factor/global diagnostics on a stable research basis while mixed bases remain fail-closed. Each panel row carries `price_basis_id` and basis description; report metadata records the analysis version and a hash of the research-input contract. Factor reports remain `qualification=UNKNOWN` and explicitly state that revision/publication PIT is not qualified.

Global-model research inherits the same factor panel and records the full panel research-input contract plus its stable hash.

## Transaction backtest execution basis

The event-driven transaction backtest deliberately does **not** use adjusted research prices as execution prices.

An instrument is excluded when:
- adjustment variants are mixed;
- its only stored basis is not raw `adjust=none`;
- price history itself is invalid/unexplained;
- an official corporate-action event occurs inside the available transaction history, because complete position-share conversion, fractional-share handling and cost-basis accounting are not implemented.

This is intentionally conservative. Research adjustment is valid for factor/return analysis but is not silently substituted for execution accounting.

Backtest quantity fields follow the same unit contract as other shared research:
- mock runs may pass through fixture quantity;
- non-mock runs expose volume/amount only from documented-unit endpoints;
- unknown quantity remains NaN and volume-flow factors fail closed.

The report records:
- `execution_price_basis=raw_unadjusted_no_corporate_action_position_events_v1`
- `quantity_contract`
- excluded instruments and reasons
- `input_hash_policy=single_raw_basis_daily_rows_v2`

The per-frame input hash now includes the adjustment basis as well as OHLC, quantity, source and fetched-at identity.

## Independent crosscheck

The crosscheck only replays raw `adjust=none` bars and requires the primary report to declare the new execution-basis and input-hash policies. It reconstructs quantity using the **primary report's** quantity contract rather than the crosscheck process's current environment.

If the official corporate-action catalog now introduces an in-period position event for a replayed code, the replay fails `primary_execution_basis_changed` rather than pretending the old execution basis is still valid.

The existing same-input hash gate remains: changed historical rows return `primary_inputs_changed`.

## Version isolation

Because research sample inclusion and backtest universe semantics change:

- factor analysis: `factor-analysis-v0.2.1-price-basis`
- global-model research: `global-model-research-v0.2.1-price-basis`
- transaction backtest: `rotation-v0.5.3-price-basis`

Formal forecast/indicator versions are unchanged in this stage because they already used the evidence-bound corporate-action contract.

## Acceptance scope

Local acceptance should run the new price-basis contract tests plus:
- corporate-action contract
- factor/global walk-forward
- backtest, crosscheck and credibility suites
- data/input-validity suites
- compileall

Exact hosted full/workspace/platform CI remains mandatory before any future release recommendation.

Qualification stays `UNKNOWN`; backtests and factor diagnostics remain research-only and non-actionable.
