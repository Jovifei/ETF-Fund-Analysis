"""Offline source/time admission and saved-board compatibility regressions."""
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from app.services.decision_board_service import DecisionBoardService
from app.utils.sector_timing import build_sector_timing_observation

AT = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
ROWS = [{"theme_l1": "科技", "grade": "可加仓", "return_5d": .01}]
TAX = {"exact": {"半导体": {"theme_l1": "科技"}}}

def evidence(**changes):
    return {"sector_name": "半导体", "board_type": "industry", "source": "akshare",
            "pct_change": 1.5, "trade_date": AT.date().isoformat(),
            "fetched_at": AT.isoformat(), **changes}

def view(row, at=AT):
    return build_sector_timing_observation(ROWS, market_evidence=[row], taxonomy=TAX, at=at)["themes"][0]["market_corroboration"]

@pytest.mark.parametrize("changes,reason", [
    ({"source": "mock-sector"}, "source_unverified"),
    ({"source": "unknown"}, "source_unverified"),
    ({"fetched_at": None}, "acquisition_time_unknown"),
    ({"fetched_at": (AT + timedelta(seconds=1)).isoformat()}, "acquisition_after_cutoff"),
    ({"trade_date": "2099-01-01"}, "trade_date_after_cutoff"),
    ({"trade_date": "2026-10-08"}, "trade_date_stale"),
    ({"trade_date": None}, "trade_date_unknown"),
    ({"pct_change_unit": "ratio"}, "unit_conflict"),
    ({"pct_change": float("nan")}, "values_missing"),
])
def test_unqualified_evidence_is_explicitly_unavailable(changes, reason):
    corr = view(evidence(**changes))
    assert corr["available"] is False
    assert corr["reason_code"] == reason
    assert corr["mean_pct_change"] is None
    assert corr["alignment"] == "unavailable"

def test_accepted_adapter_percent_is_preserved_without_conversion():
    corr = view(evidence())
    assert corr["available"] is True
    assert corr["mean_pct_change"] == 1.5
    assert corr["pct_change_unit"] == "source_percent"
    assert corr["source_time"] is None
    assert corr["actionable"] is False

def test_missing_cutoff_never_invents_time_qualification():
    assert view(evidence(), at=None)["reason_code"] == "read_time_unknown"

def test_legacy_board_cannot_keep_current_sector_digest():
    service = DecisionBoardService()
    payload = service._empty_payload(1)
    payload.update(read_model_version="legacy", config_hash="legacy",
                   rows=[{"ts_code": "588000.SH", "grade": "可加仓"}],
                   sector_timing=build_sector_timing_observation(ROWS))
    original = deepcopy(payload)
    snapshot = SimpleNamespace(payload_json=payload, generated_at=AT, snapshot_id="saved")
    db = SimpleNamespace(scalar=lambda *_args, **_kwargs: snapshot)
    result = service.read_latest(db, snapshot_id="saved")
    assert result["rows"][0]["grade"] == "数据异常"
    assert result["sector_timing"]["summary"]["add_observation_themes"] == []
    assert result["sector_timing"]["reason_code"] == "legacy_snapshot_requires_rebuild"
    assert payload == original

@pytest.mark.parametrize("timing", [build_sector_timing_observation(ROWS), {"version": "sector-timing-observation-v1", "digest": {"add_themes": ["科技"]}}])
def test_compatible_board_still_blocks_missing_or_old_sector_admission(timing):
    from app.services.decision_board_service import READ_MODEL_VERSION
    from app.utils.hashing import stable_hash
    service = DecisionBoardService()
    payload = service._empty_payload(1)
    payload.update(read_model_version=READ_MODEL_VERSION,
                   config_hash=stable_hash(service.settings.load_strategy()),
                   rows=[{"ts_code": "588000.SH", "grade": "观望"}], sector_timing=timing)
    if timing.get("version") != "sector-timing-observation-v1":
        payload["sector_timing"].pop("evidence_contract", None)
    snapshot = SimpleNamespace(payload_json=payload, generated_at=AT, snapshot_id="compatible")
    result = service.read_latest(SimpleNamespace(scalar=lambda *_a, **_k: snapshot), snapshot_id="compatible")
    assert result["rows"][0]["grade"] == "观望"
    assert result["sector_timing"]["summary"]["add_observation_themes"] == []
    assert result["sector_timing"]["reason_code"] == "sector_evidence_contract_unverified"

def test_service_forwards_authoritative_generated_cutoff(monkeypatch):
    service = DecisionBoardService()
    monkeypatch.setattr(service.settings.__class__, "load_taxonomy", lambda _self: TAX)
    monkeypatch.setattr(service, "_latest_sector_market_evidence", lambda _db, **_kwargs: [evidence(fetched_at=(AT + timedelta(seconds=1)).isoformat())])
    result = service._safe_sector_timing_observation(None, ROWS, generated_at=AT)
    corr = result["themes"][0]["market_corroboration"]
    assert corr["reason_code"] == "acquisition_after_cutoff"
    assert corr["available"] is False
    assert result["themes"][0]["observation"] == "偏强观察"

@pytest.mark.parametrize("invalid", [True, -1, float("inf"), float("nan"), 1.5])
def test_invalid_breadth_is_missing_without_erasing_valid_percent(invalid):
    corr = view(evidence(up_count=invalid))
    assert corr["available"] is True
    assert corr["breadth_up"] is None
    assert corr["mean_pct_change"] == 1.5

def test_sqlite_query_admits_only_current_known_source_before_cutoff():
    from datetime import date

    from app.models import SectorSnapshot
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    engine = create_engine("sqlite://")
    SectorSnapshot.__table__.create(engine)
    try:
        with Session(engine) as db:
            for name, day, source, fetched, pct in [
                ("半导体", AT.date(), "akshare", AT, 1.5),
                ("半导体", AT.date() + timedelta(days=1), "akshare", AT, 99),
                ("半导体", AT.date(), "mock-sector", AT, 88),
                ("半导体未来采集", AT.date(), "akshare", AT + timedelta(seconds=1), 77),
                ("半导体旧日", date(2026, 10, 8), "akshare", AT, 66),
            ]:
                db.add(SectorSnapshot(sector_name=name, trade_date=day, source=source,
                                      board_type="industry", fetched_at=fetched,
                                      pct_change=pct, quality_hash=name + source + str(day)))
            db.flush()
            rows = DecisionBoardService()._latest_sector_market_evidence(db, at=AT)
            assert len(rows) == 1
            assert rows[0]["pct_change"] == 1.5
            assert rows[0]["sector_name"] == "半导体"
    finally:
        engine.dispose()
