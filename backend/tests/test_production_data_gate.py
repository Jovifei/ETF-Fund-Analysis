from __future__ import annotations

from datetime import datetime, timezone

# The CLI is not an installed package. Load by repository path so both
# the pytest console entry point and python -m pytest work on all platforms.
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "production_data_gate", Path(__file__).resolve().parents[2] / "scripts" / "production_data_gate.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_GATE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_GATE)
evaluate_snapshot = _GATE.evaluate_snapshot


def snapshot(**overrides):
    import json
    data = json.loads((Path(__file__).parent / "fixtures" / "production_freshness_v2.json").read_text(encoding="utf-8"))
    data["items"][0].update(overrides)
    return data


NOW = datetime.fromisoformat("2026-09-15T14:35:00+08:00")


def test_complete_snapshot_passes_strict_release_gate():
    # Old fixture used a nine-hour-old quote as a positive realtime example.
    # A positive now needs dated, versioned evidence and a genuinely recent quote.
    result = evaluate_snapshot(snapshot(), now=NOW, require_realtime=True)
    assert result["status"] == "pass"
    assert result["checks_passed"] is True
    assert result["qualification_granted"] is False
    assert result["summary"]["blocked_instruments"] == 0


def test_missing_volume_and_target_indicator_fail_without_coercion():
    result = evaluate_snapshot(snapshot(missing_volume=1, indicator_latest="2026-09-13"), now=NOW)
    assert result["status"] == "fail"
    blockers = result["items"][0]["blockers"]
    assert "volume_missing" in blockers
    assert "indicator_target_not_covered" in blockers
    assert result["qualification_granted"] is False


def test_non_realtime_quote_is_research_only_unless_release_requires_it():
    data = snapshot(quote_realtime=False, quote_timestamp_verified=False)
    research = evaluate_snapshot(data, now=NOW, require_realtime=False)
    release = evaluate_snapshot(data, now=NOW, require_realtime=True)
    assert research["status"] == "pass"
    assert release["status"] == "fail"
    assert "quote_not_realtime_or_verified" in release["items"][0]["blockers"]


def test_empty_or_malformed_instrument_list_fails_closed():
    result = evaluate_snapshot({"target_trade_date": "2026-09-15", "items": []}, now=NOW)
    assert result["status"] == "fail"
    assert result["qualification_granted"] is False
