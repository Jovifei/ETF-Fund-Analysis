# Backtest execution tradability and capacity boundary audit — 2026-10-05

Branch: `codex/post-release-indicator-audit-20261004`
Stage base: `47794a2cd581b794b592abccbf5da758c012c40b`
Production remains frozen at `efc0898dd13d386b8b4d91854323e36ceffa0630`.

## Confirmed execution defect

The event-driven backtest previously treated any finite positive execution-day open price as tradable. A DailyBar with zero or missing raw volume could therefore receive simulated buys or sells even though the stored row did not prove that any market trading occurred that day.

That is distinct from quantity-unit qualification. The engine does not need to know whether volume is shares, lots or another documented unit merely to establish the minimal boolean fact that a positive trade-activity observation exists.

## Minimal tradability contract

Each canonical raw daily row now stores:

`trade_activity_observed = raw volume is finite and > 0`

This boolean is computed before quantity-unit masking. It does not interpret or scale the volume.

Execution-day open prices are eligible for simulated transactions only when:
- the raw open is finite and positive; and
- `trade_activity_observed=true`.

If activity is false/unknown:
- no buy is executed;
- no sell is executed;
- an existing holding remains held;
- valuation falls back to the most recent prior close rather than pretending the execution-day open was tradable.

The same boolean is independently reconstructed by the crosscheck engine.

## Input identity

`trade_activity_observed` is included in the daily input hash. The input-hash policy advances to:

`single_raw_basis_daily_rows_v3-activity`

Crosscheck rejects primary reports that lack:
- `execution_tradability_contract.policy=raw_positive_volume_presence_v1`; or
- the new input-hash policy.

Thus primary and second-engine replay cannot silently disagree about which dates were executable.

## Explicitly unqualified execution realism

This stage intentionally does **not** invent thresholds for:
- participation rate / percentage of daily volume;
- market impact;
- exchange price-limit execution;
- queue position or partial fills.

Backtest reports explicitly state these are not qualified:

- `participation_cap_qualified=false`
- `market_impact_model_qualified=false`
- `price_limit_execution_qualified=false`

The suspension proxy is only the minimal observed-activity boolean. Passing this gate does not make backtest returns deployable or capacity-qualified.

## Version isolation

Transaction backtest version advances to:

`rotation-v0.5.6-tradability-gate`

Factor/global/indicator/forecast formula versions are unchanged.

## Tests

Regression coverage proves:
- missing raw volume stays distinct from quantity value masking;
- a positive open with no observed activity cannot buy;
- an existing holding cannot be sold on an unobserved-activity day;
- the same row becomes executable when positive raw volume is present;
- full deterministic crosscheck still has to PASS under the new input/tradability contract.

Qualification remains `UNKNOWN`; no provider or real execution model is activated.
