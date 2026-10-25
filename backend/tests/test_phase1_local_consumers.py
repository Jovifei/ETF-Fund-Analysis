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
                                                           "7": {"expected_return": .07}}}]},
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
    five = reader.read_decision_board(horizon=7, generation=1)
    assert five["selected_horizon"] == 7
    assert five["rows"][0]["forecast"]["expected_return"] == .07
    with pytest.raises(ValueError, match="horizon"):
        reader.read_decision_board(horizon=10)


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


def test_market_context_empty_never_falls_back(monkeypatch, tmp_path):
    from app.api import router as api
    monkeypatch.setattr(api.MarketContextService, "latest_view", lambda *a: pytest.fail("cloud fallback"))
    settings = Settings(_env_file=None, workspace_research_source="local_bundle",
                        local_display_v2_store_root=str(tmp_path / "empty"))
    assert api.market_context(None, settings)["latest_view"] == []


def test_holdings_reject_unapproved_local_quote(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app.workspace import local_display_read, read_model
    bundle = {"manifest": {"sequence": 1, "code_sha": "a" * 40, "config_hash": "b" * 64},
              "parts": {"overview": {"rows": []}, "details": {"510300.SH": {"quote": {"price": 10}}}}}
    monkeypatch.setattr(local_display_read.LocalDisplayStore, "load_bundle", lambda *a: bundle)
    holding = SimpleNamespace(shares=2, cost_price=4, target_weight=None, notes=None, updated_at=None)
    instrument = SimpleNamespace(ts_code="510300.SH", name="test", kind="ETF", theme_l1="test", id=1)
    db = SimpleNamespace(execute=lambda *a: SimpleNamespace(all=lambda: [(holding, instrument)]))
    settings = Settings(_env_file=None, workspace_research_source="local_bundle",
                        shadow_sync_code_sha="c" * 40, shadow_sync_config_hash="d" * 64,
                        local_display_v2_store_root=str(tmp_path / "store"))
    result = read_model.holdings_view(db, settings, 1)
    assert result["items"][0]["quote"]["price"] is None
    assert result["total_market_value"] is None


def test_watchlist_local_bundle_never_uses_frozen_cloud_quotes(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app.workspace import actions_api, local_display_read, read_model

    bundle = {"manifest": {"sequence": 8, "code_sha": "a" * 40, "config_hash": "b" * 64,
                           "expires_at": "2026-10-24T00:00:00Z"},
              "parts": {"details": {"510300.SH": {"quote": {
                  "price": 4.2, "status": "observed", "is_realtime": True,
                  "source_time": "2026-10-23T15:00:00+08:00", "actionable": False}}}}}
    monkeypatch.setattr(local_display_read.LocalDisplayStore, "load_bundle", lambda *a: bundle)
    cloud_reads = []
    monkeypatch.setattr(read_model, "latest_rows", lambda *a, **k: cloud_reads.append(True) or {})
    pairs = [(SimpleNamespace(id=index, note=None),
              SimpleNamespace(id=index, ts_code=code, name="test", kind="ETF", theme_l1="test", enabled=True))
             for index, code in enumerate(("510300.SH", "510500.SH"), 1)]
    db = SimpleNamespace(execute=lambda *a: SimpleNamespace(all=lambda: pairs))
    settings = Settings(_env_file=None, workspace_research_source="local_bundle",
                        shadow_sync_code_sha="a" * 40, shadow_sync_config_hash="b" * 64,
                        local_display_v2_store_root=str(tmp_path / "store"))

    items = actions_api.watchlist(db, settings, SimpleNamespace(id=1))["items"]
    assert cloud_reads == []
    assert items[0]["quote"]["price"] == 4.2
    assert items[0]["quote"]["source_time"] == "2026-10-23T15:00:00+08:00"
    assert items[0]["quote"]["status"] == "stale"
    assert items[0]["quote"]["is_realtime"] is False
    assert items[1]["quote"]["price"] is None
    assert items[1]["quote"]["status"] == "missing"


def test_holdings_expired_local_bundle_quote_is_not_current(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app.workspace import local_display_read, read_model

    bundle = {"manifest": {"sequence": 8, "code_sha": "a" * 40, "config_hash": "b" * 64,
                           "expires_at": "2026-10-24T00:00:00Z"},
              "parts": {"overview": {"rows": []}, "details": {"510300.SH": {"quote": {
                  "price": 4.2, "status": "observed", "is_realtime": True,
                  "source_time": "2026-10-23T15:00:00+08:00", "actionable": False}}}}}
    monkeypatch.setattr(local_display_read.LocalDisplayStore, "load_bundle", lambda *a: bundle)
    holding = SimpleNamespace(shares=2, cost_price=4, target_weight=None, notes=None, updated_at=None)
    instrument = SimpleNamespace(ts_code="510300.SH", name="test", kind="ETF", theme_l1="test", id=1)
    db = SimpleNamespace(execute=lambda *a: SimpleNamespace(all=lambda: [(holding, instrument)]))
    settings = Settings(_env_file=None, workspace_research_source="local_bundle",
                        shadow_sync_code_sha="a" * 40, shadow_sync_config_hash="b" * 64,
                        local_display_v2_store_root=str(tmp_path / "store"))

    quote = read_model.holdings_view(db, settings, 1)["items"][0]["quote"]
    assert quote["price"] == 4.2
    assert quote["source_time"] == "2026-10-23T15:00:00+08:00"
    assert quote["status"] == "stale"
    assert quote["is_realtime"] is False


def test_search_local_bundle_does_not_show_frozen_cloud_price(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.base import Base
    from app.models import Instrument
    from app.workspace import local_display_read, read_model

    bundle = {"manifest": {"sequence": 8, "code_sha": "a" * 40, "config_hash": "b" * 64,
                           "expires_at": "2026-10-24T00:00:00Z"},
              "parts": {"details": {"510300.SH": {"quote": {
                  "price": 4.2, "status": "observed", "is_realtime": True,
                  "source_time": "2026-10-23T15:00:00+08:00", "actionable": False}}}}}
    monkeypatch.setattr(local_display_read.LocalDisplayStore, "load_bundle", lambda *a: bundle)
    cloud_reads = []
    monkeypatch.setattr(read_model, "latest_rows", lambda *a, **k: cloud_reads.append(True) or {})
    settings = Settings(_env_file=None, workspace_research_source="local_bundle",
                        shadow_sync_code_sha="a" * 40, shadow_sync_config_hash="b" * 64,
                        local_display_v2_store_root=str(tmp_path / "store"))
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add_all([Instrument(ts_code=code, symbol=code[:6], name="test", kind="ETF", enabled=True)
                        for code in ("510300.SH", "510500.SH")])
            db.flush()
            result = read_model.search_instruments(db, settings, "510", 20, None)
    finally:
        engine.dispose()

    quotes = {item["ts_code"]: item["quote"] for item in result["items"]}
    assert cloud_reads == []
    assert quotes["510300.SH"]["price"] == 4.2
    assert quotes["510300.SH"]["status"] == "stale"
    assert quotes["510500.SH"]["price"] is None


@pytest.mark.parametrize("source_time", [None, {}, 42, "not-a-date"])
def test_local_bundle_bad_quote_time_is_stale_not_server_error(monkeypatch, tmp_path, source_time):
    from app.workspace import local_display_read, read_model

    bundle = {"manifest": {"sequence": 8, "code_sha": "a" * 40, "config_hash": "b" * 64,
                           "expires_at": "2030-10-25T00:00:00Z"},
              "parts": {"details": {"510300.SH": {"quote": {
                  "price": 4.2, "status": "observed", "is_realtime": True,
                  "source_time": source_time, "actionable": False}}}}}
    monkeypatch.setattr(local_display_read.LocalDisplayStore, "load_bundle", lambda *a: bundle)
    settings = Settings(_env_file=None, workspace_research_source="local_bundle",
                        shadow_sync_code_sha="a" * 40, shadow_sync_config_hash="b" * 64,
                        local_display_v2_store_root=str(tmp_path / "store"))

    quote = read_model.local_bundle_pricing(settings)[1]["510300.SH"]
    assert quote["status"] == "stale"
    assert quote["is_realtime"] is False


def test_local_bundle_non_observed_quote_cannot_claim_realtime(monkeypatch, tmp_path):
    from app.workspace import local_display_read, read_model

    bundle = {"manifest": {"sequence": 8, "code_sha": "a" * 40, "config_hash": "b" * 64,
                           "expires_at": "2030-10-25T00:00:00Z"},
              "parts": {"details": {"510300.SH": {"quote": {
                  "price": 4.2, "status": "stale", "is_realtime": True,
                  "source_time": "2026-10-23T15:00:00+08:00", "actionable": False}}}}}
    monkeypatch.setattr(local_display_read.LocalDisplayStore, "load_bundle", lambda *a: bundle)
    settings = Settings(_env_file=None, workspace_research_source="local_bundle",
                        shadow_sync_code_sha="a" * 40, shadow_sync_config_hash="b" * 64,
                        local_display_v2_store_root=str(tmp_path / "store"))
    quote = read_model.local_bundle_pricing(settings)[1]["510300.SH"]
    assert quote["status"] == "stale"
    assert quote["is_realtime"] is False
