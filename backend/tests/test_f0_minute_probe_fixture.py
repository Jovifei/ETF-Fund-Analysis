from datetime import datetime

import pytest

from app.providers.f0_minute_probe import ProbeSchemaError, parse_minute_fixture, validate_probe_limits


def row(code="510300.SH"):
    return {
        "ts_code": code,
        "open": 4.0,
        "high": 4.2,
        "low": 3.9,
        "close": 4.1,
        "vol": 100,
        "amount": 1000,
        "trade_time": datetime(2026, 9, 30, 10, 5),
    }


def test_fixture_accepts_scoped_5m_and_15m_without_network():
    assert parse_minute_fixture(interval="5m", expected_code="510300.SH", rows=[row()])
    assert parse_minute_fixture(interval="15m", expected_code="512480.SH", rows=[row("512480.SH")])


def test_fixture_rejects_identity_and_ohlc_errors():
    with pytest.raises(ProbeSchemaError, match="identity"):
        parse_minute_fixture(interval="5m", expected_code="510300.SH", rows=[row("512480.SH")])
    bad = row()
    bad["low"] = 9
    with pytest.raises(ProbeSchemaError, match="ohlc"):
        parse_minute_fixture(interval="5m", expected_code="510300.SH", rows=[bad])


def test_probe_limits_and_no_qualification_path():
    validate_probe_limits(request_count=20, timeout_seconds=10)
    with pytest.raises(ProbeSchemaError):
        validate_probe_limits(request_count=21, timeout_seconds=10)
    with pytest.raises(ProbeSchemaError):
        validate_probe_limits(request_count=1, timeout_seconds=11)
