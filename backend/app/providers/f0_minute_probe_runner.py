"""Bounded, offline F0 orchestration with an explicitly injected fixture transport.

No SDK, credentials, settings, network transport, database, or runtime registration
is provided here. The transport must be an async, cancellation-cooperative fixture
callable. Its timeout argument is also enforced by the runner. This is not a
production adapter or evidence of real access, units, license, PIT or qualification.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from importlib.metadata import version

from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.f0_minute_probe import (
    ASSUMED_TZ,
    ProbeSchemaError,
    parse_minute_fixture,
    validate_probe_limits,
)

FROZEN_CODES = ("510300.SH", "512480.SH")
FROZEN_INTERVALS = ("5m", "15m")
FROZEN_CUTOFF = date(2026, 9, 30)
MAX_ROWS = 8000


@dataclass(frozen=True)
class MinuteProbeRequest:
    code: str
    interval: str
    trading_days: tuple[date, ...]

    @property
    def start_date(self) -> date:
        return self.trading_days[0]

    @property
    def end_date(self) -> date:
        return self.trading_days[-1]


def build_minute_probe_plan() -> tuple[MinuteProbeRequest, ...]:
    """Use only local XSHG sessions; never replace missing calendar with weekdays."""
    try:
        import exchange_calendars

        sessions = exchange_calendars.get_calendar("XSHG").sessions_in_range("2026-08-01", "2026-09-29")
        days = tuple(session.date() for session in sessions[-20:])
        if len(days) != 20 or tuple(sorted(set(days))) != days or any(day >= FROZEN_CUTOFF for day in days):
            raise ValueError
    except Exception:
        raise ProbeSchemaError("f0_verified_calendar_unavailable") from None
    return tuple(MinuteProbeRequest(code, interval, days) for code in FROZEN_CODES for interval in FROZEN_INTERVALS)


def _now(clock: Callable[[], datetime]) -> str:
    observed = clock()
    if not isinstance(observed, datetime) or observed.tzinfo is None or observed.utcoffset() is None:
        raise ProbeSchemaError("f0_clock_timezone_required")
    return observed.astimezone(UTC).isoformat()


def _elapsed(start: float, monotonic: Callable[[], float]) -> float:
    elapsed = monotonic() - start
    if not math.isfinite(elapsed) or elapsed < 0:
        raise ProbeSchemaError("f0_monotonic_clock_invalid")
    return round(elapsed, 6)


def _summarize_rows(rows: object, request: MinuteProbeRequest) -> dict:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ProbeSchemaError("INVALID_RESPONSE_SCHEMA")
    # A calendar date alone must never masquerade as a minute timestamp.
    for row in rows:
        stamp = row.get("trade_time")
        if not isinstance(stamp, datetime) and (not isinstance(stamp, str) or len(stamp) < 16):
            raise ProbeSchemaError("INVALID_RESPONSE_SCHEMA")
    try:
        parsed = parse_minute_fixture(interval=request.interval, expected_code=request.code, rows=rows)
        timestamps = [datetime.fromisoformat(row["trade_time"]).astimezone(ASSUMED_TZ) for row in parsed]
        observed_days = {stamp.date() for stamp in timestamps}
        if len(set(timestamps)) != len(timestamps) or not observed_days.issubset(request.trading_days):
            raise ProbeSchemaError("INVALID_RESPONSE_SCHEMA")
    except (ValueError, TypeError, OverflowError):
        raise ProbeSchemaError("INVALID_RESPONSE_SCHEMA") from None
    missing = sorted(set(request.trading_days) - observed_days)
    return {
        "status": "PARTIAL_FIXTURE_COVERAGE" if missing else "FIXTURE_SCHEMA_PASS",
        "record_count": len(parsed),
        "observed_trading_days": len(observed_days),
        "missing_trading_days": [day.isoformat() for day in missing],
        "source_time_min": min(timestamps).isoformat() if timestamps else None,
        "source_time_max": max(timestamps).isoformat() if timestamps else None,
    }


async def run_minute_fixture_probe(
    *,
    transport: Callable[..., Awaitable[list[dict]]],
    source: str = "tushare",
    request_budget: int = 20,
    timeout_seconds: float = 10,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic: Callable[[], float] = time.monotonic,
) -> dict:
    """Run the fixed four-request fixture plan and return a JSON-safe receipt.

    Each attempted call consumes budget, including failures. No retries are made;
    permission, timeout, schema and transport failures stop this source immediately.
    Only allowlisted metadata, counts and normalized times enter the receipt, never
    raw payloads or exception messages. Sample-day presence is not bar completeness.
    """
    validate_probe_limits(request_count=request_budget, timeout_seconds=timeout_seconds)
    if source != "tushare" or not callable(transport):
        raise ProbeSchemaError("f0_fixture_transport_scope_invalid")
    started_at = _now(clock)
    plan = build_minute_probe_plan()
    receipt = {
        "schema_version": "f0-offline-receipt-v1",
        "mode": "OFFLINE_FIXTURE_ONLY",
        "source": source,
        "endpoint": "etf_mins",
        "operation": "validate_native_minute_fixture",
        "official_reference": "https://tushare.pro/document/2?doc_id=387",
        "documentation_access_date": "2026-10-02",
        "calendar_source": "exchange_calendars:XSHG",
        "calendar_version": version("exchange-calendars"),
        "cutoff_exclusive": FROZEN_CUTOFF.isoformat(),
        "trading_days": [day.isoformat() for day in plan[0].trading_days],
        "started_at": started_at,
        "request_budget": request_budget,
        "timeout_seconds": timeout_seconds,
        "request_count": 0,
        "status": "FIXTURE_PLAN_COMPLETE",
        "stop_reason": None,
        "units": {"volume": "shares", "amount": "CNY", "status": "DOCUMENTATION_ONLY_UNVERIFIED"},
        "time_assumption": "Asia/Shanghai if source omitted timezone; not publication/PIT certification",
        "source_publication_time": None,
        "bar_closure": "UNKNOWN",
        "bar_completeness": "NOT_VERIFIED",
        "causal_15m": "NOT_RUN_TIME_CONTRACT_UNVERIFIED",
        "access": "NOT_PROBED",
        "license_storage": "UNKNOWN",
        "adjustment": "UNKNOWN",
        "pit": "UNKNOWN",
        "qualification": "UNKNOWN",
        "feasibility": "UNKNOWN",
        "actionable": False,
        "operations": [],
    }
    for request in plan:
        if receipt["request_count"] >= request_budget:
            receipt.update(status="STOPPED", stop_reason="REQUEST_BUDGET_EXHAUSTED")
            break
        operation = {
            "code": request.code, "interval": request.interval,
            "start_date": request.start_date.isoformat(), "end_date": request.end_date.isoformat(),
            "requested_at": _now(clock), "fetched_at": None, "record_count": 0,
            "source_time_min": None, "source_time_max": None,
            "status": "BLOCKED", "reason": None,
        }
        start = monotonic()
        if not math.isfinite(start):
            raise ProbeSchemaError("f0_monotonic_clock_invalid")
        receipt["request_count"] += 1
        reason = None
        try:
            rows = await asyncio.wait_for(transport(request, timeout_seconds=timeout_seconds), timeout_seconds)
            operation["fetched_at"] = _now(clock)
            if isinstance(rows, list) and len(rows) > MAX_ROWS:
                reason = "RESPONSE_TOO_LARGE"
            elif isinstance(rows, list) and not rows:
                reason = "NO_DATA"
            else:
                operation.update(_summarize_rows(rows, request))
        except PermissionError:
            reason = "PERMISSION_DENIED"
        except TimeoutError:
            reason = "REQUEST_TIMEOUT"
        except ProbeSchemaError:
            reason = "INVALID_RESPONSE_SCHEMA"
        except ProviderError as error:
            reason = "PERMISSION_DENIED" if error.safe_code in {
                "CREDENTIALS_MISSING", "PERMISSION_OR_CREDENTIALS_DENIED",
            } else "CAPABILITY_UNAVAILABLE" if isinstance(error, CapabilityUnavailable) else "TRANSPORT_FAILED"
        except Exception:
            reason = "TRANSPORT_FAILED"
        operation.update(completed_at=_now(clock), elapsed_seconds=_elapsed(start, monotonic), reason=reason)
        receipt["operations"].append(operation)
        if reason:
            receipt.update(status="STOPPED", stop_reason=reason)
            break
        if operation["status"] == "PARTIAL_FIXTURE_COVERAGE":
            receipt["status"] = "FIXTURE_PLAN_PARTIAL"
    receipt["finished_at"] = _now(clock)
    return receipt
