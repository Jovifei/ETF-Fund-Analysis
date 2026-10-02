"""F0 isolated minute probe helpers.

Test-only capability: validates provider-shaped minute payloads without network,
credentials, provider enablement, or qualification changes.
"""

from __future__ import annotations

from datetime import datetime


class ProbeSchemaError(ValueError):
    pass


ALLOWED_INTERVALS = {"5m", "15m"}


def parse_minute_fixture(*, interval: str, expected_code: str, rows: list[dict]):
    if interval not in ALLOWED_INTERVALS:
        raise ProbeSchemaError("minute_interval_not_in_f0_scope")
    checked = []
    for row in rows:
        if row.get("ts_code") != expected_code:
            raise ProbeSchemaError("minute_identity_mismatch")
        for field in ("open", "high", "low", "close", "vol", "amount"):
            if row.get(field) is None:
                raise ProbeSchemaError("minute_required_field_missing")
        if not isinstance(row.get("trade_time"), datetime):
            raise ProbeSchemaError("minute_trade_time_invalid")
        if row["low"] > row["high"]:
            raise ProbeSchemaError("minute_ohlc_invalid")
        checked.append({
            "ts_code": expected_code,
            "interval": interval,
            "volume_unit": "upstream_declared_only",
            "amount_unit": "upstream_declared_only",
        })
    return checked


def validate_probe_limits(*, request_count: int, timeout_seconds: int) -> None:
    if request_count > 20:
        raise ProbeSchemaError("f0_request_bound_exceeded")
    if timeout_seconds > 10:
        raise ProbeSchemaError("f0_timeout_bound_exceeded")
