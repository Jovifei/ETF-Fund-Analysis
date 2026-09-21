# Freshness recovery

Production inspection: 35 quotes were ingested at 13:08, but only 31 instruments
completed indicator/forecast refresh. Long settled-history retries ran during
the session, taking about eight minutes and delaying quote/board publication.

Provider selection checked raw split gaps before the research corporate-action
view, rejecting complete Tencent batches in favour of price-only fallback.
Selection now validates the same evidence-adjusted view used by computations;
returned and persisted OHLC remain raw.

Three additional official actions explain the remaining historical gaps:

- 512800: record 2025-07-04, first adjusted trading day 2025-07-07, 1:2.
  https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-07-07/512800_20250707_PJ9L.pdf
- 515220: record 2024-04-11, first adjusted trading day 2024-04-12, 1:2.
  https://www.sse.com.cn/disclosure/fund/announcement/c/new/2024-04-12/515220_20240412_5CZN.pdf
- 512200: record 2024-08-09, ex-date 2024-08-12, each old unit becomes 0.35806260 units.
  https://www.sse.com.cn/disclosure/fund/announcement/c/new/2024-08-06/512200_20240806_RYUS.pdf

Historical repair is deferred from 09:15 through 15:15 so quote and board work
can keep its configured cadence. Daily indicators still target the last settled
session; their date is not meant to equal today's live quote date before close.

Qualification of 140 sampled rows never certified the entire historical range.
Source timestamp qualification and forecast calibration remain independent.
