# S8-F0 Source Evidence Matrix v3 — 2026-10-02

Status: UNKNOWN / EVIDENCE_COLLECTION

This matrix separates repository implementation from upstream capability. Adapter existence is not permission, data quality, or qualification evidence.

| Source | Official reference | Access date | Repository evidence | Scope finding | Unit/time finding | Access conclusion |
|---|---|---|---|---|---|---|
| Tushare Pro | https://tushare.pro/document/2 | 2026-10-02 | `backend/app/providers/tushare.py` exists. `fetch_minute_bars` currently accepts only `30m`/`60m`; 5m/15m rejects before transport. | Repository does not prove upstream lack of 5m/15m. Adapter implementation gap identified. | Daily contract has explicit volume/amount normalization; minute 5m/15m unit evidence pending. | UNKNOWN / adapter gap |
| FTShare | Pending official endpoint/license citation | 2026-10-02 | `backend/app/providers/ftshare.py` exists with bounded HTTP adapter and pinned endpoints. | Endpoint capability requires upstream scope verification. | Adapter validates source timestamps/fields; no 5m/15m qualification. | UNKNOWN |
| AKShare | https://akshare.akfamily.xyz/ | 2026-10-02 | `backend/app/providers/akshare.py` exists. | Package presence does not prove upstream minute rights. | Source-specific unit verification remains required. | UNKNOWN |
| Sina | Pending official source citation | 2026-10-02 | `backend/app/providers/sina.py` is bounded quote adapter. | Quote capability is not minute OHLCV qualification. | Quantity units remain unverified unless documented. | UNKNOWN |

## Frozen probe contract

Targets:
- 510300.SH
- second ETF selected before receipt

Window:
- 20 trading days connectivity/evidence check only

Frequencies:
- native 5m
- native 15m
- causal 5m->15m only when explicitly supported

Limits:
- isolated environment
- max 20 requests/source
- 10s timeout/request
- stop on permission rejection, schema failure, or repeated upstream failure

Never:
- read tokens
- copy credentials
- write production
- enable runtime providers
- promote qualification

Required receipt:
- official URL/date
- endpoint
- access condition
- field dictionary
- volume unit
- amount unit
- source/fetch timestamps
- history/PIT/adjustment
- license/storage limits
- probe result

Conclusion remains UNKNOWN until evidence is complete.
