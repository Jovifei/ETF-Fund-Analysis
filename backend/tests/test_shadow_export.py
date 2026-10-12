from datetime import datetime,timezone,timedelta
import pytest
from app.workspace.shadow_export import local_settings,export_local,ROW_FIELDS
from app.workspace.shadow_bundle import ShadowStore
from app.workspace import shadow_schedule
from app.workspace.shadow_client import upload_bundle

@pytest.fixture(autouse=True)
def isolate_decision_board_snapshots(db_session):
    from app.models import DecisionBoardSnapshot
    from sqlalchemy import delete
    db_session.execute(delete(DecisionBoardSnapshot))
    db_session.commit()
    yield

def test_db_guard_and_public_export(database,bootstrapped,db_session,tmp_path):
    from app.core.config import get_settings
    from app.services.task_service import TaskService
    from app.utils.hashing import stable_hash
    settings=get_settings();TaskService(settings).run(db_session,'refresh_decision_board');db_session.commit()
    value=export_local(settings,sequence=1,code_sha='a'*40)
    assert all(set(row)<=ROW_FIELDS for row in value['blobs']['board']['rows'])
    assert all('holdings' not in row and 'avg_cost' not in row for row in value['blobs']['board']['rows'])
    store=ShadowStore(tmp_path/'receiver',code_sha='a'*40,config_hash=stable_hash(settings.load_strategy()))
    receipt=store.publish(value);result=store.read()
    assert result['bundle_id']==receipt['bundle_id']
    assert set(result['charts'])=={row['ts_code'] for row in result['board']['rows']}
    with pytest.raises(ValueError):local_settings(tmp_path,tmp_path/'production.sqlite3')

def test_calendar_bounded(monkeypatch):
    from types import SimpleNamespace
    class Calendar:
        def __init__(self,settings):pass
        def decision(self,date):return SimpleNamespace(verified=True,is_trade_day=True)
    monkeypatch.setattr(shadow_schedule,'TradingCalendarService',Calendar)
    now=datetime(2026,10,12,6,30,tzinfo=timezone.utc)
    assert shadow_schedule.due_slot(None,now).endswith('14:30')
    assert shadow_schedule.due_slot(None,now+timedelta(minutes=3)) is None
    with pytest.raises(ValueError):shadow_schedule.due_slot(None,now,('16:00',))

def test_https_client_never_accepts_insecure_url(monkeypatch):
    monkeypatch.setenv('SHADOW_PRODUCER_TOKEN','x'*32)
    for url in ['http://example.com/api/shadow/sync','https://user:pass@example.com/api/shadow/sync','https://example.com/api/shadow/sync?token=abc']:
        with pytest.raises(ValueError):upload_bundle(url,{})

