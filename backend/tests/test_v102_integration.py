"""User journey regressions: original template, member onboarding and discovery."""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.session import session_scope
from app.main import app
from app.models import Instrument
from app.providers.akshare import AKShareProvider
from app.providers.catalog import catalog_records


def test_aliases_lead_to_one_home_and_frame_reuses_original(monkeypatch):
    monkeypatch.setenv('WORKSPACE_UI_ENABLED', 'true')
    with TestClient(app) as client:
        for path in ('/matrix', '/classic/etf-board'):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 307
            assert response.headers['location'] == '/#etf-decisions'
        frame = client.get('/internal/decision-board-frame')
        assert frame.status_code == 200
        assert 'data-workspace-embed' in frame.text
        for marker in ('id="gradeCounters"', 'id="boardArea"', 'decision_board_workbuddy.css', 'decision_board_workbuddy.js'):
            assert marker in frame.text
        assert '<header class="app-topbar"' not in frame.text
        assert 'authLoginForm' not in frame.text
        assert 'frame-ancestors' in frame.headers['content-security-policy']


def test_registration_capabilities_are_safe_and_honest():
    config = Settings(_env_file=None, auth_enabled=True, registration_enabled=True, registration_invite_code='test-only-invite')
    app.dependency_overrides[get_settings] = lambda: config
    try:
        with TestClient(app) as client:
            response = client.get('/api/auth/capabilities')
            assert response.status_code == 200
            assert response.json()['registration_enabled'] is True
            assert response.json()['invite_required'] is True
            assert 'test-only-invite' not in response.text
            assert response.headers['cache-control'] == 'no-store'
    finally:
        app.dependency_overrides.clear()


def test_catalog_search_paginates_nontracked_nonindustry_etfs(bootstrapped):
    from app.workspace.read_model import search_instruments
    marker = 'catalog-' + uuid4().hex[:8]
    with session_scope() as db:
        for i in range(7):
            db.add(Instrument(ts_code=f'59{uuid4().int%10000:04}.SH', symbol=f'59800{i}', name=f'{marker}货币{i}', kind='ETF', enabled=False))
        db.flush()
        a = search_instruments(db, get_settings(), marker, 3, None, offset=0)
        b = search_instruments(db, get_settings(), marker, 3, None, offset=3)
        assert a['total'] == 7 and a['has_more'] is True
        assert set(x['ts_code'] for x in a['items']).isdisjoint(x['ts_code'] for x in b['items'])
        assert all(not x['enabled'] for x in a['items'])
        db.rollback()


def test_akshare_catalog_sina_fallback_keeps_etf_identity_without_name_keyword():
    def offline():
        raise TimeoutError('test source unavailable')
    sdk = SimpleNamespace(fund_etf_spot_em=offline, fund_lof_spot_em=lambda: [],
        fund_etf_category_sina=lambda symbol: [{'代码':'sh511880','名称':'银华日利'}] if symbol=='ETF基金' else [])
    provider = AKShareProvider(Settings(_env_file=None), ak_client=sdk)
    rows = catalog_records(provider)
    assert rows[0].ts_code == '511880.SH' and rows[0].kind == 'ETF'
    assert not rows[0].enabled


def test_zero_sector_return_is_not_missing():
    provider = AKShareProvider(Settings(_env_file=None), ak_client=SimpleNamespace())
    rows = provider._parse_sector_frame([{'板块名称':'平盘行业','涨跌幅':0,'上涨家数':0,'下跌家数':2}], date(2026,9,8), '板块名称')
    assert rows[0].pct_change == 0


def test_empty_sector_class_is_partial_not_success(db_session):
    from app.services.market_service import MarketService
    sdk = SimpleNamespace(name='test', fetch_sector_snapshots=lambda: [], fetch_concept_snapshots=lambda: [], fetch_market_breadth=lambda: None)
    result = MarketService(sdk, get_settings(), persist_provider_audits=False).refresh_sector_snapshots(db_session)
    assert result['status'] == 'partial'
    assert result['boards']['concept']['error'] == 'empty_response'


def test_discovery_routes_reachable_and_enqueue_never_calls_provider(monkeypatch):
    from sqlalchemy import func
    from app.workspace.models import WorkspaceDataJob
    from app.workspace import discovery
    with TestClient(app) as client:
        # GET must remain a read, including on an empty installation.
        with session_scope() as db:
            before = db.scalar(select(func.count()).select_from(WorkspaceDataJob))
        state = client.get('/api/workspace/discovery')
        assert state.status_code == 200 and not state.json()['provider_called']
        with session_scope() as db:
            assert db.scalar(select(func.count()).select_from(WorkspaceDataJob)) == before
        a = client.post('/api/workspace/discovery/refresh')
        b = client.post('/api/workspace/discovery/refresh')
        assert a.status_code == b.status_code == 202
        assert a.json()['jobs'][0]['task'] == 'context'
        assert [x['job_id'] for x in a.json()['jobs']] == [x['job_id'] for x in b.json()['jobs']]
        with session_scope() as db:
            for item in a.json()['jobs']:
                row = db.get(WorkspaceDataJob, item['job_id'])
                if row:
                    db.delete(row)


def test_tushare_dedicated_catalog_does_not_filter_etf_short_names():
    from app.providers.tushare import TushareProvider
    provider = SimpleNamespace(name='tushare', _records=lambda value:value,
        pro=SimpleNamespace(etf_basic=lambda **_: [{'ts_code':'511880.SH','extname':'银华日利','list_status':'L'}], fund_basic=lambda **_:[]))
    rows = catalog_records(provider)
    assert rows[0].ts_code == '511880.SH' and rows[0].kind == 'ETF'
    assert rows.coverage['ETF']['source'] == 'tushare:etf_basic'


def test_catalog_sync_keeps_existing_holdings_and_inactive_research_scope(db_session, monkeypatch):
    from app.workspace import worker
    from app.providers.catalog import CatalogRows
    from app.providers.types import InstrumentRecord
    marker = uuid4().hex
    item = Instrument(ts_code='591997.SH',symbol='591997',name=marker,kind='ETF',enabled=False)
    db_session.add(item);db_session.flush()
    row_id = item.id
    monkeypatch.setattr(worker,'catalog_records',lambda _:CatalogRows([InstrumentRecord(ts_code=item.ts_code,symbol=item.symbol,name='非行业货币ETF',kind='ETF',exchange='SH')],coverage={'ETF':{'source':'fixture','count':1},'LOF':{'source':None,'count':0}}))
    result = worker.sync_catalog(db_session,SimpleNamespace(name='mock'))
    assert item.id == row_id and not item.enabled and item.name == '非行业货币ETF'
    assert result['status'] == 'partial'
    db_session.rollback()
