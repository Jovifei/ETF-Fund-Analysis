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

## Independently verified endpoint documentation (2026-10-02)

Primary source: https://tushare.pro/document/2?doc_id=387 (ETF historical minutes), read directly by local Codex.

The published etf_mins dictionary lists native 1/5/15/30/60 minute frequencies, an8000-row request limit and more than10 years of historical coverage. It defines vol as shares and amount as CNY. trade_time is labelled trading time; this does not establish bar closure, publication time or point-in-time revision guarantees. Project permission, storage/reuse license, actual samples and usable PIT remain unverified. These are documentation-level capabilities, not access or data qualification PASS.

Implication: required frequencies are documented upstream, while current project Adapter disables5m/15m. Overall feasibility remains UNKNOWN until access/license/time/PIT evidence is resolved. Do not repeat a homepage-only capability search or classify this as upstream unsupported.
