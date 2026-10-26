from datetime import datetime, timedelta, timezone

import pytest

from app.services.settled_daily_input import SettledDailyInput
from app.workspace.local_display_contract import compute_parts_hashes
from app.workspace.local_display_read import LocalDisplayReader, LocalDisplayStore


NOW = datetime(2026, 10, 26, 9, 40, tzinfo=timezone.utc)
CODE = "510300.SH"


def observation():
    context = SettledDailyInput(
        base={"target_trade_date": "2026-10-26", "target_codes": [CODE], "input_hash": "a" * 64},
        quote_hash="b" * 64, task_hash="c" * 64, run_id="synthetic", after_id=0,
        started_at=NOW, finished_at=NOW, receipt_hash="d" * 64,
    )
    return context.observation


def bundle(input_observation=None):
    parts = {
        "overview": {"rows": [{"ts_code": CODE, "grade": "观望"}], "generated_at": NOW.isoformat()},
        "details": {CODE: {"instrument": {"ts_code": CODE}, "quote": {"is_realtime": False}}},
        "charts": {CODE: {"bars": []}},
        "sectors": {"sectors": []},
    }
    manifest = {"contract_version": "local-display-v2", "code_sha": "a" * 40,
                "config_hash": "b" * 64, "sequence": 1, "generated_at": NOW.isoformat(),
                "expires_at": (NOW + timedelta(hours=2)).isoformat(), "actionable": False,
                "data_origin": "local_research", "universe": [CODE], "parts_hashes": compute_parts_hashes(parts)}
    if input_observation is not None:
        manifest["input_observation"] = input_observation
    return {"manifest": manifest, "parts": parts}


def read(reader, endpoint):
    if endpoint == "overview":
        return reader.read_overview()
    if endpoint == "board":
        return reader.read_decision_board()
    return reader.read_instrument_detail(CODE, now=NOW)


def test_settled_observation_has_explicit_type_and_compatible_basis():
    value = observation()
    assert value["type"] == "settled_daily_research"
    assert value["basis"] == "settled_daily_bars"
    assert value["is_realtime"] is False and value["actionable"] is False


@pytest.mark.parametrize("endpoint", ["overview", "board", "detail"])
def test_reader_preserves_manifest_input_observation_without_mutating_cache(tmp_path, endpoint):
    expected = {**observation(), "type": "settled_daily_research", "provenance": {"labels": ["settled"]}}
    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(expected), now=NOW)
    reader = LocalDisplayReader(store)
    first = read(reader, endpoint)
    assert first["input_observation"] == expected
    first["input_observation"]["basis"] = "changed"
    first["input_observation"]["provenance"]["labels"].append("changed")
    assert read(reader, endpoint)["input_observation"] == expected
    assert reader.load_bundle(None)["manifest"]["input_observation"] == expected


@pytest.mark.parametrize("endpoint", ["overview", "board", "detail"])
def test_legacy_bundle_without_input_observation_remains_readable(tmp_path, endpoint):
    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(), now=NOW)
    result = read(LocalDisplayReader(store), endpoint)
    assert result is not None and "input_observation" not in result
