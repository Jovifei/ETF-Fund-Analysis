"""Regression evidence for the local-only V105 handoff patch (no network)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Instrument
from app.workspace.catalog_search import search_terms

SH = ZoneInfo('Asia/Shanghai')
NOW = datetime(2026, 9, 10, 14, 30, tzinfo=SH)


@pytest.mark.parametrize('query,expected', [
    ('煤炭开采加工', '煤炭'), ('煤炭开采加工行业板块', '煤炭'),
    ('军工装备', '军工'), ('军工设备', '国防'), ('元件', '半导体'),
    ('港口航运', '航运'), ('石油加工贸易', '油气'),
])
def test_screenshot_sector_names_expand(query, expected):
    terms, ctx = search_terms(query)
    assert expected in terms
    assert ctx['method'] == 'sector_alias'


def test_nonmetal_does_not_alias_to_nonferrous():
    terms, _ = search_terms('非金属材料')
    assert '有色' not in terms and '金属' not in terms
    assert search_terms('591234.SH')[1]['method'] == 'literal'


def test_search_can_find_untracked_coal_without_changing_pool(db_session):
    from app.workspace.read_model import search_instruments
    item = Instrument(ts_code='590997.SH', symbol='590997', name='煤炭交接测试ETF',
                      kind='ETF', enabled=False)
    db_session.add(item); db_session.flush()
    try:
        result = search_instruments(db_session, get_settings(), '煤炭开采加工', 100, None)
        assert any(x['ts_code'] == item.ts_code for x in result['items'])
        assert item.enabled is False
    finally:
        db_session.rollback()


def observation(**changes):
    return {'source_timestamp': NOW-timedelta(days=3), 'fetched_at': NOW,
            'freshness': 'fresh', 'verification_status': 'verified', 'is_mock': False,
            **changes}


def test_context_read_age_is_not_ingestion_age():
    from app.workspace.display_freshness import context_display
    data = observation()
    result = context_display(data, now=NOW, context_kind='tradable_proxy')
    assert result['status'] == 'stale'
    assert result['source_time'] != result['fetched_at']
    assert data['freshness'] == 'fresh'  # never overwrite persisted qualification


@pytest.mark.parametrize('patch,expected', [
    ({'source_timestamp': None}, 'unavailable'),
    ({'source_timestamp': NOW+timedelta(minutes=10)}, 'unverified'),
    ({'source_timestamp': NOW-timedelta(minutes=10), 'verification_status': 'unverified'}, 'unverified'),
    ({'source_timestamp': NOW-timedelta(minutes=10), 'is_mock': True}, 'mock'),
    ({'source_timestamp': NOW-timedelta(minutes=10), 'freshness': 'degraded'}, 'degraded'),
    ({'source_timestamp': NOW-timedelta(minutes=10)}, 'recent_observation'),
])
def test_freshness_does_not_promote_unqualified_data(patch, expected):
    from app.workspace.display_freshness import context_display
    r = context_display(observation(**patch), now=NOW, context_kind='tradable_proxy')
    assert r['status'] == expected
    assert r['actionable'] is False


def test_index_midnight_is_conservatively_date_only():
    from app.workspace.display_freshness import context_display
    r = context_display(observation(source_timestamp=datetime(2026,9,9)), now=NOW, context_kind='index')
    assert r['status'] == 'historical'
    assert r['date_label'] == '2026-09-09'
    assert r['precision'] == 'date_assumed'
    assert '实时' in r['note']


def test_schedule_default_is_off_and_windows_are_explicit():
    from app.workspace.refresh_policy import balanced_plan
    assert get_settings().balanced_refresh_enabled is False
    morning=balanced_plan(NOW, is_trade_day=True)
    assert morning.market_open and morning.quote_minutes == 30
    assert morning.news_minutes == 30 and not morning.after_close
    lunch=balanced_plan(NOW.replace(hour=12), is_trade_day=True)
    assert not lunch.market_open
    close=balanced_plan(NOW.replace(hour=16,minute=15), is_trade_day=True)
    assert close.after_close
    assert not balanced_plan(NOW, is_trade_day=False).market_open
    assert balanced_plan(NOW.replace(hour=23), is_trade_day=True).news_minutes == 120


def test_daily_refresh_success_is_once_per_local_day_and_failure_is_backed_off():
    from app.workspace.refresh_policy import daily_due
    at=NOW.replace(hour=16,minute=30)
    assert daily_due(None, None, at)
    assert not daily_due(at-timedelta(minutes=5), at-timedelta(minutes=5), at)
    assert not daily_due(None, at-timedelta(minutes=5), at)
    assert daily_due(None, at-timedelta(minutes=65), at)
    # TaskService writes market-clock time; do not re-interpret naive values as UTC.
    assert not daily_due(at.replace(tzinfo=None), None, at)


def test_historical_comparison_uses_adjacent_cached_bars(db_session):
    from backend.tests.test_v103_history import instrument
    from app.services.decision_board_service import DecisionBoardService
    inst=instrument(db_session, missing_volume=True)
    settings=get_settings().model_copy(update={'market_provider':'akshare'})
    try:
        built=DecisionBoardService(settings).refresh(db_session)
        row=next(r for r in built.payload['rows'] if r['ts_code']==inst.ts_code)
        comp=row['indicator_comparison']
        assert comp['basis']=='adjacent_historical_bars_display_only'
        assert comp['previous_as_of_date'] < comp['as_of_date']
        assert comp['values']['macd_dif']['previous'] is not None
        assert row['actionable'] is False and row['history'][-1]['volume'] is None
    finally:
        db_session.rollback()


def test_admin_data_status_is_read_only_and_no_raw_error_leaks(db_session):
    from app.workspace.data_health import read
    from app.models import TaskRun
    row=TaskRun(run_id='handoff-health-fixture', task_name='refresh_quotes', status='failed',
                started_at=NOW, finished_at=NOW, error='SENSITIVE_TEST_SENTINEL')
    db_session.add(row);db_session.flush()
    try:
        result=read(db_session, get_settings(), now=NOW)
        assert result['provider_called'] is False and result['actionable'] is False
        assert len(result['panels']) >= 9
        assert 'SENSITIVE_TEST_SENTINEL' not in str(result)
        assert not db_session.dirty and not db_session.new
    finally:
        db_session.rollback()


def test_display_endpoint_preserves_original_snapshot_api(bootstrapped):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        original = client.get('/api/market-context').json()['latest_view']
        response = client.get('/api/workspace/market-context')
        assert response.status_code == 200
        result = response.json()
        assert result['provider_called'] is False
        assert response.headers['cache-control'] == 'private, no-store'
        assert [{k:v for k,v in row.items() if k!='display_time'} for row in result['latest_view']] == original


def test_decision_board_endpoint_is_not_cached(bootstrapped):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        response = client.get('/api/decision-board')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'private, no-store'


def test_data_health_keeps_actual_admin_dependency(bootstrapped):
    from fastapi import Request
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models import AuthUser
    from app.core.security import require_private_access
    member=AuthUser(id=99881, username='handoff-role-fixture', role='member', status='active')
    settings=get_settings().model_copy(update={'auth_enabled':True})
    async def resolved_session(request: Request):
        # Only session resolution is injected; real require_admin must still reject members.
        request.state.auth_user=member
    before=dict(app.dependency_overrides)
    app.dependency_overrides[get_settings]=lambda:settings
    app.dependency_overrides[require_private_access]=resolved_session
    try:
        with TestClient(app) as client:
            assert client.get('/api/workspace/data-health').status_code==403
            member.role='admin'
            response=client.get('/api/workspace/data-health')
            assert response.status_code==200
            assert response.json()['provider_called'] is False
    finally:
        app.dependency_overrides.clear();app.dependency_overrides.update(before)
