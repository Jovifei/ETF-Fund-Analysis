# Current snapshot temporal-causality audit — 2026-10-04

Branch: `codex/post-release-indicator-audit-20261004`
Stage base: `28f677c73943df9f65805692a435591026a05daf`
Production remains frozen at `efc0898dd13d386b8b4d91854323e36ceffa0630`.

This stage extends current snapshot compatibility from identity to read-time causality. It does not delete future/invalid rows; historical audit paths may still inspect them.

## Confirmed temporal defect

The current-snapshot contract verified version/schema/config identity, but a same-version row with a future `as_of_date`, future `generated_at`, future `SignalSnapshot.as_of_time`, or future quote timestamp could still be selected by several current consumers. Preflight could flag some of these conditions while SignalService continued to use the row for research scoring before writing a non-actionable signal.

The shared contract advances to:

`current-snapshot-v3-temporal`

For current reads with an explicit/read-time reference:
- Indicator/Forecast `as_of_date` must not be after the read date.
- Indicator/Forecast `generated_at` must not be after the read time.
- Signal `as_of_time` must not be after the read time and must not be expired.
- Quote source time/fetched time must not be after the read time.

The temporal latest row is still selected first. If that row is from the future, current consumers do not silently fall back to an older row.

## Signal generation

SignalService filters quote, indicator and forecast inputs against the same read-time reference before scoring. A future row therefore enters new SignalSnapshot provenance as unavailable rather than contributing a score while merely reducing actionability.

Preflight's formal forecast availability uses the same temporal compatibility contract.

## Current surfaces

Read-time quote/snapshot filtering is applied to:
- Dashboard;
- SignalGrade;
- ETF 14:30;
- Kline stabilization;
- SignalCenter current indicators/signals;
- Portfolio optimization;
- current forecast helpers and CurrentDecision signal fallback.

Historical SignalCenter curves remain historical mixed-version evidence and are not relabelled current.

## Holding valuation

HoldingService previously used `cost_price` as `latest_price` whenever QuoteSnapshot was absent. That fabricated current market value and PnL from acquisition cost.

Holding valuation now requires a current, non-future QuoteSnapshot. Without one:
- `latest_price=None`
- `market_value=None`
- `pnl=None`
- `pnl_pct=None`
- portfolio current weights are unavailable when any holding is unpriced

The quote compatibility reasons are returned with the holding. Cost remains stored as cost and is never substituted for market price.

## Version isolation

Current signal/read semantics advance to:
- strategy/signal `signal-v0.7.4-temporal-causality`
- signal grade `signal-grade-v0.3.3-temporal-causality`
- signal center `signal-center-v0.3.2-temporal-causality`
- 14:30 workbench `etf-1430-workbench-v0.1.5-temporal-causality`

Indicator/feature/forecast formula identities are unchanged. The strategy config hash change intentionally makes prior indicator/forecast rows current-incompatible until the normal pipeline recomputes them.

## Tests

Regression coverage proves:
- future Indicator/Forecast rows are incompatible despite current version strings;
- future SignalSnapshot is not current;
- future quote is rejected across current surfaces;
- holdings never use cost as current price;
- Signal refresh does not wrap future rows into current provenance;
- 14:30 forecast reader rejects future same-version snapshots.

## Qualification boundary

This is software causality hardening only.

`REAL_DATA_QUALIFICATION=UNKNOWN`
`actionable=false`
`calibration_status=not_calibrated`
