"""Offline orchestration only: all minute responses are synthetic fixtures."""

import asyncio
import json
from datetime import UTC, datetime

import pytest
from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.f0_minute_probe import ProbeSchemaError
from app.providers.f0_minute_probe_runner import build_minute_probe_plan, run_minute_fixture_probe

NOW = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)


def fixture_rows(request):
    return [
        {"ts_code": request.code, "trade_time": f"{day}T10:15:00", "open": 4.0,
         "high": 4.2, "low": 3.9, "close": 4.1, "vol": 100, "amount": 410}
        for day in request.trading_days
    ]


def run(transport, **kwargs):
    return asyncio.run(run_minute_fixture_probe(
        transport=transport, clock=lambda: NOW, monotonic=lambda: 100.0, **kwargs,
    ))


def test_plan_freezes_pair_native_intervals_and_verified_sessions():
    plan = build_minute_probe_plan()
    assert [(item.code, item.interval) for item in plan] == [
        ("510300.SH", "5m"), ("510300.SH", "15m"),
        ("512480.SH", "5m"), ("512480.SH", "15m"),
    ]
    days = plan[0].trading_days
    assert len(days) == len(set(days)) == 20
    assert list(days) == sorted(days)
    assert days[-1].isoformat() == "2026-09-29"
    # Mid-autumn holiday and weekends must not be counted as trading sessions.
    assert "2026-09-25" not in {day.isoformat() for day in days}
    assert all(day.weekday() < 5 for day in days)
    assert all(item.trading_days == days for item in plan)


def test_complete_receipt_is_deterministic_sanitized_and_never_qualified():
    calls = []

    async def transport(request, *, timeout_seconds):
        calls.append((request, timeout_seconds))
        rows = fixture_rows(request)
        rows[0]["private_metadata"] = "must-not-appear"
        return rows

    receipt = run(transport)
    assert receipt == run(transport)
    assert len(calls) == 8
    assert all(timeout == 10 for _, timeout in calls)
    assert receipt["request_count"] == 4
    assert receipt["status"] == "FIXTURE_PLAN_COMPLETE"
    assert receipt["qualification"] == receipt["feasibility"] == receipt["pit"] == "UNKNOWN"
    assert receipt["actionable"] is False
    assert receipt["source"] == "tushare"
    assert receipt["endpoint"] == "etf_mins"
    assert receipt["calendar_source"] == "exchange_calendars:XSHG"
    assert receipt["source_publication_time"] is None
    assert receipt["causal_15m"] == "NOT_RUN_TIME_CONTRACT_UNVERIFIED"
    assert receipt["units"]["status"] == "DOCUMENTATION_ONLY_UNVERIFIED"
    assert "must-not-appear" not in json.dumps(receipt)
    for operation in receipt["operations"]:
        assert operation["status"] == "FIXTURE_SCHEMA_PASS"
        assert operation["record_count"] == 20
        assert operation["observed_trading_days"] == 20
        assert operation["missing_trading_days"] == []
        assert operation["fetched_at"] == NOW.isoformat()
        assert operation["elapsed_seconds"] == 0
        assert operation["source_time_min"].endswith("T10:15:00+08:00")


@pytest.mark.parametrize("budget,expected", [(0, 0), (1, 1), (3, 3), (20, 4)])
def test_request_budget_is_enforced_before_transport(budget, expected):
    calls = []

    async def transport(request, **kwargs):
        calls.append(request)
        return fixture_rows(request)

    receipt = run(transport, request_budget=budget)
    assert receipt["request_count"] == len(calls) == expected
    assert receipt["stop_reason"] == ("REQUEST_BUDGET_EXHAUSTED" if budget < 4 else None)


@pytest.mark.parametrize("options", [
    {"source": "https://example.invalid/?token=private"},
    {"source": []}, {"request_budget": True}, {"request_budget": 21},
    {"request_budget": -1}, {"timeout_seconds": 11},
    {"timeout_seconds": float("nan")}, {"timeout_seconds": True},
])
def test_invalid_configuration_never_invokes_transport(options):
    async def forbidden(*args, **kwargs):
        pytest.fail("invalid configuration reached transport")

    with pytest.raises(ProbeSchemaError):
        run(forbidden, **options)


