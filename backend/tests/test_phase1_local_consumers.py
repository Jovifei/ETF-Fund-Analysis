from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.workspace.local_display_read import LocalDisplayReader


class MemoryStore:
    def __init__(self):
        self.latest = 1
        self.calls = []
        self.bundles = {
            i: {"manifest": {"sequence": i, "generated_at": f"2026-10-15T0{i}:00:00Z",
                              "expires_at": "2026-10-15T20:00:00Z"},
                "parts": {"overview": {"snapshot_id": f"board-{i}", "rows": [
                    {"ts_code": "510300.SH", "forecasts": {"1": {"expected_return": .01},
                                                           "5": {"expected_return": .05}}}]},
                          "details": {"510300.SH": {"read_as_of": f"2026-10-15T0{i}:00:00Z"}},
                          "charts": {"510300.SH": {"as_of": f"2026-10-15T0{i}:00:00Z", "bars": []}},
                          "sectors": {"sectors": []}}}
            for i in (1, 2)
        }

    def load_bundle(self, generation=None):
        self.calls.append(generation)
        return deepcopy(self.bundles.get(self.latest if generation is None else int(generation)))


def test_explicit_generation_and_capture_time_never_follow_latest():
    store = MemoryStore()
    reader = LocalDisplayReader(store)
    detail = reader.read_instrument_detail("510300.SH")
    store.latest = 2
    chart = reader.read_chart_data("510300.SH", generation=detail["generation"], as_of=detail["read_as_of"])
    assert chart["generation"] == detail["generation"] == 1
    assert chart["as_of"] == detail["read_as_of"]
    with pytest.raises(ValueError, match="generation_time_mismatch"):
        reader.read_chart_data("510300.SH", generation=2, as_of=detail["read_as_of"])


def test_board_snapshot_and_horizon_are_explicit():
    reader = LocalDisplayReader(MemoryStore())
    assert reader.read_decision_board(snapshot_id="missing") is None
    five = reader.read_decision_board(horizon=5, generation=1)
    assert five["selected_horizon"] == 5
    assert five["rows"][0]["forecast"]["expected_return"] == .05
    with pytest.raises(ValueError, match="horizon"):
        reader.read_decision_board(horizon=20)


def test_cloud_chart_reader_never_aggregates_daily_data():
    reader = LocalDisplayReader(MemoryStore())
    assert reader.read_chart_data("510300.SH", interval="1w") is None


def test_local_board_missing_never_reads_cloud_database(monkeypatch, tmp_path):
    from app.api import router as api
    settings = Settings(_env_file=None, workspace_research_source="local_bundle",
                        local_display_v2_store_root=str(tmp_path / "empty"))
    def forbidden(*args, **kwargs):
        pytest.fail("local display read fell back to cloud research database")
    monkeypatch.setattr(api.DecisionBoardService, "read_latest", forbidden)
    with pytest.raises(HTTPException) as exc:
        api.decision_board(None, settings, type("Response", (), {"headers": {}})(), horizon=1,
                           snapshot_id=None, generation=None)
    assert exc.value.status_code == 404


def test_chart_api_forwards_capture_time(monkeypatch):
    from app.workspace import api
    seen = {}
    class Reader:
        def read_chart_data(self, *args, **kwargs):
            seen.update(kwargs)
            return {"bars": []}
    monkeypatch.setattr(api, "_local_reader", lambda _: Reader())
    at = datetime(2026, 10, 14, tzinfo=timezone.utc)
    api.chart("510300.SH", None, Settings(_env_file=None, workspace_research_source="local_bundle"),
              None, interval="1d", limit=30, as_of=at, generation="1")
    assert seen["generation"] == "1" and seen["as_of"] == at
