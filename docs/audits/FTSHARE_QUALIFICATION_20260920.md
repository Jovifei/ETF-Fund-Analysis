# FTShare qualification probe — 2026-09-20

## Scope

Read-only probes only. No runtime configuration, database, account, credential, holding, or production state was changed.

## Observed endpoint state

- Skill `etf-ohlcs`, five-symbol sample: HTTP 404 for every symbol.
- Skill `etf-candlesticks`, same sample: HTTP 405 for every symbol.
- Application `scripts/qualify_ftshare.py`, symbols `510300.SH`, `512000.SH`, `512480.SH`, `515880.SH`, and `588200.SH`: list, daily bars, and spot quotes all returned sanitized `CapabilityUnavailable`, zero records, and exit 1.
- Every report remained `unqualified` with `required_operation_unavailable`, `absolute_units_not_independently_certified`, and `operational_timestamp_not_qualified`.

The sample establishes current unavailability only. It does not prove that every FTShare endpoint is permanently unavailable and does not qualify historical units or realtime timestamps.

## Gate repair

The previous script derived top-level qualification only from three non-empty operations while leaving unit and timestamp findings empty. The repaired qualification requires all three operations plus explicit `independently_certified=true` daily-unit evidence and `operational_grade=true` quote-time evidence. Missing evidence fails closed.

FTShare remains disabled/unqualified in production. The next data-qualification attempt must use a recovered endpoint or another documented independent source and reconcile same-day absolute volume and amount before changing runtime configuration.
