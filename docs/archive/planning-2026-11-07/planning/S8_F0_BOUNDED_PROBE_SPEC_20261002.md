# S8-F0 bounded probe specification — 2026-10-02

Status: PREPARED / NOT_RUN

## Frozen sample scope

ETF candidates:

- 510300.SH (broad index ETF)
- 512480.SH (industry ETF)

Window:

- end boundary: 2026-09-30
- previous 20 verifiable trading sessions
- trading-session calendar source must be recorded before execution
- do not substitute 20 natural calendar days

## Frequencies

Required checks:

- native 5m
- native 15m
- optional causal 5m aggregation to 15m if native unavailable

## Transport-only fixture tests

Allowed without credentials:

- fake transport response fixtures
- schema validation
- unit validation
- timestamp parsing validation
- interval routing validation

Not allowed:

- real provider calls without authorized access
- token reads
- environment credential inspection
- production provider enablement

## Probe limits

Per source:

- maximum requests: 20
- timeout: 10 seconds/request
- stop immediately on permission failure
- stop after repeated provider transport failure

## Acceptance fields

Every returned bar candidate must identify:

- symbol
- interval
- OHLC
- volume field and unit
- amount field and unit
- source timestamp
- fetch timestamp
- timezone semantics
- adjustment/PIT contract

## Expected outcomes

- FEASIBLE: all required evidence exists and legal repeatable access is confirmed.
- CONDITIONAL: capability exists but permission/license/history/PIT condition remains unresolved.
- NOT_FEASIBLE_WITHIN_SCOPE: scoped legal investigation fails requirements.
- UNKNOWN: evidence incomplete.

Current expected state: UNKNOWN until evidence collection completes.
