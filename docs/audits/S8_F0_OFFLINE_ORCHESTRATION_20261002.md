# S8-F0 offline orchestration receipt — 2026-10-02

Status: OFFLINE_FIXTURE_VALIDATION_ONLY. Real feasibility, project access, license/storage, units and PIT remain UNKNOWN. No production deployment or qualification promotion.

## Scope and identity

- Working branch: `codex/remote-stage-s8f0-s2-20261002`; starting source `67d1a648efa549b3c52743ce5c839ccc527cfec9`.
- New implementation: `backend/app/providers/f0_minute_probe_runner.py`; tests: `backend/tests/test_f0_minute_probe_runner.py`.
- Executes only injected asynchronous fixture transports. There is no default transport, SDK integration, credential/configuration read, network probe, database write, CLI, scheduler, API registration, or production adapter change.
- This implements the orchestration preparation allowed by the [F0 plan](../planning/S8_F0_DATA_FEASIBILITY_SPIKE.md), [source matrix](S8_F0_SOURCE_MATRIX_20261002.md), and [frozen fixture handoff](../handoffs/S8_F0_FIXTURE_REVIEW_HANDOFF_20261002.md). It does not complete the actual F0 investigation.

## Frozen contract

1. The pair is `510300.SH` and `512480.SH`. Four operations cover native 5m and native 15m for each ETF. There is no caller-controlled target, interval, endpoint or date expansion.
2. Local `exchange-calendars:XSHG` supplies the last 20 sessions strictly before `2026-09-30`. On installed version `4.13.2`, this is `2026-09-01` through `2026-09-29`, excluding weekends and the `2026-09-25` holiday. Missing calendar authority fails closed; no weekday fallback or calendar network request.
3. Caller budget must be an integer from 0 through 20; timeout must be finite and satisfy `0 < seconds <= 10`, with booleans rejected. An attempted call consumes budget even if it fails. Budget is checked before dispatch. The fixed plan normally needs four calls.
4. `asyncio.wait_for` enforces the deadline for the supported asynchronous, cancellation-cooperative fixture transport. This is not a hard sandbox for arbitrary synchronous/event-loop-blocking code. Future real adapters require separate review of their own transport deadlines before use.
5. No retries. Permission rejection, timeout, unavailable capability, schema failure, empty response, oversized response and transport failure stop the source immediately. Caller cancellation propagates.
6. Responses are limited to 8,000 rows per operation, as documented for `etf_mins`. Rows must match identity and existing numeric/OHLC checks. Date-only timestamps, duplicate normalized timestamps and bars outside the selected sessions fail closed. Source ordering may be ascending or descending.
7. Receipts contain only fixed source/reference metadata, normalized timestamps, per-operation elapsed time, validated record counts, sampled/missing trading days, allowlisted failure reasons and explicit unknown qualification fields. Raw rows, arbitrary source metadata and exception text are not serialized. Failed transport has no fetched timestamp; request/completion times are separate. Local fetch time is never publication time.
8. Sample-day presence does not verify intraday bar completeness. Partial-day coverage is explicit. Unit names are documentation-only declarations from the previously reviewed [official endpoint dictionary](https://tushare.pro/document/2?doc_id=387), not verified fixture or actual source units. Values are not converted.
9. Causal 5m→15m remains NOT_RUN because the bar-closure/publication contract is unverified. PIT, adjustment, license/storage, access and feasibility are not inferred from fixture success.

## Verification actually executed

- RED: the new runner tests failed collection because the runner module did not yet exist. No production fixture/network was used.
- GREEN: 58 focused runner/parser/production-boundary tests passed in Python 3.12.14, including failure stops, cancellation, request budget, real async timeout, malformed/nonnumeric inputs, calendar failure, partial coverage, deterministic sanitized receipts and unchanged production 5m/15m rejection.
- Scoped Ruff, Python compileall, browser JavaScript syntax, committed-secret scan and `git diff --check` passed.
- Initial aggregate: 1,486 collected, 1,473 passed, 11 skipped, two failures, zero errors in 1,670.512 seconds. This began before the final timestamp refinements/four added tests and is **not** final-snapshot acceptance. Both failures were independently reproduced as local test-environment omissions: AKShare was absent, and Sina initialization required `socksio` for the cloud proxy. No F0 test failed.
- Installed AKShare 1.19.1 and socksio 1.0.0 from PyPI into the isolated test venv only; no production requirements or provider code changed. All 60 recovery checks passed (58 final F0 tests plus both previously failing provider-construction tests).
- Final aggregate against the stable reviewed F0 code: **1,490 collected, 1,479 passed, 11 skipped, zero failures/errors, exit 0, 1,684.152 seconds**. This used the completed isolated cloud test environment and the exact code/test hashes below. It covers the F0-only candidate on `67d1a64`; any subsequent combined performance candidate needs its own validation. Exact published-commit Actions remain pending.
- Independent read-only review found no blocking findings, reran all 58 focused tests and scoped Ruff, and checked additional denial redaction, timestamp normalization/duplicate detection, failed-fetch timestamp semantics, partial status and strict JSON serialization cases. Reviewed SHA-256: runner `16bbb2ed23eba39f7e8663e328de55fd1616fb5e4a36231194f6e13e86f865c3`; tests `f9761262c76e1a708ecaf0f161002a78958d5193296e5a4beaeb212f0616a2df`.

[The receipt example](S8_F0_OFFLINE_RECEIPT_EXAMPLE_20261002.json) was generated only from synthetic rows: one artificial bar per selected session and an injected fixed clock. Its 0-second timings are deterministic fixture values, not measured upstream latency. It is not a real source sample or intraday completeness record.

The Windows project-hub wrapper and local root-doc synchronization are unavailable in this Linux cloud workspace. Neither was invoked; local synchronization remains pending. Existing production identity, acceptance counters, UNKNOWN real-data state and actionable=false remain unchanged.

## Next gate

Review and verify this exact offline implementation, then confirm a specifically authorized project access path and source storage/license/time contracts before any real probe. A synthetic receipt cannot open F1, promote qualification or authorize runtime enablement.

## Combined candidate verification — 2026-10-03

The unchanged reviewed F0 runner/test hashes were then combined with the
independently reviewed scalar-median performance correction and test transaction
isolation. The complete combined aggregate passed: 1493 collected, 1482 passed,
11 existing skips, 0 failures/errors, exit 0, 569.823 seconds. This is separate
from the F0-only 1490-case run above. See the [combined receipt](CI_PRICE_STRUCTURE_PERFORMANCE_20261003.md)
for exact hashes, parity evidence and the existing CI timeout diagnosis. Exact b799087
full/workspace/audit CI is now SUCCESS; the full CI JUnit independently records
1493 collected, 1482 passed, 11 skipped and zero failures in 651.036 seconds.
See the linked closure receipt for all run/artifact identities. Real probes,
deployment and qualification are unchanged.
