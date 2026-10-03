"""Selection, legacy projection and full non-flow golden parity."""
import json
import socket
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.db.base import Base
from app.models import DecisionBoardSnapshot, EtfShareScale
from app.services.decision_board_service import DecisionBoardService
from app.services.flow_share_research import build_flow_share_view
from app.services.signal_grade_service import SignalGradeService
from app.utils.hashing import stable_hash
from flow_share_sample import AS_OF, add_sample
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

NEW_VERSION = "decision-read-v110-flow-share-provenance"


@pytest.fixture
def runtime(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Provider/network access is forbidden in this contract")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    settings = Settings(_env_file=None, app_env="test", auth_enabled=False,
                        market_provider="akshare", allow_mock_fallback=False,
                        database_url="sqlite:///:memory:")
    try:
        with Session(engine) as db:
            inst = add_sample(db)
            yield db, settings, inst
    finally:
        engine.dispose()


def test_entire_non_flow_rows_equal_independent_pre_change_golden(runtime):
    db, settings, _ = runtime
    baseline = json.loads((Path(__file__).parent / "fixtures/flow_share_non_flow_golden.json").read_text())
    live = SignalGradeService(settings).build(db, as_of=AS_OF)["rows"][0]
    board = DecisionBoardService(settings)._build_payload(db, AS_OF)
    assert board["read_model_version"] == NEW_VERSION
    assert board["flow_share_contract"] == "etf-flow-share-v2"
    actual = {"signal_grade_row": {k: v for k, v in live.items() if k != "flow_share"},
              "decision_board_row": {k: v for k, v in board["rows"][0].items() if k != "flow_share"}}
    assert actual == baseline["rows"]
    assert live["grade"] == "可加仓" and live["actionable"] is False


def test_naive_board_generation_saves_an_aware_envelope_and_roundtrips(runtime):
    db, settings, _ = runtime
    service = DecisionBoardService(settings)
    payload = service._build_payload(db, AS_OF.replace(tzinfo=None))
    assert payload["generated_at"] == AS_OF.isoformat()
    db.add(DecisionBoardSnapshot(snapshot_id=payload["snapshot_id"], generated_at=AS_OF.replace(tzinfo=None),
                                freshness=payload["freshness"], payload_json=payload))
    db.commit()
    value = service.read_latest(db, snapshot_id=payload["snapshot_id"])["rows"][0]["flow_share"]
    assert value == payload["rows"][0]["flow_share"]
    assert value["main_net_inflow"] == 20


def test_both_callers_select_newest_known_total_without_older_delta(runtime):
    db, settings, inst = runtime
    later = AS_OF + timedelta(days=1)
    newest = EtfShareScale(instrument_id=inst.id, trade_date=later.date(), shares=800,
                          previous_trade_date=None, previous_shares=None, share_delta=None,
                          share_delta_ratio=None, day_over_day=False, proxy="不可用",
                          source="akshare:fund_etf_scale_sse", exchange="SH", fetched_at=later,
                          quality_hash="newest-no-delta")
    db.add(newest)
    # A newer source date is never eligible, even with an earlier acquisition.
    db.add(EtfShareScale(instrument_id=inst.id, trade_date=date(2099, 1, 1), shares=999,
                        day_over_day=False, proxy="不可用", source=newest.source, exchange="SH",
                        fetched_at=AS_OF, quality_hash="future-source"))
    db.flush()
    service = DecisionBoardService(settings)
    for cutoff, expected in [(AS_OF, 900), (later, 800)]:
        live = SignalGradeService(settings).build(db, as_of=cutoff)["rows"][0]["flow_share"]["share_scale"]
        board = service._build_payload(db, cutoff)["rows"][0]["flow_share"]["share_scale"]
        assert live == board
        assert live["shares"] == expected
    assert live["share_delta"] is None and live["proxy"] == "不可用"
    # A correction acquired after the cutoff cannot reconstruct the old value.
    newest.fetched_at = later + timedelta(seconds=1)
    db.flush()
    value = service._build_payload(db, later)["rows"][0]["flow_share"]["share_scale"]
    assert value["shares"] == 900 and value["trade_date"] == AS_OF.date().isoformat()


def saved_payload(settings, *, version=NEW_VERSION, contract="etf-flow-share-v2", declared=None):
    flow = build_flow_share_view(SimpleNamespace(source="akshare:em:v101", flow_contract="etf-spot-flow-v1",
                                                quote_time=AS_OF, fetched_at=AS_OF, timestamp_verified=True,
                                                main_net_inflow=42), None, as_of=AS_OF)
    flow["contract"] = contract
    return {"snapshot_id": "saved-flow", "generated_at": AS_OF.isoformat(),
            "read_model_version": version, "config_hash": stable_hash(settings.load_strategy()),
            "flow_share_contract": contract if declared is None else declared,
            "freshness": "stale", "data_status": {}, "source_status": {},
            "rows": [{"ts_code": "510390.SH", "grade": "可加仓", "actionable": False,
                      "forecasts": {str(h): {"expected_return": h/100, "calibration_status": "not_calibrated"}
                                    for h in (1, 3, 5, 10)},
                      "flow_share": flow}]}


@pytest.mark.parametrize("field", ["spot_fetched_at", "spot_source", "spot_contract", "read_as_of",
                                  "unit_qualification", "actionable", "research_only"])
