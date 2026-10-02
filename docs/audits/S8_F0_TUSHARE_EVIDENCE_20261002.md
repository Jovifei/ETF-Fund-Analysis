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


## Cloud documentation recheck — 2026-10-03 Asia/Shanghai

Read-only official pages were rechecked at 2026-10-02 16:01 UTC. No authenticated API, account permission, order, credential, or real-market sample was accessed.

- [ETF endpoint dictionary](https://tushare.pro/document/2?doc_id=387): confirms native 5m/15m, an 8,000-row limit, documented volume in shares and amount in CNY. `trade_time` still establishes only a trading-time field; no publication timestamp, revision identifier, historical as-of query or explicit bar-boundary guarantee appears in that endpoint schema.
- [Linked permission table](https://tushare.pro/document/1?doc_id=290): minute permissions are independent of the points system. The general historical-minute row lists CNY 2,000/year for personal users and 500 calls/minute, up to 8,000 rows/call; the page says fees are not refundable. **This is a public indicative schedule, not a confirmed ETF-specific entitlement or project quote.** Verify `etf_mins` inclusion and current eligibility before any purchase. No budget or purchase is approved by this receipt.
- [Data-service agreement](https://tushare.pro/document/1?doc_id=405), section II(B): describes a personal, non-transferable, noncommercial, revocable, time-limited license and prohibits account sharing. The reviewed text does not supply an explicit project-specific grant for cloud persistence, derivative snapshots, redistributing samples or PIT archives. **No legal/storage permission is inferred.** Confirm those specific uses through an authorized account/provider channel before real sample persistence.
- [User agreement](https://tushare.pro/document/1?doc_id=409), section V: disclaims guarantees of timeliness, accuracy, completeness and uninterrupted service. This is a documented service risk, not evidence that any particular sample is bad.

The engineering result is bounded offline preparation only. The economic/license decision remains open; F0 overall conclusion stays UNKNOWN. A prospective paid tier does not justify upgrading to FEASIBLE or CONDITIONAL without checking project permission and actual evidence.
