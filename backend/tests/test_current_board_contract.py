from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.models import DecisionBoardSnapshot, Instrument
from app.services.current_decision_service import CurrentDecisionService
from app.services.decision_board_service import READ_MODEL_VERSION
from app.services.signal_center_service import SignalCenterService
from app.utils.hashing import stable_hash


@pytest.fixture
def board_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
        db.rollback()
    engine.dispose()


def put_board(db, settings, *, identity, when, current=True):
    row = DecisionBoardSnapshot(
        snapshot_id=identity, generated_at=when,
        next_refresh_at=when + timedelta(hours=1), freshness='fresh',
        payload_json={
            'snapshot_id': identity, 'generated_at': when.isoformat(),
            'read_model_version': READ_MODEL_VERSION if current else 'obsolete',
            'config_hash': stable_hash(settings.load_strategy()) if current else 'obsolete',
            'rows': [{'ts_code': '510300.SH', 'grade': '可入场'}],
        },
    )
    db.add(row)
    db.flush()
    return row


def read_rows(kind, db, settings):
    if kind == 'current_decision':
        return CurrentDecisionService(settings).latest_board_rows(db)
    return SignalCenterService(settings)._latest_decision_rows(db)


@pytest.mark.parametrize('kind', ['current_decision', 'signal_center'])
def test_future_latest_board_is_unavailable_without_falling_back(board_db, kind):
    settings = Settings(_env_file=None, app_env='test', market_provider='mock', auth_enabled=False)
    now = datetime.now(settings.timezone)
    put_board(board_db, settings, identity='earlier', when=now-timedelta(hours=1))
    put_board(board_db, settings, identity='future', when=now+timedelta(days=1))
    board_db.expunge_all()  # Exercise SQLite's naive datetime readback too.
    identity, rows = read_rows(kind, board_db, settings)
    assert identity == 'future'
    assert rows == {}
    assert not board_db.dirty and not board_db.new and not board_db.deleted


@pytest.mark.parametrize('kind', ['current_decision', 'signal_center'])
def test_legacy_latest_board_never_publishes_original_grade(board_db, kind):
    settings = Settings(_env_file=None, app_env='test', market_provider='mock', auth_enabled=False)
    put_board(board_db, settings, identity='legacy', when=datetime.now(settings.timezone)-timedelta(minutes=1), current=False)
    _, rows = read_rows(kind, board_db, settings)
    assert rows['510300.SH']['grade'] == '数据异常'
    assert not board_db.dirty


@pytest.mark.parametrize('kind', ['current_decision', 'signal_center'])
def test_current_valid_board_retains_its_grade(board_db, kind):
    settings = Settings(_env_file=None, app_env='test', market_provider='mock', auth_enabled=False)
    put_board(board_db, settings, identity='valid', when=datetime.now(settings.timezone)-timedelta(minutes=1))
    identity, rows = read_rows(kind, board_db, settings)
    assert identity == 'valid'
    assert rows['510300.SH']['grade'] == '可入场'
    assert not board_db.dirty


def test_default_board_read_rejects_future_without_older_fallback(board_db):
    from app.services.decision_board_service import DecisionBoardService

    settings = Settings(_env_file=None, app_env='test', market_provider='mock', auth_enabled=False)
    now = datetime.now(settings.timezone)
    put_board(board_db, settings, identity='earlier', when=now-timedelta(hours=1))
    put_board(board_db, settings, identity='future', when=now+timedelta(days=1))
    payload = DecisionBoardService(settings).read_latest(board_db)
    assert payload['snapshot_id'] == 'future'
    assert payload['rows'] == []
    assert payload['read_contract'] == 'snapshot_after_read_time'
    assert payload['source_status']['actionable'] is False
    assert not board_db.dirty and not board_db.new and not board_db.deleted


