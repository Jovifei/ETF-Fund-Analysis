# Offline Mock settled-date repair — 2026-10-11

Local authorized fix; no provider credentials, production reads/writes, commits or deployment.

The pre-change actual MarketService on isolated SQLite, frozen Sunday test clock, returned failed with target 2026-10-11 while bars ended Friday. Six initial regressions failed before the explicit override API existed.

Optional mock_settled_date is accepted only for market_provider=mock, an exact date object, a verified trading session and a date <= settled_session(actual current time). Future, non-session, unverified and real-provider overrides raise ValueError before ingestion. None preserves existing Mock behavior and real-provider settled-date behavior. Coverage admission is unchanged; failed/partial results are never relabelled success.

TaskService._execute forwards only an explicitly supplied override. Offline compute_local derives settled_session and requests that Mock ingestion target. Computation/capture clocks remain actual current time; no timestamp backdating. Collector order and fail-closed early stop remain unchanged. Parent retains the prior failed receipt.

Final scoped Python 3.12 tests: 8 passed (7 Mock/date/TaskService tests plus collector ordering/kwargs spy). Actual SQLite Sunday default still fails, explicit verified Friday produces succeeded/full coverage and latest bar Friday. New fixture-only forwarding test corrected its initial dispatcher-name/setup error before final pass. Scoped new-test Ruff, changed-module compilation and whitespace check PASS. Full suite and CLI operational rerun remain parent gates.
