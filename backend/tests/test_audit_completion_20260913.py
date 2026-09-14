"""Regression tests: task completion must describe outputs for the target session."""
from datetime import datetime, date
from uuid import uuid4
import pytest
from app.core.config import get_settings
from app.models import Instrument, TaskRun
from sqlalchemy import select
from app.services.task_outcome import normalize_outcome, coverage_outcome
from app.services.settlement import session_refresh_due

@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,1.5,True,'3'])
def test_bad_coverage_counter_is_a_failed_result_not_an_exception(value):
    result=normalize_outcome({'requested':3,'completed':value,'status':'succeeded'})
    assert result['status']=='failed'
    assert result['coverage_complete'] is False


def test_input_instruments_are_not_successful_output():
    assert normalize_outcome({'instruments':35,'skipped':35})['status']=='failed'
    assert normalize_outcome({'instruments':35})['status']=='failed'
    assert coverage_outcome(2,3)['status']=='failed'


def test_nested_incomplete_result_cannot_keep_coverage_true():
    result=normalize_outcome({'requested':2,'completed':2,'coverage_complete':True,
        'input':{'requested':2,'completed':1}})
    assert result['status']=='partial'
    assert result['coverage_complete'] is False


def add_run(db,name,at,status='succeeded',target='2026-09-11',**fields):
    if name == 'refresh_bars':
        codes = list(db.scalars(select(Instrument.ts_code).where(Instrument.enabled.is_(True))))
        if not codes:
            db.add(Instrument(ts_code='998899.SH', symbol='998899', name='scope fixture', kind='ETF', enabled=True))
            db.flush()
            codes = ['998899.SH']
        fields = {'requested': len(codes), 'completed': len(codes),
                  'coverage': [{'ts_code': code, 'complete': True, 'received_through': target} for code in codes], **fields}
    db.add(TaskRun(run_id=uuid4().hex,task_name=name,status=status,started_at=at,
        finished_at=at,result_json={'status':status,'target_trade_date':target,
        'requested':2,'completed':2,'coverage_complete':True,**fields}))
    db.flush()


def test_new_target_does_not_inherit_yesterdays_backoff(db_session):
    s=get_settings();at=datetime(2026,9,11,15,16,tzinfo=s.timezone)
    add_run(db_session,'target-new',at.replace(minute=14),target='2026-09-10')
    assert session_refresh_due(db_session,s,'target-new',at)


def test_downstream_recovers_after_bars_succeeded_and_indicator_failed(db_session):
    s=get_settings();at=datetime(2026,9,11,16,0,tzinfo=s.timezone)
    add_run(db_session,'refresh_bars',at.replace(minute=30,hour=15))
    add_run(db_session,'refresh_indicators',at.replace(minute=30,hour=15),
        status='failed',completed=0,coverage_complete=False)
    from app.scheduler import settled_pipeline_tasks
    due=settled_pipeline_tasks(db_session,s,at)
    assert 'refresh_bars' not in due
    assert 'refresh_indicators' in due
    assert 'refresh_forecasts' in due


def test_later_successful_input_invalidates_derived_completion(db_session):
    s=get_settings();at=datetime(2026,9,11,17,0,tzinfo=s.timezone)
    add_run(db_session,'refresh_indicators',at.replace(hour=16,minute=10))
    add_run(db_session,'refresh_bars',at.replace(hour=16,minute=30))
    assert session_refresh_due(db_session,s,'refresh_indicators',at,
        dependencies=('refresh_bars',))


def test_shared_outcome_reaches_workspace_worker_and_nested_pipeline():
    from app.workspace.worker import outcome_state
    assert outcome_state({'instruments':35,'skipped':35})=='failed'
    assert outcome_state({})=='failed'
    assert outcome_state({'status':'succeeded','completed':1,'requested':2})=='partial'
    assert normalize_outcome({'status':'partial','failed_steps':['context'],
        'steps':{'bars':{'status':'succeeded','unchanged':2},'context':{'status':'failed'}}})['status']=='partial'
