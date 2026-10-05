# S8-F0-03 public documentation recheck — 2026-10-05

Checked 2026-10-05, approximately 01:36–01:48 UTC (09:36–09:48 Asia/Shanghai). Scope: existing Tushare, FTShare, AKShare/Eastmoney and Sina candidates only. Official public documentation was read; no account, credential, entitlement, market-data API, purchase or production operation was attempted. FTShare's dynamic documentation was verified in the cloud browser after the text fetch returned an empty page.

Status: **DOCS_ONLY; overall feasibility UNKNOWN; real probes NOT_RUN**. Interface existence is not project permission, actual data availability, independent-unit certification or PIT qualification.

## Documented capability matrix

| Candidate | ETF 5m / 15m | Units / adjustment | Time / delay | History | Access / license / public cost |
|---|---|---|---|---|---|
| Tushare etf_mins | Both explicitly supported; 8,000 rows/request | vol: shares; amount: CNY. Endpoint does not document an adjustment parameter/convention | trade_time is labelled trading time; timezone, interval closure, publication/revision timestamps and historical as-of guarantee not specified | Endpoint advertises over 10 years; instrument-specific completeness untested | Separate minute permission. Generic personal historical-minute schedule is CNY 2,000/year; ETF-specific inclusion/project entitlement still unconfirmed |
| FTShare etf_minutes | Server-side multi-minute aggregation includes 5 and 15; do not call this independently proven raw/native bars | volume: fund units; turnover/OHLC: CNY. None/Forward/Backward adjustment | Explicit opening/closing millisecond timestamps; within-trading-day aggregation. Historical endpoint excludes live current-day minutes; documentation says current-day update after 16:30, without an explicit timezone/SLA | Query span at most 3 days, 1–1,000 rows, default 50. Earliest retained date/12-month completeness not stated | Listed in Basic tier. Public pages reviewed give tier placement, not a price or project-specific storage/reuse license |
| AKShare fund_etf_hist_min_em (Eastmoney source) | SDK wrapper explicitly accepts 5 and 15 | '', qfq, hfq supported for these periods. Minute volume/amount units are not specified in this dictionary; do not borrow daily units | Time column without documented timezone, publication time, bar-close or revision guarantee | Described as recent data. The explicit five-trading-day cap applies to 1-minute data; no fixed 5/15 retention guarantee is stated | AKShare describes academic-research use. Package access/open-source code is not an upstream data-storage/commercial license |
| Sina | No authoritative public ETF 5/15 API contract located in this bounded review | Minute units/adjustment unknown. AKShare's separately documented Sina fund wrapper is daily, not a minute contract | Minute timezone, delay, closure and PIT unknown | Unknown | No verified minute tariff or project-use/storage permission; do not infer free or unavailable |

### Official sources for the matrix

- Tushare [ETF historical-minute dictionary](https://tushare.pro/document/2?doc_id=387), directly read on the check date.
- FTShare [ETF historical minutes](https://market.ft.tech/gateway/doc/p/oj78iq7k), directly observed in the public browser. It documents `GET /api/v2/market/data/etf_minutes`, ETF-only scope and short exchange suffixes.
- AKShare [ETF intraday dictionary](https://akshare.akfamily.xyz/data/fund/fund_public.html), section headed ETF基金分时行情-东财 / fund_etf_hist_min_em. The same [public-fund page](https://akshare.akfamily.xyz/data/fund/fund_public.html) describes fund_etf_hist_sina as daily; this is AKShare's wrapper documentation, not a Sina minute-data license.
- AKShare [project overview and use warning](https://akshare.akfamily.xyz/introduction.html), directly read; its visible document update date is 2026-09-30.

## Keep historical and real-time services separate

Tushare publishes separate [ETF real-time minutes](https://tushare.pro/document/2?doc_id=416) and [day-cumulative real-time minutes](https://tushare.pro/document/2?doc_id=470) endpoints. Their docs include 5MIN/15MIN and shares/CNY, but no project permission or latency/PIT guarantee was verified. The generic [minute guide](https://tushare.pro/document/1?doc_id=234) describes historical-minute processing after the close, around 17:00–21:00; do not treat that as an ETF real-time SLA or an explicit timezone statement.

FTShare's [ETF real-time-minute page](https://market.ft.tech/gateway/doc/p/rytblp5v) is **Professional tier**, current-day **one-minute only**, at most 20 symbols. It does not accept a requested period, date range or adjustment option. It names opening/closing millisecond timestamps and CNY turnover, but its volume field has no unit declaration on this page. Do not transfer the historical endpoint's units or 5/15 capability to it. A causal 1m→5m/15m research aggregation would require a separately frozen contract and sample evidence; none was implemented or run here.

## Cost and permission evidence

Tushare's [permission table](https://tushare.pro/document/1?doc_id=290) separates minute access from points. Its generic historical-minute row lists CNY 2,000/year for individuals, 500 calls/minute and 8,000 rows/call; the real-time-minute row lists CNY 1,000/month. It states institutional prices are ten times individual prices and fees are nonrefundable. These are indicative published rows, not a confirmed ETF-specific quote or account entitlement. No subscription was selected.

The [Tushare data-service agreement](https://tushare.pro/document/1?doc_id=405), II(B), describes a personal, non-transferable, noncommercial, revocable and time-limited license, and forbids account sharing. The reviewed text does not establish a specific grant for this project's cloud persistence, derivative snapshots, redistribution or PIT archive. The [user agreement](https://tushare.pro/document/1?doc_id=409) also restricts third-party account use and does not guarantee service/data quality. This is a factual contract-summary for engineering intake, not a legal conclusion or acceptance of terms.

FTShare's [four-tier interface table](https://market.ft.tech/gateway/doc/p/pb8eizu3) places historical ETF minutes in Basic and real-time ETF minutes in Professional. The reviewed public [product page](https://ftai.chat/ftshare) and table expose no monetary price or clear cloud-storage/redistribution/PIT license. The product page had login/subscription controls; they were not used. Cost and project permission remain UNKNOWN, rather than being inferred from tier names.

## Repository versus upstream

At local source `a2eb45320668d6888890fcef81233f88fba7f46f`:

- TushareProvider.fetch_minute_bars still permits only 30m/60m; 5m/15m fails before transport. Upstream documentation support does not silently enable this path.
- FTShare's repository adapter retains bounded daily/quote routes and has no minute override. The newly verified v2/v4 documentation is **not** evidence that those endpoints were called or that the adapter has migrated.
- AKShare and Sina adapters have no corresponding minute override in the inspected files. SDK/upstream capability and project implementation remain distinct.
- The frozen F0 pair/window and request budget remain unchanged. Existing offline fixtures do not establish real samples.

## Decision boundary and next evidence

The principal new evidence is FTShare's exact historical/realtime split and its historical quantity/open-close dictionary, plus AKShare's explicit 5/15 wrapper and adjustment support. Tushare's previously recorded endpoint/cost/license findings were rechecked, not relabelled a new access result.

Before any separately authorized bounded real probe, confirm the chosen account's exact endpoint entitlement and project storage/reuse permission. Then validate the frozen pair/window, actual period completeness, independent units, calendar/timezone/bar-boundary semantics, publication/revision evidence and delayed/live separation through the Adapter. No FEASIBLE conclusion, runtime activation, calibration upgrade or actionable signal follows from this documentation review.
