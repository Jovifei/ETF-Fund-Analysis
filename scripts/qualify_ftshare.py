#!/usr/bin/env python3
"""Run bounded, read-only FTShare ETF qualification probes.

This script intentionally reports only sanitized operation outcomes.  It does
not alter environment variables, settings files, databases, or application
state, and it never invokes the third-party Skill scripts.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings  # noqa: E402
from app.providers.base import CapabilityUnavailable, ProviderError  # noqa: E402
from app.providers.ftshare import FTShareProvider  # noqa: E402

SKILL_COMMIT = "cbcfb6283e075fbaa65487a2cb1a75b70c5d4308"
PROBE_CODE = "510300.SH"
MAX_REPORTED_LATENCY_MS = 120_000.0
def _upstream_code(exc: BaseException) -> str | None:
    """Return only an adapter-attached safe code; never inspect raw text."""
    code = getattr(exc, "safe_code", None)
    return code if code == "UPSTREAM_REJECTED" else None


def _latency_ms(started: float) -> float:
    return round(min(MAX_REPORTED_LATENCY_MS, max(0.0, (time.perf_counter() - started) * 1000)), 2)


def _failure(exc: BaseException) -> dict[str, str | None]:
    # Exception text can contain an upstream message or host detail.  Keep the
    # report useful without making it a raw response/error sink.
    if isinstance(exc, CapabilityUnavailable):
        category = "CapabilityUnavailable"
    elif isinstance(exc, ProviderError):
        category = "ProviderError"
    else:
        category = "ProviderError"
    return {"status": "rejected", "failure_class": category, "upstream_code": _upstream_code(exc)}


def _clear_unverified_claims(report: dict) -> None:
    report.update({"schema_fields": None, "unit_findings": None, "timestamp_findings": None})


def _typed_fields(rows: list[object]) -> list[str]:
    """Only report the normalized record fields actually returned by the adapter."""
    fields: set[str] = set()
    for row in rows:
        to_dict = getattr(row, "to_dict", None)
        if not callable(to_dict):
            raise TypeError("qualification adapter returned untyped record")
        values = to_dict()
        if not isinstance(values, dict) or any(not isinstance(key, str) for key in values):
            raise TypeError("qualification adapter returned invalid record")
        fields.update(values)
    return sorted(fields)


def _probe(name: str, operation, report: dict) -> None:
    started = time.perf_counter()
    try:
        rows = operation()
        schema_fields = _typed_fields(rows)
        report.update(
            {
                "status": "ok" if rows else "rejected",
                "records": len(rows),
                "latency_ms": _latency_ms(started),
                "source": f"ftshare:{name}",
                "schema_fields": schema_fields,
                # Unit labels are not inferred from names or numeric shape.
                # A future provider contract validator may populate these only
                # after a source-side unit qualification.
                "unit_findings": {},
                "timestamp_findings": {},
                "upstream_code": None,
                # Provider-level truncation is not exposed by the normalized
                # records, so never assert a false value in a qualification
                # report.  The adapter's byte/page bounds are reported below.
                "pagination": {"bounded": True, "truncated": None},
            }
        )
        if not rows:
            report["failure_class"] = "CapabilityUnavailable"
            report["pagination"] = {"bounded": None, "truncated": None}
            report["upstream_code"] = None
            _clear_unverified_claims(report)
    except Exception as exc:  # noqa: BLE001 - report only sanitized class
        report.update(_failure(exc))
        report["records"] = 0
        report["latency_ms"] = _latency_ms(started)
        report["source"] = f"ftshare:{name}"
        report["pagination"] = {"bounded": None, "truncated": None}
        _clear_unverified_claims(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="bounded read-only FTShare ETF qualification")
    parser.add_argument("--code", default=PROBE_CODE, help="one ETF probe code (default: 510300.SH)")
    args = parser.parse_args()
    try:
        settings = Settings(_env_file=None, market_provider="ftshare", ftshare_enabled=True)
        provider = FTShareProvider(settings)
    except Exception as exc:  # noqa: BLE001
        report = {
            "status": "unqualified",
            "skill_commit": SKILL_COMMIT,
            "schemas": {"instruments": "InstrumentRecord", "daily": "BarRecord", "spot": "QuoteRecord"},
            "provider": "ftshare",
            "operations": {"provider_init": _failure(exc)},
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    operations = {
        "list_instruments": {
            "provider": "ftshare",
            "operation": "list_instruments",
            "records": 0,
        },
        "fetch_daily_bars": {
            "provider": "ftshare",
            "operation": "fetch_daily_bars",
            "records": 0,
        },
        "fetch_spot_quotes": {
            "provider": "ftshare",
            "operation": "fetch_spot_quotes",
            "records": 0,
        },
    }
    try:
        end = date.today()
        start = end - timedelta(days=min(10, settings.ftshare_max_date_span_days))
        _probe("list_instruments", lambda: provider.list_instruments([args.code]), operations["list_instruments"])
        _probe(
            "fetch_daily_bars",
            lambda: provider.fetch_daily_bars(args.code, start, end),
            operations["fetch_daily_bars"],
        )
        _probe("fetch_spot_quotes", lambda: provider.fetch_spot_quotes([args.code]), operations["fetch_spot_quotes"])
    finally:
        provider.close()

    qualified = all(operations[key].get("status") == "ok" and operations[key].get("records", 0) > 0 for key in operations)
    report = {
        "status": "qualified" if qualified else "unqualified",
        "skill_commit": SKILL_COMMIT,
        "schemas": {"instruments": "InstrumentRecord", "daily": "BarRecord", "spot": "QuoteRecord"},
        "provider": "ftshare",
        "probe_code": args.code,
        "bounded": {
            "max_pages": settings.ftshare_max_pages,
            "max_rows": settings.ftshare_max_rows,
            "max_date_span_days": settings.ftshare_max_date_span_days,
            "max_response_bytes": settings.ftshare_max_response_bytes,
        },
        "operations": operations,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if qualified else 1


if __name__ == "__main__":
    raise SystemExit(main())
