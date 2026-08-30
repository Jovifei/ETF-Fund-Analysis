from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.providers.base import CapabilityUnavailable
from app.providers.ftshare import FTShareProvider
from app.providers.types import BarRecord


def _module():
    path = Path(__file__).parents[2] / "scripts" / "qualify_ftshare.py"
    spec = importlib.util.spec_from_file_location("qualify_ftshare_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rejected_qualification_never_claims_schema_units_or_timestamps():
    module = _module()
    report = {"provider": "ftshare", "operation": "fetch_daily_bars"}

    def rejected():
        raise CapabilityUnavailable("private upstream detail", safe_code="UPSTREAM_REJECTED")

    module._probe("fetch_daily_bars", rejected, report)

    assert report["status"] == "rejected"
    assert report["records"] == 0
    assert report["schema_fields"] is None
    assert report["unit_findings"] is None
    assert report["timestamp_findings"] is None
    assert report["upstream_code"] == "UPSTREAM_REJECTED"
    assert "private upstream detail" not in str(report)
    assert 0 <= report["latency_ms"] <= module.MAX_REPORTED_LATENCY_MS


@pytest.mark.parametrize(
    ("error_code", "expected_safe_code"),
    [
        ("UPSTREAM_REJECTED", "UPSTREAM_REJECTED"),
        ("UPSTREAM_REJECTED_SUFFIX", None),
        ("unrelated_raw_code", None),
    ],
)
def test_provider_error_code_reaches_qualification_only_when_exact_allowlisted(error_code, expected_safe_code):
    module = _module()

    def handler(_request):
        return httpx.Response(
            403,
            json={"error": {"code": error_code, "message": "UPSTREAM_REJECTED private detail"}},
        )

    provider = FTShareProvider(
        Settings(_env_file=None, ftshare_enabled=True),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        report = {"provider": "ftshare", "operation": "list_instruments"}
        module._probe("list_instruments", provider.list_instruments, report)
    finally:
        provider.close()

    assert report["status"] == "rejected"
    assert report["upstream_code"] == expected_safe_code
    assert "private detail" not in str(report)


def test_successful_qualification_records_only_typed_observed_fields():
    module = _module()
    report = {"provider": "ftshare", "operation": "fetch_daily_bars"}
    row = BarRecord(
        ts_code="510300.SH", trade_date="2026-08-30", open=1, high=1, low=1, close=1,
        volume=1, amount=1, source="ftshare:fetch_daily_bars",
    )

    module._probe("fetch_daily_bars", lambda: [row], report)

    assert report["status"] == "ok"
    assert report["schema_fields"] == sorted(row.to_dict())
    assert report["unit_findings"] == {}
    assert report["timestamp_findings"] == {}
    assert report["upstream_code"] is None
