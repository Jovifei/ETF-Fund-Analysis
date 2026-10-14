# Observed-activity valuation and independent fill-ledger audit — 2026-10-11

## Source boundary

Repository: `Jovifei/ETF-Fund-Analysis`
Branch: `codex/post-release-indicator-audit-20261004`
Stage base: `afdf6c21e7ab71d930ed52123bc260a1f36783f8`
Production/release branch remains frozen at `efc0898dd13d386b8b4d91854323e36ceffa0630`.

This is an independent post-release code-only research audit. It does not query providers, deploy, purchase licensed data, write production state or qualify trading.

## Confirmed defects

### Inactive daily-bar closes still marked portfolio equity

The previous tradability stage introduced a raw-positive-volume activity boolean and refused buy/sell execution without observed activity. However the primary daily equity loop continued marking held shares using the latest raw stored close, regardless of activity. Crosscheck did the same. A zero-/unknown-volume bar with a changed close could thus create an unobserved PnL jump even though the same bar had been rejected for execution.

The primary open-value fallback also selected the most recent prior close without requiring activity. This was inconsistent with the explicit `raw_positive_volume_presence_v1` evidence contract.

### Aggregates alone could pass independent crosscheck

Crosscheck required the number of trades, total fees and slippage within tolerance and final/daily equity drift, but did not compare exact per-fill code/date/side/shares/price. Two different trade ledgers could theoretically share the same aggregate counts and costs. The second engine must validate execution identity, not only aggregate totals.

## Corrected observed-close policy

The primary backtest now uses `last_observed_positive_volume_close_v1` for:
- open equity when execution-day open is not tradable;
- post-trade daily portfolio valuation;
- benchmark total/excess-return marking.

The independent crosscheck implements the same rule separately, without importing primary execution code. The chosen mark is the most recent finite positive close from a row with `trade_activity_observed=true`; zero-/unknown-volume rows cannot reset it.

An existing holding with no observable historical trade-backed price is unpriceable. The primary engine fails closed; crosscheck reports `unpriceable_held_position` rather than manufacturing zero market value or falling back to the cost basis. This does not infer transaction volume units or market impact.

The execution open-price filter also requires a finite positive open.

## Per-fill identity contract

Crosscheck now compares normalized ordered primary and replay fills on:
- execution date;
- instrument code;
- buy/sell side;
- integer share count;
- execution price (6 decimals);
- gross amount and commission (2 decimals).

`trade_ledger_identity_match` is a separate mandatory gate. Limited mismatch details accompany a failure. Existing equity-curve, aggregate commission, total slippage and trade-count checks remain mandatory.

An exact match is intentionally stricter than the previous aggregate-only comparison. Full deterministic replay must remain PASS or the discrepancy must be investigated; do not weaken this gate to force green.

## Version and scope

Backtest identity advances to `rotation-v0.5.8-observed-mark-ledger`. The report embeds `valuation_policy=last_observed_positive_volume_close_v1` and `trade_ledger_reconciliation_required=true` under execution tradability/audit. Crosscheck rejects older reports lacking these contracts; it does not reinterpret them as current.

The daily input-hash policy remains `single_raw_basis_daily_rows_v3-activity`: underlying stored row identity and volume-activity evidence did not change.

Price momentum/regime feature interpretation, point-in-time publication history, participation rate, price-limit execution, queues and impact/capacity models remain **unqualified**. These require separate analysis and/or market evidence. This stage only closes trade-backed valuation and replay identity.

## Acceptance

Local exact-SHA checks:
- `backend/tests/test_backtest_mark_and_ledger_contract.py`;
- `backend/tests/test_backtest.py`;
- `backend/tests/test_backtest_crosscheck.py`;
- `backend/tests/test_backtest_credibility_contract.py`;
- `backend/tests/test_historical_classification_contract.py`;
- `backend/tests/test_universe_survivorship_contract.py`;
- `backend/tests/test_price_basis_research_execution_contract.py`;
- compileall.

Require deterministic crosscheck PASS with `trade_ledger_identity_match=true`. Zero-/unknown-volume closes must not change the trade-backed valuation mark. Missing marks must fail closed. Full exact-SHA CI/workspace/platform results remain separate acceptance gates.

`REAL_DATA_QUALIFICATION=UNKNOWN`
`actionable=false`
`calibration_status=not_calibrated`
