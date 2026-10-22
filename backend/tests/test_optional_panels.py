"""Optional market-context / sector panels: publish real data, or an honest reason."""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.models import SectorSnapshot, TaskRun
from app.services.task_service import TaskService
from app.workspace.local_compute import (
    OPTIONAL_REASON_CARRIED, OPTIONAL_REASON_FAILED, OPTIONAL_REASON_NOT_TODAY,
    _market_item_too_old, export_local_v2, optional_result_available,
)
from app.workspace.local_display_read import LocalDisplayReader

UNIVERSE = ["510300.SH", "512480.SH"]


@pytest.mark.parametrize("result,expected", [
    ({"task_name": "refresh_market_context", "status": "succeeded"}, True),
    ({"task_name": "refresh_market_context", "status": "partial", "observed": 6}, True),
    ({"task_name": "refresh_market_context", "status": "partial", "observed": 0}, False),
    ({"task_name": "refresh_market_context", "status": "partial", "observed": True}, False),
    ({"task_name": "refresh_market_context", "status": "failed", "observed": 6}, False),
    ({"task_name": "refresh_sector_snapshots", "status": "partial", "observed": 6}, False),
    ({"task_name": "refresh_sector_snapshots", "status": "succeeded"}, True),
    ({"task_name": "refresh_sector_snapshots", "status": "unavailable"}, False),
])
def test_optional_result_available(result, expected):
    assert optional_result_available(result) is expected


def test_market_item_age_gate():
    now = datetime(2026, 10, 22, 6, 0, tzinfo=timezone.utc)
    assert _market_item_too_old({"source_timestamp": datetime(2016, 6, 12, 16)}, now)
    assert not _market_item_too_old({"source_timestamp": datetime(2026, 10, 20, 16)}, now)
    assert not _market_item_too_old({"source_timestamp": None}, now)
    assert not _market_item_too_old({"source_timestamp": "not-a-date"}, now)


@pytest.fixture
def board(database, bootstrapped, db_session):
    settings = get_settings()
    TaskService(settings).run(db_session, "refresh_decision_board")
    db_session.commit()
    yield settings
    db_session.execute(delete(TaskRun).where(TaskRun.run_id.like("optpanel-%")))
    db_session.commit()


def _add_run(db, settings, task, status, start, finish, result):
    db.add(TaskRun(run_id=f"optpanel-{uuid4().hex}", task_name=task, status=status,
                   started_at=start, finished_at=finish, result_json=json.dumps(result)))
    db.commit()


def _sector_window(db):
    lo = db.scalar(select(func.min(SectorSnapshot.fetched_at)))
    hi = db.scalar(select(func.max(SectorSnapshot.fetched_at)))
    return lo, hi


def _local_naive(settings, value):
    return value.astimezone(settings.timezone).replace(tzinfo=None)


def test_fast_slot_carries_same_day_refresh_with_label(board, db_session):
    settings = board
    lo, hi = _sector_window(db_session)
    assert lo is not None, "bootstrap must have stored sector snapshots"
    now = datetime.now(timezone.utc)
    local_now = _local_naive(settings, now)
    if lo.date() != local_now.date():
        pytest.skip("bootstrap sector rows not from today (midnight boundary)")
    _add_run(db_session, settings, "refresh_sector_snapshots", "succeeded", lo, hi, {"status": "succeeded"})
    _add_run(db_session, settings, "refresh_market_context", "partial", lo, local_now - timedelta(seconds=1),
             {"status": "partial", "observed": 3})
    bundle = export_local_v2(settings, sequence=1, code_sha="b" * 40, universe=UNIVERSE,
                             private_research=True, unavailable_parts=[], carry_optional=True)
    sectors = bundle["parts"]["sectors"]
    assert sectors["sectors"], "same-day stored sectors must be published"
    assert sectors["availability"] == "carried_forward"
    assert sectors["reason"] == OPTIONAL_REASON_CARRIED and sectors["refreshed_in_slot"] is False
    assert sectors["refreshed_at"].startswith(local_now.date().isoformat())
    market = bundle["parts"]["market_context"]
    assert market["availability"] == "carried_forward" and isinstance(market["items"], list)
    # Grades and row corroboration keep the fast-slot "not refreshed" projection.
    detail = bundle["parts"]["details"]["510300.SH"]
    assert "sectors_optional_not_refreshed" in detail["decision_explanation"]["evidence_caveats"]


