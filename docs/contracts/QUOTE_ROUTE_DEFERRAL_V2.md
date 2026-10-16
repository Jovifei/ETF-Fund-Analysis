# Quote-only degraded-adapter deferral

Routing version: `quote-route-v2-degraded-deferral`.

`MarketProvider.quote_selection_capability` defaults to `unknown`; unknown adapters retain their original candidate order. AKShare explicitly declares `degraded_only`: its current spot adapter always emits `is_realtime=False`, so these observations cannot satisfy the existing composite quote selection predicate. This declaration neither certifies data rights nor promotes timestamp, quantity, or strategy qualification.

Only `fetch_spot_quotes` schedules candidate adapters before declared degraded-only adapters. `self.providers`, catalog, daily history, news, and other operations keep their existing order. Qualified candidates retain their original relative priority. Degraded and daily fallback observations are selected by the original provider index, rather than the changed request order; qualified observations still outrank degraded observations, and degraded observations still outrank daily fallbacks. Missing and duplicate requested-code semantics remain unchanged.

Once qualified coverage is complete, deferred adapters receive no request. Their audit trace is `skipped`, with zero latency/count, no result hash, and an explicit deferral reason. Actual deferred calls preserve their real status/latency/count and carry a public deferral reason. A declared degraded-only adapter that actually returns a selectable qualified quote raises `QuoteCapabilityContractError`; ordinary fallback cannot turn that contradiction into success.

The existing MarketService timestamp checks, closed-session typed evidence, eight-minute fast-publication/replay checks, UNKNOWN qualifications, `actionable=false`, and `not_calibrated` remain independent. No indicator formula, feature, signal threshold, or strategy weight changes, so no strategy formula version changes. The source SHA and this routing version identify the operational request change.

The original f3ab310 composite was executed offline with fixed synthetic provider returns to generate the selection golden values in `test_quote_route_deferral.py`: complete/partial qualified coverage, all-degraded values, daily fallback, empty/error paths, missing symbols, and duplicate requests. Those are contract tests, not live-provider or timing acceptance. Separate real timing and release acceptance remain required.
