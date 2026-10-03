# S8-F0 Execution Handoff — 2026-10-02

Status: EVIDENCE_COLLECTION_READY

Scope:
- Investigate real 5m/15m OHLCV/amount feasibility only.
- No procurement, account creation, credential access, production writes, schema changes, or qualification promotion.
- Existing S2 deployment remains independent.

## Frozen bounded probe

Universe:
- 510300.SH
- second ETF selected before probe execution with different liquidity profile

Window:
- 20 trading days connectivity/evidence check only.
- Does not prove model validity or data qualification.

Intervals:
- native 5m
- native 15m
- causal 5m to 15m aggregation if source supports it

Probe guard:
- maximum 20 requests per source
- 10 second timeout per request
- stop on permission failure or repeated provider failure
- isolated environment only
- no production database writes

## Decision rules

Conclusion labels require evidence:
- FEASIBLE: legal repeatable access, field/unit/time/history evidence, and constraints documented.
- CONDITIONAL: capability exists but missing budget, permission, history, PIT, or license conditions.
- NOT_FEASIBLE_WITHIN_SCOPE: investigated legal sources do not satisfy scoped requirements.
- UNKNOWN: evidence incomplete; do not force a conclusion.

## Evidence required per source

Record:
- official source/document URL
- access date
- exact endpoint/interface
- free/paid/access requirement
- ETF/frequency scope
- volume unit evidence
- amount unit evidence
- source timestamp vs publish/fetch timestamp
- history coverage and PIT/adjustment contract
- license/storage/repeat access restrictions
- bounded probe receipt and failure reason

## Known official references (capability only, not project permission)

- Tushare: https://tushare.pro/document/2
  - Record only documented API capability and license/access requirements.
  - Do not infer this project has a token, account, quota or entitlement.

- AKShare: https://akshare.akfamily.xyz/
  - Record library/interface capability separately from upstream source permissions.
  - Do not infer all upstream data is licensed for this project use.

## Adapter boundary

Local execution may run existing adapters only after inventory confirms:
- adapter path
- contract mapping
- required access conditions

It must not:
- read credentials
- copy tokens
- inspect secrets
- bypass provider adapters
- write production data
- enable runtime providers
- promote data qualification

## Deliverables

1. source capability matrix
2. bounded probe receipt
3. final F0 conclusion with evidence links

Current conclusion: UNKNOWN until evidence collection completes.
