"""A successful manual slice is not completion of the scheduled universe."""
from datetime import datetime
from uuid import uuid4
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Instrument, TaskRun
from app.services.settlement import session_refresh_due


@pytest.fixture
def scope_db(db_session):
    # All writes stay in the existing disposable test transaction.
    for symbol in ('998801', '998802'):
        if not db_session.scalar(select(Instrument).where(Instrument.ts_code == symbol + '.SH')):
            db_session.add(Instrument(ts_code=symbol + '.SH', symbol=symbol,
                                      name='scope regression', kind='ETF', enabled=True))
    db_session.flush()
    yield db_session
    db_session.rollback()


def record(db, codes, *, requested=None, complete=True):
    now = datetime(2026, 9, 14, 16, 0, tzinfo=get_settings().timezone)
    db.add(TaskRun(run_id=uuid4().hex, task_name='refresh_bars', status='succeeded',
        started_at=now, finished_at=now, result_json={
            'status': 'succeeded', 'target_trade_date': '2026-09-14',
            'requested': len(codes) if requested is None else requested,
            'completed': len(codes), 'coverage_complete': complete,
            'coverage': [{'ts_code': code, 'received_through': '2026-09-14',
                          'complete': True} for code in codes]}))
    db.flush()
    return now


def enabled(db):
    return list(db.scalars(select(Instrument.ts_code).where(Instrument.enabled.is_(True))))


def test_manual_slice_cannot_suppress_whole_universe_even_inside_backoff(scope_db):
    now = record(scope_db, enabled(scope_db)[:1])
    assert session_refresh_due(scope_db, get_settings(), 'refresh_bars', now)


def test_complete_current_universe_suppresses_redundant_download(scope_db):
    now = record(scope_db, enabled(scope_db))
    assert not session_refresh_due(scope_db, get_settings(), 'refresh_bars', now)


def test_same_count_different_codes_is_not_universe_completion(scope_db):
    codes = enabled(scope_db)
    now = record(scope_db, codes[:-1] + ['999999.SH'])
    assert session_refresh_due(scope_db, get_settings(), 'refresh_bars', now.replace(minute=30))


def test_newly_enabled_instrument_invalidates_completion(scope_db):
    now = record(scope_db, enabled(scope_db))
    scope_db.add(Instrument(ts_code='998803.SH', symbol='998803', name='new', kind='ETF', enabled=True))
    scope_db.flush()
    assert session_refresh_due(scope_db, get_settings(), 'refresh_bars', now)


def test_failed_full_attempt_keeps_retry_budget(scope_db):
    codes = enabled(scope_db)
    now = record(scope_db, codes[:-1], requested=len(codes), complete=False)
    assert not session_refresh_due(scope_db, get_settings(), 'refresh_bars', now.replace(minute=1))
    assert session_refresh_due(scope_db, get_settings(), 'refresh_bars', now.replace(minute=16))


def test_file_lease_without_query_is_released_when_session_closes(tmp_path):
    from app.db.task_lock import sqlite_pipeline_lease
    engine = create_engine('sqlite:///' + str(tmp_path / 'lease.sqlite'))
    with Session(engine) as db:
        assert sqlite_pipeline_lease(db)
        # No SQL follows the acquisition; close must still release the OS lease.
    child = '''import sys
from pathlib import Path
from app.db.task_lock import PipelineFileLock, PipelineLockBusy
try:
    lock=PipelineFileLock(Path(sys.argv[1])).acquire(); lock.release()
except PipelineLockBusy:
    sys.exit(7)
'''
    result = subprocess.run([sys.executable, '-c', child,
                            str(tmp_path / 'lease.sqlite.pipeline.lock')], timeout=10)
    engine.dispose()
    assert result.returncode == 0
