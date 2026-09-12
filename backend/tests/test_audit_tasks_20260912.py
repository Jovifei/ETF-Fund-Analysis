from datetime import datetime, date
from zoneinfo import ZoneInfo
from app.core.config import get_settings


def test_settled_session_cutoff_and_weekend():
    from app.services.settlement import settled_session
    s=get_settings()
    assert settled_session(s,datetime(2026,9,11,15,1,tzinfo=s.timezone))==date(2026,9,10)
    assert settled_session(s,datetime(2026,9,11,15,16,tzinfo=s.timezone))==date(2026,9,11)
    assert settled_session(s,datetime(2026,9,12,16,0,tzinfo=s.timezone))==date(2026,9,11)


def test_all_skipped_or_unknown_result_is_not_success():
    from app.services.task_outcome import normalize_outcome
    assert normalize_outcome({'created':0,'updated':0,'skipped':35,'failures':[{'reason':'missing'}]})['status']=='failed'
    assert normalize_outcome({})['status']=='failed'
    assert normalize_outcome({'status':'succeeded','created':0,'skipped':35})['status']=='failed'
    assert normalize_outcome({'requested':3,'completed':2,'status':'succeeded'})['status']=='partial'
    assert normalize_outcome({'requested':3,'completed':3,'coverage_complete':False})['status']=='partial'
    assert normalize_outcome({'requested':3,'completed':3,'coverage_complete':True})['status']=='succeeded'


def test_scheduler_guard_propagates_partial_and_commits():
    from app.scheduler import _run_guarded
    class DB:
        commits=0
        def commit(self):self.commits+=1
    class Tasks:
        def run(self,*a,**k):return {'status':'partial','missing':2}
    d=DB(); failures=[]
    assert not _run_guarded(Tasks(),d,'refresh_bars',executed=[],failures=failures)
    assert d.commits==1 and failures


def test_session_target_not_start_time_prevents_false_success(db_session):
    from app.services.settlement import session_refresh_due
    from app.models import TaskRun
    s=get_settings();at=datetime(2026,9,11,15,16,tzinfo=s.timezone)
    db_session.add(TaskRun(run_id='audit-old-session',task_name='audit_daily',status='succeeded',
        started_at=at.replace(minute=1),finished_at=at.replace(minute=2),
        result_json={'status':'succeeded','target_trade_date':'2026-09-10','coverage_complete':True}))
    db_session.flush()
    assert session_refresh_due(db_session,s,'audit_daily',at,retry_minutes=10)
    db_session.add(TaskRun(run_id='audit-partial-session',task_name='audit_daily',status='partial',
        started_at=at,finished_at=at,result_json={'target_trade_date':'2026-09-11','coverage_complete':False}))
    db_session.flush()
    assert not session_refresh_due(db_session,s,'audit_daily',at.replace(minute=17),retry_minutes=10)
    assert session_refresh_due(db_session,s,'audit_daily',at.replace(minute=27),retry_minutes=10)


def test_file_lease_is_cross_process_and_not_released_before_commit(tmp_path):
    import subprocess, sys
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.db.task_lock import sqlite_pipeline_lease
    engine=create_engine('sqlite:///'+str(tmp_path/'isolated.sqlite'))
    with Session(engine) as db:
        assert sqlite_pipeline_lease(db)
        db.execute(text('select 1'))
        lock_path=str(tmp_path/'isolated.sqlite.pipeline.lock')
        code='''import sys
from pathlib import Path
from app.db.task_lock import PipelineFileLock, PipelineLockBusy
try:
    lock=PipelineFileLock(Path(sys.argv[1])).acquire()
    lock.release()
except PipelineLockBusy:
    sys.exit(7)
'''
        assert subprocess.run([sys.executable,'-c',code,lock_path],timeout=10).returncode==7
        db.commit()
        assert subprocess.run([sys.executable,'-c',code,lock_path],timeout=10).returncode==0
    engine.dispose()
