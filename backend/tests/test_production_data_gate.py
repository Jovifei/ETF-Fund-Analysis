from __future__ import annotations

from datetime import datetime, timezone

from scripts.production_data_gate import evaluate_snapshot


def item(**overrides):
    value = {
        "ts_code": "510300.SH",
        "name": "fixture",
        "daily_latest": "2026-09-15",
        "missing_volume": 0,
        "missing_amount": 0,
        "indicator_latest": "2026-09-15",
        "indicator_version": "ind-v0.7.3-audit",
        "forecast_latest": "2026-09-15",
        "forecast_horizons": 4,
        "quote_latest": "2026-09-15T14:34:00+08:00",
        "quote_realtime": True,
        "quote_timestamp_verified": True,
        "daily_rows": 288,
    }
    value.update(overrides)
    return value


def test_complete_snapshot_passes_strict_release_gate():
    result = evaluate_snapshot(
        {"target_trade_date": "2026-09-15", "items": [item()]},
        now=datetime(2026, 9, 15, 15, 30, tzinfo=timezone.utc),
        require_realtime=True,
    )
    assert result["status"] == "pass"
    assert result["qualification_granted"] is True
    assert result["summary"]["blocked_instruments"] == 0


def test_missing_volume_and_target_indicator_fail_without_coercion():
    result = evaluate_snapshot(
        {"target_trade_date": "2026-09-15", "items": [item(missing_volume=1, indicator_latest="2026-09-14")]},
        now=datetime(2026, 9, 15, 15, 30, tzinfo=timezone.utc),
    )
    assert result["status"] == "fail"
    blockers = result["items"][0]["blockers"]
    assert "volume_missing" in blockers
    assert "indicator_target_not_covered" in blockers
    assert result["qualification_granted"] is False


def test_non_realtime_quote_is_research_only_unless_release_requires_it():
    snapshot = {"target_trade_date": "2026-09-15", "items": [item(quote_realtime=False, quote_timestamp_verified=False)]}
    research = evaluate_snapshot(snapshot, require_realtime=False)
    release = evaluate_snapshot(snapshot, require_realtime=True)
    assert research["status"] == "pass"
    assert release["status"] == "fail"
    assert "quote_not_realtime_or_verified" in release["items"][0]["blockers"]


def test_empty_or_malformed_instrument_list_fails_closed():
    result = evaluate_snapshot({"target_trade_date": "2026-09-15", "items": []})
    assert result["status"] == "fail"
    assert result["qualification_granted"] is False
