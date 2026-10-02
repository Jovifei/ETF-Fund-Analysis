"""F0 isolated minute probe helpers.

Fixture-only capability: validates provider-shaped minute payloads without
network, credentials, provider enablement, production writes, or qualification
changes. Numeric fields remain in upstream-declared units; no unit conversion.
"""

from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo


class ProbeSchemaError(ValueError):
    pass


ALLOWED_INTERVALS = {"5m", "15m"}
ASSUMED_TZ = ZoneInfo("Asia/Shanghai")


def _number(value, field):
    if isinstance(value, bool):
        raise ProbeSchemaError(f"{field}_boolean_invalid")
    if not isinstance(value, (int, float)):
        raise ProbeSchemaError(f"{field}_numeric_invalid")
    if not math.isfinite(float(value)):
        raise ProbeSchemaError(f"{field}_non_finite")
    return value


def _trade_time(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=ASSUMED_TZ)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProbeSchemaError("minute_trade_time_invalid") from exc
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=ASSUMED_TZ)
    raise ProbeSchemaError("minute_trade_time_invalid")


def parse_minute_fixture(*, interval: str, expected_code: str, rows: list[dict]):
    if interval not in ALLOWED_INTERVALS:
        raise ProbeSchemaError("minute_interval_not_in_f0_scope")
    checked = []
    for row in rows:
        if row.get("ts_code") != expected_code:
            raise ProbeSchemaError("minute_identity_mismatch")
        values = {field: _number(row.get(field), field) for field in ("open", "high", "low", "close", "vol", "amount")}
        if values["vol"] < 0 or values["amount"] < 0:
            raise ProbeSchemaError("minute_quantity_negative")
        if not (values["low"] <= values["open"] <= values["high"] and values["low"] <= values["close"] <= values["high"]):
            raise ProbeSchemaError("minute_ohlc_invalid")
        observed = _trade_time(row.get("trade_time"))
        checked.append({
            "ts_code": expected_code,
            "interval": interval,
            "open": values["open"],
            "high": values["high"],
            "low": values["low"],
            "close": values["close"],
            "volume": values["vol"],
            "amount": values["amount"],
            "trade_time": observed.isoformat(),
            "time_assumption": "Asia/Shanghai if source omitted timezone; not publication/PIT certification",
            "volume_unit": "upstream_declared_only",
            "amount_unit": "upstream_declared_only",
            "qualified": False,
            "actionable": False,
        })
    return checked


def validate_probe_limits(*, request_count: int, timeout_seconds: int) -> None:
    if isinstance(request_count, bool) or not isinstance(request_count, int) or request_count < 0 or request_count > 20:
        raise ProbeSchemaError("f0_request_bound_invalid")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0 or timeout_seconds > 10:
        raise ProbeSchemaError("f0_timeout_bound_invalid")
