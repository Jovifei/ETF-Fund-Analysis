# S8-F0 Tushare evidence record — 2026-10-02

Status: UNKNOWN / EVIDENCE_COLLECTION

This record separates upstream capability, repository adapter capability, and this project's permission/qualification. No permission is assumed.

## Official references reviewed

| Item | Reference | Access date | Scope recorded |
|---|---|---|---|
| Tushare API documentation | https://tushare.pro/document/2 | 2026-10-02 | Official API documentation entry; exact endpoint field evidence still requires endpoint-level verification |
| Tushare etf_mins capability | endpoint referenced by repository adapter | 2026-10-02 | Repository calls etf_mins; account permission and ETF minute availability remain unverified |

## Repository evidence

`backend/app/providers/tushare.py` currently implements `fetch_minute_bars`.

Observed adapter boundary:

- supported intervals in current code: 30m, 60m
- 5m and 15m requests fail before transport
- this is an implementation capability gap, not evidence that upstream data does not exist

## Missing upstream evidence

Not yet verified:

- native ETF 5m support
- native ETF 15m support
- exact `vol` unit for minute endpoint
- exact `amount` unit for minute endpoint
- `trade_time` close/open interval semantics
- historical retention
- PIT/revision behavior
- storage/reuse license
- account permission required for this project

## Unit separation

Do not reuse daily contract evidence:

- daily fund_daily volume/amount units are separate from minute bars
- minute unit evidence must come from minute endpoint dictionary or trusted upstream documentation

## Conclusion

Tushare minute feasibility: UNKNOWN.

No procurement, credential access, provider enablement, production write, or qualification promotion performed.