def test_export_https_transport_real_cookie_same_manifest(database,bootstrapped,db_session,tmp_path,monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from app.main import app
    from app.core.config import get_settings
    from app.services.task_service import TaskService
    from app.services.auth_service import AuthService
    from app.workspace import shadow_api
    from app.workspace.shadow_bundle import digest
    settings=get_settings();TaskService(settings).run(db_session,'refresh_decision_board');db_session.commit()
    value=export_local(settings,sequence=101,code_sha='a'*40)
    receiver=settings.model_copy(update={'auth_enabled':True,'auth_cookie_secure':False,'shadow_sync_enabled':True,'shadow_sync_root':str(tmp_path/'remote'),'shadow_sync_code_sha':'a'*40,'shadow_sync_config_hash':value['manifest']['config_hash'],'shadow_sync_producer_token':SecretStr('z'*32),'shadow_sync_active_key_id':'test-1','shadow_sync_signing_secret':SecretStr('s'*32)})
    AuthService().create_user(db_session,username='shadow-reader',email='shadow@example.test',password='offline synthetic strong password',role='member');db_session.commit()
    app.dependency_overrides[get_settings]=lambda:receiver
    monkeypatch.setattr(shadow_api,'get_settings',lambda:receiver)
    monkeypatch.setenv('SHADOW_PRODUCER_TOKEN','z'*32)
    monkeypatch.setenv('SHADOW_SIGNING_KEY_ID','test-1')
    monkeypatch.setenv('SHADOW_SIGNING_SECRET','s'*32)
    try:
        client=TestClient(app)
        class Response:
            def __init__(self,response):self.response=response
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,size):return self.response.content[:size]
        def transport(request,**kwargs):
            response=client.post('/api/shadow/sync',content=request.data,headers=dict(request.header_items()))
            assert response.status_code==200,response.text
            return Response(response)
        receipt=upload_bundle('https://receiver.example/api/shadow/sync',value,opener=transport)
        assert client.get('/api/shadow/bundle',headers={'Authorization':'Bearer '+'z'*32}).status_code==401
        login=client.post('/api/auth/login',json={'identifier':'shadow-reader','password':'offline synthetic strong password'})
        assert login.status_code==200,login.text
        response=client.get('/api/shadow/bundle');assert response.status_code==200,response.text
        actual=response.json();assert actual['bundle_id']==receipt['bundle_id']==digest(value['manifest'])
        for part in ['board','charts','market']:assert digest(actual[part])==value['manifest']['parts'][part]
        assert actual['supported_intervals']==['1d']
        chart=next(chart for chart in actual['charts'].values() if chart['bars'])
        assert 'ma5' in chart['research_bars'][-1]['indicators']
        assert chart['studies']['levels']
        assert chart['qualification']=='UNKNOWN' and chart['cost_overlay_allowed'] is False
        assert 'avg_cost' not in str(chart) and 'holdings' not in str(chart)
        assert response.headers['cache-control']=='private, no-store'
    finally:app.dependency_overrides.pop(get_settings,None)


def test_public_chart_keeps_indicators_levels_and_basis_without_cost():
    from app.workspace.shadow_projection import project_chart
    source={'bars':[{'date':'2026-10-10','close':10,'indicators':{'ma5':9,'rsi14':52},'avg_cost':8}], 'research_bars':[{'date':'2026-10-10','close':10,'indicators':{'ma5':9}}], 'studies':{'levels':[{'price':9,'kind':'support','methods':['MA5']}],'nearest_support':{'price':9},'cost_overlay':8},'research_price_basis':'research','display_price_basis':'raw','cost':8}
    result=project_chart(source)
    assert result['bars'][0]['indicators']['ma5']==9
    assert result['studies']['levels'][0]['price']==9
    assert result['research_price_basis']=='research'
    assert result['cost_overlay_allowed'] is False
    assert 'cost' not in result and 'avg_cost' not in result['bars'][0]

def test_mock_collection_precedes_compute_without_live_fetch(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from app.workspace.shadow_export import compute_local
    import app.services.task_service as tasks
    calls=[]
    class Spy:
        def __init__(self,settings):assert settings.market_provider=='mock'
        def run(self,db,task,**kwargs):calls.append((task,kwargs));return {'status':'succeeded'}
        def close(self):pass
    monkeypatch.setattr(tasks,'TaskService',Spy)
    from datetime import date
    monkeypatch.setattr('app.services.settlement.settled_session', lambda _settings: date(2026, 10, 9))
    settings=SimpleNamespace(app_env='test',market_provider='mock',database_url='sqlite:///'+(tmp_path/'research.sqlite3').as_posix())
    compute_local(settings)
    assert [task for task,_ in calls]==['refresh_bars','refresh_quotes','refresh_sector_snapshots','refresh_indicators','refresh_forecasts','refresh_signals','refresh_decision_board']
    assert calls[0][1]=={'lookback_days':420, 'mock_settled_date':date(2026, 10, 9)}

def test_offline_full_mock_quotes_remain_partial_but_displayable():
    from app.workspace.shadow_export import offline_result_ready
    result={'status':'partial','requested':35,'received':35,'missing':0,'degraded':35,'realtime':0}
    assert offline_result_ready('refresh_quotes',result)
    assert result['status']=='partial'
    assert not offline_result_ready('refresh_quotes',{**result,'missing':1})
    assert not offline_result_ready('refresh_forecasts',result)
    assert not offline_result_ready('refresh_quotes',{**result,'status':'failed'})
