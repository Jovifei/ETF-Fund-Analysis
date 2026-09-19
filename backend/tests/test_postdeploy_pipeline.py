"""Each settled output must recover independently; blocked research is still published."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest

from app.core.config import get_settings
from app.db.base import Base
from app.models import Instrument, TaskRun
from app.scheduler import DAILY_DEPENDENCIES, settled_pipeline_tasks
from app.services.settlement import session_refresh_due


@pytest.fixture
def isolated():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Instrument(ts_code='998801.SH', symbol='998801', kind='ETF', name='test', enabled=True))
        db.flush()
        yield db
    engine.dispose()


def done(db, name, at, **extra):
    result = {'status':'succeeded', 'requested':1, 'completed':1, 'coverage_complete':True,
              'target_trade_date':'2026-09-14', **extra}
    if name == 'refresh_bars':
        result['coverage'] = [{'ts_code':'998801.SH','complete':True,'received_through':'2026-09-14'}]
    db.add(TaskRun(run_id=uuid4().hex, task_name=name, status=result['status'], started_at=at,
                   finished_at=at, result_json=result))
    db.flush()


def test_restart_after_forecast_still_schedules_missing_board_and_report(isolated):
    now = datetime(2026,9,14,16,0,tzinfo=get_settings().timezone)
    for i, name in enumerate(('refresh_bars','refresh_indicators','refresh_forecasts')):
        done(isolated, name, now.replace(hour=15,minute=20+i))
    due = settled_pipeline_tasks(isolated,get_settings(),now)
    assert 'refresh_bars' not in due
    assert 'refresh_indicators' not in due
    assert 'refresh_forecasts' not in due
    assert 'refresh_decision_board' in due
    assert 'generate_report' in due


def test_board_and_report_have_explicit_upstream_invalidation_contract():
    assert 'refresh_signals' in DAILY_DEPENDENCIES['refresh_decision_board']
    assert 'refresh_decision_board' in DAILY_DEPENDENCIES['generate_report']


def test_settled_pipeline_order_is_topological():
    ordered = list(DAILY_DEPENDENCIES)
    positions = {name: index for index, name in enumerate(ordered)}
    for task_name, dependencies in DAILY_DEPENDENCIES.items():
        assert all(positions[dependency] < positions[task_name] for dependency in dependencies)


def test_new_input_in_same_tick_invalidates_all_downstream_outputs(isolated):
    now = datetime(2026,9,14,17,0,tzinfo=get_settings().timezone)
    for i,name in enumerate(DAILY_DEPENDENCIES):
        done(isolated,name,now.replace(hour=15,minute=20+i))
    # Newly written input invalidates indicators, and that planned recompute
    # must in turn invalidate board/report even before it has a finished_at.
    done(isolated,'refresh_bars',now.replace(hour=16,minute=40))
    due = settled_pipeline_tasks(isolated,get_settings(),now)
    assert 'refresh_indicators' in due
    assert 'refresh_decision_board' in due and 'generate_report' in due


def test_blocked_inputs_do_not_invent_research_qualification(isolated):
    from app.services.settlement import stamp_output_completion
    result = stamp_output_completion(isolated,get_settings(),'refresh_decision_board',
        {'status':'succeeded','snapshot_id':'test','actionable':False,'blocked_instruments':1},
        datetime(2026,9,14,16,0,tzinfo=get_settings().timezone))
    assert result['coverage_complete'] is True
    assert result['completion_basis'] == 'processed_output_not_research_qualification'
    assert result['actionable'] is False and result['blocked_instruments']==1


def test_failed_board_remains_due_without_upstream_repeat(isolated):
    now = datetime(2026,9,14,17,0,tzinfo=get_settings().timezone)
    for name in ('refresh_bars','refresh_indicators','refresh_forecasts','refresh_signals'):
        done(isolated,name,now.replace(hour=16))
    done(isolated,'refresh_decision_board',now.replace(hour=16),status='failed',completed=0,coverage_complete=False)
    due=settled_pipeline_tasks(isolated,get_settings(),now)
    assert 'refresh_decision_board' in due and 'refresh_bars' not in due


def _stamp_done(db, name, at, **extra):
    from app.services.settlement import stamp_output_completion, settled_session

    settings = get_settings()
    target = settled_session(settings, at).isoformat()
    result = {
        "status": "succeeded",
        "requested": 1,
        "completed": 1,
        "coverage_complete": True,
        "target_trade_date": target,
        **extra,
    }
    if name == "refresh_bars":
        result["coverage"] = [{"ts_code": "998801.SH", "complete": True, "received_through": target}]
    if name == "refresh_decision_board":
        result.setdefault("snapshot_id", "slot-receipt")
    if name in {"refresh_signals", "refresh_sector_snapshots"}:
        result.setdefault("created", 1)
    result = stamp_output_completion(db, settings, name, result, at)
    db.add(TaskRun(
        run_id=uuid4().hex,
        task_name=name,
        status=result["status"],
        started_at=at,
        finished_at=at,
        result_json=result,
    ))
    db.flush()
    return result


def test_intraday_board_success_cannot_complete_same_day_settled_board(isolated):
    settings = get_settings()
    slot_at = datetime(2026, 9, 14, 14, 50, tzinfo=settings.timezone)
    eod = datetime(2026, 9, 14, 16, 5, tzinfo=settings.timezone)
    slot = _stamp_done(isolated, "refresh_decision_board", slot_at)
    assert slot["coverage_complete"] is True
    assert slot["target_trade_date"] != "2026-09-14"
    for offset, name in enumerate(("refresh_bars", "refresh_indicators", "refresh_forecasts", "refresh_signals")):
        _stamp_done(isolated, name, eod.replace(hour=15, minute=20 + offset))
    due = settled_pipeline_tasks(isolated, settings, eod)
    assert "refresh_bars" not in due
    assert "refresh_indicators" not in due
    assert "refresh_forecasts" not in due
    assert "refresh_decision_board" in due
    assert "generate_report" in due
    assert session_refresh_due(
        isolated,
        settings,
        "refresh_decision_board",
        eod,
        dependencies=DAILY_DEPENDENCIES["refresh_decision_board"],
    )