def test_v2_label_cannot_substitute_for_saved_provenance(runtime, field):
    db, settings, _ = runtime
    payload = saved_payload(settings)
    payload["rows"][0]["flow_share"].pop(field)
    original = deepcopy(payload)
    db.add(DecisionBoardSnapshot(snapshot_id="saved-flow", generated_at=AS_OF,
                                freshness="stale", payload_json=payload))
    db.commit()
    value = DecisionBoardService(settings).read_latest(db)["rows"][0]["flow_share"]
    assert value["main_net_inflow"] is None
    assert value["spot_reason_code"] == "saved_flow_contract_invalid"
    assert db.scalar(select(DecisionBoardSnapshot)).payload_json == original


@pytest.mark.parametrize("changes", [
    {"read_as_of": (AS_OF+timedelta(days=1)).isoformat()},
    {"spot_fetched_at": (AS_OF+timedelta(seconds=1)).isoformat()},
    {"net_inflow_unit": "million_cny"},
    {"actionable": True},
    {"main_net_inflow": True},
])
def test_saved_v2_inconsistent_fields_are_blocked(runtime, changes):
    db, settings, _ = runtime
    payload = saved_payload(settings)
    payload["rows"][0]["flow_share"].update(changes)
    db.add(DecisionBoardSnapshot(snapshot_id="saved-flow", generated_at=AS_OF,
                                freshness="stale", payload_json=payload))
    db.commit()
    flow = DecisionBoardService(settings).read_latest(db)["rows"][0]["flow_share"]
    assert flow["main_net_inflow"] is None
    assert flow["spot_reason_code"] == "saved_flow_contract_invalid"


def test_saved_flow_cannot_borrow_a_changed_json_generation_time(runtime):
    db, settings, _ = runtime
    payload = saved_payload(settings)
    payload["generated_at"] = (AS_OF + timedelta(days=1)).isoformat()
    db.add(DecisionBoardSnapshot(snapshot_id="saved-flow", generated_at=AS_OF,
                                freshness="stale", payload_json=payload))
    db.commit()
    flow = DecisionBoardService(settings).read_latest(db)["rows"][0]["flow_share"]
    assert flow["main_net_inflow"] is None
    assert flow["spot_reason_code"] == "saved_flow_contract_invalid"


@pytest.mark.parametrize(("version", "contract", "declared", "reason"), [
    ("decision-read-v109-flow-share", "etf-flow-share-v1", None, "legacy_snapshot_requires_rebuild"),
    (NEW_VERSION, None, None, "flow_contract_unverified"),
    (NEW_VERSION, "unsupported", None, "flow_contract_unverified"),
    (NEW_VERSION, "etf-flow-share-v2", "etf-flow-share-v1", "flow_contract_unverified"),
])
def test_old_or_mixed_saved_contracts_are_blocked_without_rewriting(runtime, monkeypatch, version, contract, declared, reason):
    db, settings, _ = runtime
    payload = saved_payload(settings, version=version, contract=contract, declared=declared)
    original = deepcopy(payload)
    db.add(DecisionBoardSnapshot(snapshot_id="saved-flow", generated_at=AS_OF,
                                freshness="stale", payload_json=payload))
    db.commit()
    statements = []
    def sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split()[0].upper())
    event.listen(db.bind, "before_cursor_execute", sql)
    def forbidden(*args, **kwargs):
        raise AssertionError("Reading saved snapshots cannot rebuild")
    monkeypatch.setattr(DecisionBoardService, "_build_payload", forbidden)
    monkeypatch.setattr(SignalGradeService, "build", forbidden)
    service = DecisionBoardService(settings)
    try:
        for horizon in (1, 3, 5, 10):
            for snapshot_id in (None, "saved-flow"):
                result = service.read_latest(db, horizon=horizon, snapshot_id=snapshot_id)
                row = result["rows"][0]
                flow = row["flow_share"]
                assert flow["main_net_inflow"] is flow["share_scale"]["shares"] is None
                assert flow["spot_reason_code"] == reason
                assert flow["projection_kind"] == "blocked_saved_contract"
                assert flow["projection_contract"] == "etf-flow-share-v2"
                assert flow["original_contract"] == contract
                assert flow["original_board_version"] == version
                assert result["read_model_version"] == version
                assert flow["actionable"] is False
                detail = service.read_instrument(db, "510390.SH", horizon=horizon, snapshot_id=snapshot_id)
                assert detail["flow_share"] == flow
                if version != NEW_VERSION:
                    assert row["historical_grade"] == "可加仓"
                    assert row["grade"] == "数据异常"
                else:
                    assert row["grade"] == "可加仓"
        db.expire_all()
        assert db.scalar(select(DecisionBoardSnapshot)).payload_json == original
        assert not db.dirty and not db.new and not db.deleted
        assert set(statements) == {"SELECT"}
    finally:
        event.remove(db.bind, "before_cursor_execute", sql)


def test_current_saved_flow_passes_through_on_snapshot_and_http_reads(runtime):
    from app.core.config import get_settings
    from app.db.session import get_db
    from app.main import app
    from fastapi.testclient import TestClient
    db, settings, _ = runtime
    payload = saved_payload(settings)
    db.add(DecisionBoardSnapshot(snapshot_id="saved-flow", generated_at=AS_OF,
                                freshness="stale", payload_json=payload))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        client = TestClient(app)
        for endpoint in ("/api/decision-board", "/api/decision-board/510390.SH"):
            response = client.get(endpoint, params={"snapshot_id": "saved-flow", "horizon": 5})
            assert response.status_code == 200
            assert response.headers["cache-control"] == "private, no-store"
            value = response.json()
            row = value["rows"][0] if "rows" in value else value
            assert row["flow_share"]["main_net_inflow"] == 42
            assert row["forecast"]["expected_return"] == .05
        assert db.scalar(select(DecisionBoardSnapshot)).payload_json == payload
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_settings, None)
