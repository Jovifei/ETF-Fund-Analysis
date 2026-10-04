# Backtest credibility and crosscheck audit — 2026-10-04

Branch: `codex/post-release-indicator-audit-20261004`
Stage base: `80425bd6ff52099bab21f7a656398530fbbc6023`
Production remains frozen at `efc0898dd13d386b8b4d91854323e36ceffa0630`.

This is a post-release research-audit stage. It does not deploy, does not promote strategy/model qualification, and does not claim provider/PIT entitlement.

## Confirmed defects fixed

### 1. Unknown quantity was converted to zero in the backtest input

`RotationBacktestService._load_frames()` converted missing volume/amount to `0.0`. The v0.5 research engine then used those zeros in CMF/MFI, volume ratio, VWAP and pullback logic. Unknown quantity is now preserved as NaN and the report records quantity-missing warnings.

The v0.5 flow/structure layer now keeps price-only structure available while returning NaN for quantity-dependent evidence whose required window contains unknown volume/amount. Amount ratio no longer falls back to volume ratio.

### 2. Missing factor evidence was silently ranked as the bottom percentile

The common percentile helper previously used `.fillna(0.0)`. Missing research evidence is now preserved as NaN. A positively weighted missing factor therefore makes the candidate score unavailable instead of inventing a worst-rank observation.

Ablation variants now sum only factors with positive weight. A deliberately zero-weight quantity factor cannot poison a price-only ablation through `NaN * 0`.

The v0.5 absolute-momentum gate is returned to price-only momentum. CMF remains an explicit volume-flow factor rather than a hidden gate that survives even when the volume-flow factor weight is zero.

### 3. Independent crosscheck execution semantics did not match the primary engine

The second engine previously:
- extracted related symbols from the wrong `selection` shape instead of `target_weights`/trades;
- did not guarantee liquidation of positions removed from the target portfolio;
- used positive slippage for sells as well as buys;
- sized at a same-day close-valued portfolio before an open execution;
- recorded post-trade cash against pre-trade market value.

It now independently replays the primary contract:
- decision at close T, execution at open T+1;
- open-equity sizing;
- removed target positions are sold;
- buy execution uses `open*(1+slippage)`, sell execution uses `open*(1-slippage)`;
- commission/minimum commission/lot constraints are independently applied;
- the post-trade portfolio is revalued at that execution day's close.

The crosscheck now compares final equity, the maximum daily equity-curve difference, trade count, total commission and inferred total slippage. The deterministic mock replay test must return `status=pass`; tests no longer accept either pass or fail.

### 4. Report identity/governance

Crosscheck selects the latest appended rotation report by artifact ID rather than semantic timestamp, re-hashes the primary report before replay, and refuses to substitute current configuration when the report's configuration is absent.

Primary reports now bind `backtest_version`. Ablation and crosscheck receipts carry the same execution-version identity.

Mock detection accepts namespaced mock sources instead of only an exact string equal to `mock`.

## PIT and qualification boundary

The backtest proves only calendar causality: features use rows with trade dates at or before close T and trades execute at open T+1. The persisted DailyBar model does not prove that every historical correction/publication was actually available at that historical time.

Reports therefore state:
- `future_trade_dates_in_features=false`
- `point_in_time_revision_qualified=false`
- `qualification=UNKNOWN`

Commission, minimum commission and slippage settings are recorded in the audit payload. This remains an unsealed research backtest, not a claim of deployable or statistically qualified strategy returns.

## Version isolation

Backtest execution/validity semantics advance to:

`rotation-v0.5.2-validity-crosscheck`

Old reports remain historical evidence; they are not relabelled as results from this engine.

## Acceptance scope

Local acceptance should run:
- `backend/tests/test_backtest.py`
- `backend/tests/test_backtest_crosscheck.py`
- `backend/tests/test_backtest_credibility_contract.py`
- the v0.5/task pipeline regressions;
- the current maturity/OBV/input-validity suites;
- compileall.

Exact hosted full CI must prove the independent replay, image build/smoke and database contracts. No deployment is implied by passing this stage.