@pytest.mark.parametrize("error,reason", [
    (PermissionError("raw secret rejection"), "PERMISSION_DENIED"),
    (TimeoutError("raw secret timeout"), "REQUEST_TIMEOUT"),
    (RuntimeError("raw secret upstream"), "TRANSPORT_FAILED"),
    (ProviderError("raw secret", safe_code="PERMISSION_OR_CREDENTIALS_DENIED"), "PERMISSION_DENIED"),
    (CapabilityUnavailable("raw secret"), "CAPABILITY_UNAVAILABLE"),
])
def test_transport_failure_stops_source_and_does_not_echo_exception(error, reason):
    calls = []

    async def transport(request, **kwargs):
        calls.append(request)
        raise error

    receipt = run(transport)
    assert len(calls) == receipt["request_count"] == 1
    assert receipt["stop_reason"] == reason
    assert receipt["operations"][0]["reason"] == reason
    assert receipt["operations"][0]["fetched_at"] is None
    assert receipt["operations"][0]["completed_at"] == NOW.isoformat()
    assert "raw secret" not in json.dumps(receipt)


def test_runner_deadline_cancels_awaitable_and_stops_following_requests():
    calls = []
    cancelled = []

    async def transport(request, **kwargs):
        calls.append(request)
        try:
            await asyncio.sleep(1)
        finally:
            cancelled.append(request)

    receipt = run(transport, timeout_seconds=0.01)
    assert receipt["stop_reason"] == "REQUEST_TIMEOUT"
    assert len(calls) == len(cancelled) == receipt["request_count"] == 1


@pytest.mark.parametrize("bad_payload", [None, {}, "private", [None], ["private"]])
def test_malformed_response_is_sanitized_and_stops(bad_payload):
    calls = []

    async def transport(request, **kwargs):
        calls.append(request)
        return bad_payload

    receipt = run(transport)
    assert len(calls) == 1
    assert receipt["stop_reason"] == "INVALID_RESPONSE_SCHEMA"
    assert "private" not in json.dumps(receipt)


@pytest.mark.parametrize("mutation", [
    {"ts_code": "000001.SZ"}, {"trade_time": "2026-09-30T10:15:00"},
    {"trade_time": "2026-09-25T10:15:00"}, {"trade_time": "2026-09-29"},
    {"close": float("nan")}, {"open": True}, {"vol": -1}, {"amount": 10 ** 400},
])
def test_invalid_rows_reject_entire_operation(mutation):
    async def transport(request, **kwargs):
        rows = fixture_rows(request)
        rows[-1].update(mutation)
        return rows

    receipt = run(transport)
    assert receipt["request_count"] == 1
    assert receipt["stop_reason"] == "INVALID_RESPONSE_SCHEMA"
    assert receipt["operations"][0]["record_count"] == 0


def test_duplicate_timestamp_is_rejected_but_reverse_order_is_allowed():
    async def duplicate(request, **kwargs):
        rows = fixture_rows(request)
        return rows + rows[:1]

    assert run(duplicate)["stop_reason"] == "INVALID_RESPONSE_SCHEMA"

    async def reverse(request, **kwargs):
        return fixture_rows(request)[::-1]

    assert run(reverse)["status"] == "FIXTURE_PLAN_COMPLETE"


def test_empty_response_stops_and_partial_day_coverage_is_visible():
    async def empty(request, **kwargs):
        return []

    receipt = run(empty)
    assert receipt["stop_reason"] == "NO_DATA"
    assert receipt["request_count"] == 1

    async def partial(request, **kwargs):
        return fixture_rows(request)[:-1]

    receipt = run(partial)
    assert receipt["status"] == "FIXTURE_PLAN_PARTIAL"
    assert receipt["operations"][0]["missing_trading_days"] == ["2026-09-29"]
    assert receipt["operations"][0]["status"] == "PARTIAL_FIXTURE_COVERAGE"


def test_row_budget_rejects_before_parsing():
    async def transport(request, **kwargs):
        return [None] * 8001

    receipt = run(transport)
    assert receipt["stop_reason"] == "RESPONSE_TOO_LARGE"
    assert receipt["request_count"] == 1


def test_unverified_calendar_fails_closed_before_transport(monkeypatch):
    import exchange_calendars

    def unavailable(*args, **kwargs):
        raise RuntimeError("private calendar error")

    monkeypatch.setattr(exchange_calendars, "get_calendar", unavailable)

    async def forbidden(*args, **kwargs):
        pytest.fail("calendar fallback reached transport")

    with pytest.raises(ProbeSchemaError, match="f0_verified_calendar_unavailable"):
        run(forbidden)


def test_clock_must_be_timezone_aware_before_transport():
    async def forbidden(*args, **kwargs):
        pytest.fail("invalid clock reached transport")

    with pytest.raises(ProbeSchemaError, match="f0_clock_timezone_required"):
        asyncio.run(run_minute_fixture_probe(transport=forbidden, clock=lambda: datetime(2026, 10, 2)))


def test_caller_cancellation_is_not_swallowed():
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        run(cancelled)
