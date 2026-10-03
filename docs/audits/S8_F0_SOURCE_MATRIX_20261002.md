# S8-F0 Source Evidence Matrix v4 — 2026-10-03 Asia/Shanghai

Status: UNKNOWN / EVIDENCE_COLLECTION

This matrix separates repository implementation from upstream capability. Adapter existence is not permission, data quality, or qualification evidence.

| Source | Official reference | Access date | Repository evidence | Scope finding | Unit/time finding | Access conclusion |
|---|---|---|---|---|---|---|
| Tushare Pro | https://tushare.pro/document/2?doc_id=387 | 2026-10-03 | Production adapter still accepts only `30m`/`60m`; 5m/15m rejects before transport. Separate offline runner has no real transport. | Native 5m/15m and >10-year history documented; actual access/sample coverage not verified. | Minute dictionary declares volume in shares and amount in CNY; independent sample units, bar closure, publication time and PIT not verified. | UNKNOWN / project access and license unresolved |
| FTShare | Pending official endpoint/license citation | 2026-10-02 | `backend/app/providers/ftshare.py` exists with bounded HTTP adapter and pinned endpoints. | Endpoint capability requires upstream scope verification. | Adapter validates source timestamps/fields; no 5m/15m qualification. | UNKNOWN |
| AKShare | https://akshare.akfamily.xyz/ | 2026-10-02 | `backend/app/providers/akshare.py` exists. | Package presence does not prove upstream minute rights. | Source-specific unit verification remains required. | UNKNOWN |
| Sina | Pending official source citation | 2026-10-02 | `backend/app/providers/sina.py` is bounded quote adapter. | Quote capability is not minute OHLCV qualification. | Quantity units remain unverified unless documented. | UNKNOWN |

## Frozen probe contract

Targets:
- 510300.SH
- 512480.SH, frozen by the existing fixture handoff

Window:
- last 20 verified XSHG sessions strictly before 2026-09-30; connectivity/evidence check only

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

## Offline preparation and current documentary access evidence

[Offline orchestration receipt](S8_F0_OFFLINE_ORCHESTRATION_20261002.md): four fixed native pair/interval operations, maximum 20 attempts, maximum 10-second cooperative asynchronous fixture deadline, no retries and stop on the first capability/permission/timeout/schema/transport failure. Focused tests and independent code review pass; actual probe remains NOT_RUN.

[Official evidence recheck](S8_F0_TUSHARE_EVIDENCE_20261002.md): the linked permission table lists a generic personal historical-minute tier at CNY 2,000/year, separately from points. ETF inclusion and actual project eligibility require confirmation. Service terms do not establish this project's cloud storage/PIT rights. No purchase, account action, agreement acceptance or real provider request was made.
