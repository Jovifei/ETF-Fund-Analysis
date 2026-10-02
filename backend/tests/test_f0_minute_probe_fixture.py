from datetime import datetime

import pytest

from app.providers.f0_minute_probe import ProbeSchemaError, parse_minute_fixture, validate_probe_limits


def row(code="510300.SH"):
    return {"ts_code": code, "open": 4.0, "high": 4.2, "low": 3.9, "close": 4.1, "vol": 100, "amount": 1000, "trade_time": "2026-09-30T10:05:00"}


def test_fixture_keeps_scoped_intervals_and_evidence_without_qualification():
    result = parse_minute_fixture(interval="5m", expected_code="510300.SH", rows=[row()])
    assert result[0]["qualified"] is False
    assert result[0]["actionable"] is False
    assert result[0]["volume"] == 100
    assert result[0]["amount"] == 1000

    assert parse_minute_fixture(interval="15m", expected_code="512480.SH", rows=[row("512480.SH")])


@pytest.mark.parametrize("field,value", [("close", float("nan")), ("open", float("inf")), ("vol", -1), ("amount", -1), ("open", True)])
def test_fixture_rejects_invalid_numeric_evidence(field, value):
    bad = row()
    bad[field] = value
    with pytest.raises(ProbeSchemaError):
        parse_minute_fixture(interval="5m", expected_code="510300.SH", rows=[bad])


def test_fixture_rejects_ohlc_envelope_and_identity():
    bad = row()
    bad["high"] = 3
    with pytest.raises(ProbeSchemaError, match="ohlc"):
        parse_minute_fixture(interval="5m", expected_code="510300.SH", rows=[bad])
    with pytest.raises(ProbeSchemaError, match="identity"):
        parse_minute_fixture(interval="5m", expected_code="510300.SH", rows=[row("512480.SH")])


@pytest.mark.parametrize("count,timeout", [(-1, 10), (21, 10), (1, 0), (1, 11), (True, 10), (1, True)])
def test_fixture_rejects_invalid_probe_limits(count, timeout):
    with pytest.raises(ProbeSchemaError):
        validate_probe_limits(request_count=count, timeout_seconds=timeout)


def test_fixture_does_not_claim_real_data():
    value = parse_minute_fixture(interval="5m", expected_code="510300.SH", rows=[row()])[0]
    assert value["volume_unit"] == "upstream_declared_only"
    assert value["amount_unit"] == "upstream_declared_only"
    assert "not publication/PIT certification" in value["time_assumption"]

@pytest.mark.parametrize('timeout', [float('nan'), float('inf'), -float('inf')])
def test_non_finite_timeout_is_rejected(timeout):
    with pytest.raises(ProbeSchemaError):
        validate_probe_limits(request_count=1, timeout_seconds=timeout)