def test_fast_slot_without_same_day_refresh_reports_reason(board, db_session):
    settings = board
    db_session.execute(delete(TaskRun).where(TaskRun.task_name.in_(
        ["refresh_sector_snapshots", "refresh_market_context"])))
    db_session.commit()
    bundle = export_local_v2(settings, sequence=2, code_sha="b" * 40, universe=UNIVERSE,
                             private_research=True, unavailable_parts=[], carry_optional=True)
    assert bundle["parts"]["sectors"] == {"sectors": [], "availability": "unavailable",
                                          "reason": OPTIONAL_REASON_NOT_TODAY}
    assert bundle["parts"]["market_context"] == {"items": [], "availability": "unavailable",
                                                 "reason": OPTIONAL_REASON_NOT_TODAY}


def test_failed_refresh_keeps_failure_reason_and_later_failed_rows_are_excluded(board, db_session):
    settings = board
    lo, hi = _sector_window(db_session)
    local_now = _local_naive(settings, datetime.now(timezone.utc))
    if lo.date() != local_now.date():
        pytest.skip("bootstrap sector rows not from today (midnight boundary)")
    _add_run(db_session, settings, "refresh_sector_snapshots", "succeeded", lo, hi, {"status": "succeeded"})
    late = hi + timedelta(milliseconds=5)
    db_session.add(SectorSnapshot(board_type="industry", sector_name="optpanel-late-failed-row",
                                  trade_date=late.date(), pct_change=9.9, source="test", fetched_at=late,
                                  quality_hash="optpanel"))
    db_session.commit()
    try:
        bundle = export_local_v2(settings, sequence=3, code_sha="b" * 40, universe=UNIVERSE,
                                 private_research=True, unavailable_parts=[], carry_optional=True)
        names = {row["sector_name"] for row in bundle["parts"]["sectors"]["sectors"]}
        assert names and "optpanel-late-failed-row" not in names
        failed = export_local_v2(settings, sequence=4, code_sha="b" * 40, universe=UNIVERSE,
                                 private_research=True, unavailable_parts=["sectors"])
        assert failed["parts"]["sectors"]["reason"] == OPTIONAL_REASON_FAILED
    finally:
        db_session.execute(delete(SectorSnapshot).where(SectorSnapshot.sector_name == "optpanel-late-failed-row"))
        db_session.commit()


def test_reader_passes_honest_status_through():
    class Store:
        pass
    reader = LocalDisplayReader.__new__(LocalDisplayReader)
    reader.load_bundle = lambda generation=None: {"manifest": {"sequence": 7}, "parts": {
        "sectors": {"sectors": [], "availability": "unavailable", "reason": OPTIONAL_REASON_NOT_TODAY}}}
    view = reader.read_sectors()
    assert view["available"] is False and view["reason"] == OPTIONAL_REASON_NOT_TODAY
    reader.load_bundle = lambda generation=None: {"manifest": {"sequence": 8}, "parts": {
        "sectors": {"sectors": [{"sector_name": "x", "pct_change": 1.0, "trade_date": "2026-10-22"}],
                    "availability": "carried_forward", "reason": OPTIONAL_REASON_CARRIED,
                    "refreshed_at": "2026-10-22T13:58:25+08:00", "source_as_of": "2026-10-22"}}}
    view = reader.read_sectors()
    assert view["available"] is True and view["source_as_of"] == "2026-10-22"
    assert view["boards"][0]["sector_pct_change"] == 1.0