def test_explicit_historical_snapshot_remains_inspectable_but_not_current(board_db):
    from app.services.decision_board_service import DecisionBoardService

    settings = Settings(_env_file=None, app_env='test', market_provider='mock', auth_enabled=False)
    now = datetime.now(settings.timezone)
    put_board(board_db, settings, identity='future-audit', when=now+timedelta(days=1))
    service = DecisionBoardService(settings)
    historical = service.read_latest(board_db, snapshot_id='future-audit')
    assert historical['rows'][0]['grade'] == '可入场'
    current = service.read_latest(board_db, snapshot_id='future-audit', at=now)
    assert current['rows'] == []
    assert current['read_contract'] == 'snapshot_after_read_time'
    assert service.read_instrument(board_db, '510300.SH') is None
    assert not board_db.dirty


@pytest.mark.parametrize('kind', ['current_decision', 'signal_center'])
@pytest.mark.parametrize('changed_field', ['read_model_version', 'config_hash'])
def test_each_board_identity_mismatch_demotes_raw_grade(board_db, kind, changed_field):
    settings = Settings(_env_file=None, app_env='test', market_provider='mock', auth_enabled=False)
    row = put_board(board_db, settings, identity='mismatch', when=datetime.now(settings.timezone)-timedelta(minutes=1))
    row.payload_json = {**row.payload_json, changed_field: 'obsolete'}
    board_db.flush()
    _, rows = read_rows(kind, board_db, settings)
    assert rows['510300.SH']['grade'] == '数据异常'
    assert rows['510300.SH']['historical_grade'] == '可入场'
    assert row.payload_json['rows'][0]['grade'] == '可入场'
    assert not board_db.dirty


def test_exact_read_boundary_accepts_equivalent_utc_instant(board_db):
    from datetime import timezone
    from app.services.decision_board_service import DecisionBoardService

    settings = Settings(_env_file=None, app_env='test', market_provider='mock', auth_enabled=False)
    observed = datetime.now(settings.timezone)
    put_board(board_db, settings, identity='boundary', when=observed)
    payload = DecisionBoardService(settings).read_latest(
        board_db, snapshot_id='boundary', at=observed.astimezone(timezone.utc),
    )
    assert payload['rows'][0]['grade'] == '可入场'
    assert payload['read_contract'] == 'version_matched'
    assert not board_db.dirty


def test_detail_retains_blocked_reason_only_for_included_instrument(board_db):
    from app.workspace.read_model import instrument_detail

    settings = Settings(_env_file=None, app_env='test', market_provider='mock', auth_enabled=False)
    for code in ('510300.SH', '511000.SH'):
        board_db.add(Instrument(ts_code=code, symbol=code[:6], name='detail fixture', kind='ETF', enabled=True))
    board_db.flush()
    now = datetime.now(settings.timezone)
    put_board(board_db, settings, identity='future-detail', when=now+timedelta(days=1))
    included = instrument_detail(board_db, settings, '510300.SH', None, as_of=now)
    absent = instrument_detail(board_db, settings, '511000.SH', None, as_of=now)
    assert included['decision'] is None and absent['decision'] is None
    assert included['availability']['decision']['reason_code'] == 'decision_snapshot_after_read_time'
    assert absent['availability']['decision']['reason_code'] == 'decision_not_generated'
    assert not board_db.dirty


def test_detail_accepts_board_before_explicit_historical_cutoff(board_db):
    from app.workspace.read_model import instrument_detail

    settings = Settings(_env_file=None, app_env='test', market_provider='mock', auth_enabled=False)
    board_db.add(Instrument(ts_code='510300.SH', symbol='510300', name='detail fixture', kind='ETF', enabled=True))
    board_db.flush()
    now = datetime.now(settings.timezone)
    missing = instrument_detail(board_db, settings, '510300.SH', None, as_of=now)
    assert missing['availability']['decision']['reason_code'] == 'decision_not_generated'
    put_board(board_db, settings, identity='past-detail', when=now-timedelta(hours=2))
    detail = instrument_detail(board_db, settings, '510300.SH', None, as_of=now-timedelta(hours=1))
    assert detail['decision']['grade'] == '可入场'
    assert detail['availability']['decision']['status'] == 'available'
    assert not board_db.dirty
