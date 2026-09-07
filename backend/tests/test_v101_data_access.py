"""Offline contract tests; credentials and live provider access are never assumed."""
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.core.config import Settings
from app.providers.akshare import AKShareProvider
from app.providers.tushare import TushareProvider

TZ = ZoneInfo('Asia/Shanghai')


def test_tushare_daily_uses_shares_yuan_and_keeps_zero_percent():
    calls=[]
    def daily(**kw):
        calls.append(kw)
        return [{'ts_code':'512480.SH','trade_date':'20260904','open':1,'high':2,'low':1,'close':1.2,'vol':20,'amount':2.4,'pct_chg':0}]
    p=TushareProvider(Settings(_env_file=None), pro_client=SimpleNamespace(fund_daily=daily))
    rows=p.fetch_daily_bars('512480.SH',date(2026,9,1),date(2026,9,4))
    assert rows[0].volume == 2000 and rows[0].amount == 2400
    assert rows[0].pct_change == 0 and rows[0].source.endswith(':v101')


def test_tushare_realtime_requests_sh_topic_and_trade_time():
    calls=[]
    def rt(**kw): calls.append(kw); return []
    p=TushareProvider(Settings(_env_file=None),pro_client=SimpleNamespace(rt_etf_k=rt))
    p._call_candidate('rt_etf_k',['512480.SH','159915.SZ'])
    assert len(calls)==2
    assert calls[0]['topic']=='HQ_FND_TICK'
    assert 'trade_time' in calls[0]['fields']
    assert 'topic' not in calls[1]


def test_tushare_never_promotes_bare_clock_to_current_trading_day():
    p=TushareProvider(Settings(_env_file=None),pro_client=SimpleNamespace())
    now=datetime(2026,9,7,14,30,tzinfo=TZ)
    assert p._quote_timestamp({'trade_time':'14:29:59'},now) is None
    assert p._quote_timestamp({'trade_time':'2026-09-07 14:29:59'},now).date()==now.date()


def test_akshare_etf_only_spot_avoids_lof_request_and_fake_time():
    calls=[]
    def etf(): calls.append('etf');return [{'代码':'512480','最新价':1.2,'成交量':20,'成交额':2400,'涨跌幅':0}]
    def lof(): calls.append('lof');raise AssertionError('unrelated all-LOF scan')
    p=AKShareProvider(Settings(_env_file=None),ak_client=SimpleNamespace(fund_etf_spot_em=etf,fund_lof_spot_em=lof))
    q=p.fetch_spot_quotes(['512480.SH'])
    assert calls == ['etf'] and len(q)==1
    assert q[0].volume==2000 and q[0].pct_change==0
    assert q[0].is_realtime is False and q[0].degraded_reason


def test_empty_em_history_uses_sina_and_source_is_visible():
    fake=SimpleNamespace(fund_etf_hist_em=lambda **kw:[],fund_etf_hist_sina=lambda **kw:[{'date':'2026-09-04','open':1,'high':2,'low':1,'close':1.2,'volume':20}])
    p=AKShareProvider(Settings(_env_file=None),ak_client=fake)
    rows=p.fetch_daily_bars('512480.SH',date(2026,9,1),date(2026,9,4))
    assert len(rows)==1 and rows[0].source=='akshare:sina:v101'
    assert rows[0].amount is None


def test_catalog_is_separate_from_light_daily_refresh():
    from app.workspace.worker import task_sequence
    seq=task_sequence('prices',['512480.SH'],420)
    assert 'refresh_bars' in [name for name,_ in seq]
    assert not {'sync_instruments','refresh_news','refresh_market_context','refresh_sector_snapshots'} & {name for name,_ in seq}


def test_worker_detects_degraded_quotes_and_sector_errors():
    from app.workspace.worker import outcome_state
    assert outcome_state({'inserted':2,'degraded':2,'realtime':0})=='partial'
    assert outcome_state({'error':'TimeoutError','boards':{}})=='partial'


def test_network_timeout_is_hard_and_process_is_reaped():
    import multiprocessing,time
    from app.providers.bounded_sdk import bounded_call, ProviderTimeout
    before={p.pid for p in multiprocessing.active_children()}
    started=time.monotonic()
    with pytest.raises(ProviderTimeout): bounded_call('akshare','fund_etf_spot_em',{},timeout=0.001)
    assert time.monotonic()-started < 5
    assert {p.pid for p in multiprocessing.active_children()}==before

@pytest.fixture
def v101_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.base import Base
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


def test_connection_status_is_read_only_and_never_returns_credentials(v101_db):
    import json
    from sqlalchemy import event
    from app.models import RuntimeSetting
    from app.workspace.data_sources import inspect_sources
    token = 'test-only-' + '0'*32
    v101_db.add(RuntimeSetting(key='tushare_token', value_json=token))
    v101_db.add(RuntimeSetting(key='market_data_tier', value_json='complete'))
    v101_db.commit()
    statements=[]
    event.listen(v101_db.get_bind(),'before_cursor_execute',lambda conn,cursor,sql,*args: statements.append(sql))
    result=inspect_sources(v101_db,Settings(_env_file=None).model_copy(update={'market_provider':'composite'}))
    assert result['effective_provider']=='composite'
    assert result['credential_origin']=='legacy_database'
    assert result['sources'][0]['status']=='permission_not_verified'
    assert token not in json.dumps(result) and result['provider_called'] is False
    assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)


def test_catalog_sync_audit_has_required_run_identity(v101_db):
    from app.workspace.worker import sync_catalog
    from app.models import ProviderAudit
    from sqlalchemy import select
    client=SimpleNamespace(fund_basic=lambda **kw:[{'ts_code':'512480.SH','name':'测试ETF'}])
    provider=TushareProvider(Settings(_env_file=None),pro_client=client)
    result=sync_catalog(v101_db,provider)
    assert result['created']==1
    v101_db.flush()
    audit=v101_db.scalar(select(ProviderAudit))
    assert audit is not None and audit.run_id and audit.status=='ok'


def test_legacy_unit_repair_requires_complete_atomic_refetch(v101_db):
    from sqlalchemy import select
    from app.models import Instrument, DailyBar
    from app.providers.types import BarRecord
    from app.services.market_service import MarketService
    from app.providers.data_contract import require_current_history,HistoryContractError
    inst=Instrument(ts_code='512480.SH',symbol='512480',name='测试ETF',kind='ETF',enabled=True)
    v101_db.add(inst);v101_db.flush()
    days=[date(2026,9,3),date(2026,9,4)]
    for day in days:
        v101_db.add(DailyBar(instrument_id=inst.id,trade_date=day,adjust='none',open=1,high=2,low=1,close=1.2,volume=20,amount=2.4,source='tushare:fund_daily',quality_hash='a'*64))
    v101_db.commit()
    settings=Settings(_env_file=None).model_copy(update={'market_provider':'tushare'})
    batch=[BarRecord(ts_code=inst.ts_code,trade_date=days[-1],open=1,high=2,low=1,close=1.2,volume=2000,amount=2400,source='tushare:fund_daily:v101')]
    provider=SimpleNamespace(name='tushare',fetch_daily_bars=lambda *args:batch)
    service=MarketService(provider,settings)
    assert service.refresh_daily_bars(v101_db,lookback_days=1800)['failures']
    assert {row.source for row in v101_db.scalars(select(DailyBar))}=={'tushare:fund_daily'}
    with pytest.raises(HistoryContractError):require_current_history(v101_db,settings)
    batch.insert(0,BarRecord(ts_code=inst.ts_code,trade_date=days[0],open=1,high=2,low=1,close=1.2,volume=2000,amount=2400,source='tushare:fund_daily:v101'))
    assert not service.refresh_daily_bars(v101_db,lookback_days=1800)['failures']
    require_current_history(v101_db,settings)
    assert all(row.volume==2000 and row.amount==2400 for row in v101_db.scalars(select(DailyBar)))


def test_legacy_chart_does_not_display_unrepaired_volume(v101_db):
    from app.models import Instrument, DailyBar
    from app.workspace.read_model import chart_data
    inst=Instrument(ts_code='512480.SH',symbol='512480',name='测试ETF',enabled=True)
    v101_db.add(inst);v101_db.flush()
    v101_db.add(DailyBar(instrument_id=inst.id,trade_date=date(2026,9,4),adjust='none',open=1,high=2,low=1,close=1.2,volume=20,source='akshare',quality_hash='a'*64));v101_db.flush()
    data=chart_data(v101_db,Settings(_env_file=None).model_copy(update={'market_provider':'akshare'}),inst.ts_code,'1d',260)
    assert data['available'] and data['qualification']=='legacy_units_unverified'
    assert data['bars'][0]['close']==1.2 and data['bars'][0]['volume'] is None
    assert not data['sr_overlay_allowed'] and data['bars'][0]['indicators']=={}


def test_tushare_minute_wires_official_freq_and_canonical_units():
    calls=[]
    def minute(**kwargs):
        calls.append(kwargs)
        return [{'ts_code':'512480.SH','trade_time':'2026-09-04 14:30:00','open':1,'high':2,'low':1,'close':1.2,'vol':2000,'amount':2400}]
    p=TushareProvider(Settings(_env_file=None),pro_client=SimpleNamespace(etf_mins=minute))
    bars=p.fetch_minute_bars('512480.SH','30m',date(2026,9,1),date(2026,9,4))
    assert calls[0]['freq']=='30min' and bars[0].volume==2000 and bars[0].amount==2400
    assert bars[0].trade_date.hour==14 and bars[0].source=='tushare:etf_mins:v101'


def test_conflicting_minute_batch_is_rejected_before_database_write(v101_db):
    from app.models import Instrument,MarketBar
    from app.services.market_bar_service import MarketBarService
    from app.providers.types import BarRecord
    from sqlalchemy import select
    inst=Instrument(ts_code='512480.SH',symbol='512480',name='测试ETF');v101_db.add(inst);v101_db.flush()
    now=datetime.now(TZ)
    rows=[BarRecord(ts_code=inst.ts_code,trade_date=now,open=1,high=2,low=1,close=1.2,source='tushare:etf_mins:v101'),BarRecord(ts_code=inst.ts_code,trade_date=now,open=1,high=2,low=1,close=1.3,source='tushare:etf_mins:v101')]
    provider=SimpleNamespace(name='tushare',fetch_minute_bars=lambda *a:rows)
    settings=Settings(_env_file=None).model_copy(update={'minute_bars_enabled':True})
    result=MarketBarService(settings,provider).sync_minute_bars(v101_db,[inst.ts_code])
    assert result['status']=='partial' and v101_db.scalar(select(MarketBar.id)) is None


def test_daily_quote_fallback_does_not_hide_later_current_snapshot():
    from app.providers.composite import CompositeProvider
    from app.providers.types import QuoteRecord
    now=datetime.now(TZ)
    primary=SimpleNamespace(name='tushare',fetch_spot_quotes=lambda codes:[QuoteRecord(ts_code=codes[0],quote_time=now,price=1,source='tushare:fund_daily:v101',degraded_reason='daily_only')])
    secondary=SimpleNamespace(name='akshare',fetch_spot_quotes=lambda codes:[QuoteRecord(ts_code=codes[0],quote_time=now,price=1.2,source='akshare:em:v101',is_realtime=False,degraded_reason='source_timestamp_missing_observed_at_fetch')])
    result=CompositeProvider([primary,secondary]).fetch_spot_quotes(['512480.SH'])
    assert result[0].price==1.2 and not result[0].is_realtime


def test_rss_does_not_invent_publication_time_or_shift_utc_tuple():
    from app.providers.rss_news import RssNewsProvider
    p=object.__new__(RssNewsProvider);p.tz=TZ
    assert p._published_at({}) is None
    assert p._published_at({'published_parsed':(2026,9,4,6,30,0,0,0,0)}).hour==14
    assert p._published_at({'published':'2026-09-04T06:30:00Z'}).hour==14


def test_unknown_listed_fund_is_not_silently_classified_as_etf():
    p=TushareProvider(Settings(_env_file=None),pro_client=SimpleNamespace(fund_basic=lambda **kw:[{'ts_code':'501000.SH','name':'普通基金'}]))
    assert p.resolve_instrument('501000.SH') is None


def test_http_transport_uses_only_fixed_https_and_does_not_echo_error(monkeypatch):
    import httpx,json
    from app.providers.bounded_sdk import _https_query,CapabilityUnavailable
    token='synthetic-not-real-'+'x'*32
    seen=[]
    class Client:
        def __init__(self,**kw):assert kw['follow_redirects'] is False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stream(self,method,url,**kwargs):
            seen.append((method,url))
            return httpx.Response(200,json={'code':-1,'msg':'token '+token},request=httpx.Request('POST',url))
    # httpx.Response has close but is not a context manager in this version.
    from contextlib import contextmanager
    original=Client.stream
    Client.stream=contextmanager(lambda self,*args,**kw:(yield original(self,*args,**kw)))
    monkeypatch.setattr(httpx,'Client',Client)
    with pytest.raises(CapabilityUnavailable) as exc:_https_query('fund_daily',{},token,2)
    assert token not in str(exc.value) and seen==[('POST','https://api.tushare.pro')]


def test_new_source_api_and_original_panel_routes_are_explicit(bootstrapped):
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        value=client.get('/api/workspace/data-sources')
        assert value.status_code==200 and value.json()['provider_called'] is False
        assert 'no-store' in value.headers['Cache-Control']
        classic=client.get('/classic/etf-board')
        assert classic.status_code==200 and 'decision_board_workbuddy.js' in classic.text
        board=client.get('/api/workspace/overview').json()
        assert all('ma' in row and 'td' in row and 'sector' in row for row in board['rows'])
        assert client.get('/api/workspace/does-not-exist').status_code==404


def test_invalid_quote_batch_cannot_write_valid_prefix(v101_db):
    from app.providers.types import QuoteRecord
    from app.models import Instrument, QuoteSnapshot, ProviderAudit
    from app.providers.base import ProviderError
    from app.services.market_service import MarketService
    from sqlalchemy import select
    inst=Instrument(ts_code='512480.SH',symbol='512480',name='测试ETF')
    v101_db.add(inst);v101_db.flush()
    now=datetime.now(TZ)
    rows=[QuoteRecord(ts_code=inst.ts_code,quote_time=now,price=1,source='akshare:em:v101'),
          QuoteRecord(ts_code=inst.ts_code,quote_time=now,price=float('nan'),source='akshare:em:v101')]
    provider=SimpleNamespace(name='akshare',fetch_spot_quotes=lambda codes: rows)
    with pytest.raises(ProviderError, match='quote_price_invalid'):
        MarketService(provider,Settings(_env_file=None)).refresh_quotes(v101_db,[inst.ts_code])
    assert v101_db.scalar(select(QuoteSnapshot.id)) is None
    v101_db.flush()
    assert v101_db.scalar(select(ProviderAudit)).status=='failed'


def test_minute_ingestion_records_fetch_and_rejection_audit(v101_db):
    from app.models import Instrument, ProviderAudit
    from app.services.market_bar_service import MarketBarService
    from sqlalchemy import select
    inst=Instrument(ts_code='512480.SH',symbol='512480',name='测试ETF')
    v101_db.add(inst);v101_db.flush()
    provider=SimpleNamespace(name='tushare',fetch_minute_bars=lambda *args: [])
    settings=Settings(_env_file=None).model_copy(update={'minute_bars_enabled':True})
    out=MarketBarService(settings,provider).sync_minute_bars(v101_db,[inst.ts_code])
    logs=list(v101_db.scalars(select(ProviderAudit)))
    assert out['status']=='partial' and out['run_id']
    assert {row.operation for row in logs}=={'fetch_minute_bars','validate_minute_bars'}
    assert logs[-1].status=='failed' and all(row.run_id==out['run_id'] for row in logs)


def test_tushare_composite_skips_serial_daily_fetch_before_other_quotes():
    from app.providers.composite import CompositeProvider
    from app.providers.types import QuoteRecord
    calls=[]
    def daily(**kw): calls.append(kw); raise AssertionError('unrelated slow daily loop')
    primary=TushareProvider(Settings(_env_file=None),pro_client=SimpleNamespace(rt_etf_k=lambda **kw:[],fund_daily=daily))
    secondary=SimpleNamespace(name='akshare',fetch_spot_quotes=lambda codes:[QuoteRecord(ts_code=code,quote_time=datetime.now(TZ),price=1,source='akshare:em:v101') for code in codes])
    out=CompositeProvider([primary,secondary]).fetch_spot_quotes(['510300.SH','512480.SH'])
    assert len(out)==2 and calls==[]


def test_sina_price_only_is_not_zero_volume_shared_signal_input(v101_db):
    from app.models import DailyBar,Instrument
    from app.providers.data_contract import require_current_history,HistoryContractError
    from app.workspace.worker import outcome_state
    inst=Instrument(ts_code='512480.SH',symbol='512480',name='测试ETF',enabled=True)
    v101_db.add(inst);v101_db.flush()
    v101_db.add(DailyBar(instrument_id=inst.id,trade_date=date(2026,9,4),adjust='none',open=1,high=2,low=1,close=1.2,volume=None,source='akshare:sina:v101',quality_hash='b'*64));v101_db.flush()
    with pytest.raises(HistoryContractError,match='price_only'):
        require_current_history(v101_db,Settings(_env_file=None).model_copy(update={'market_provider':'akshare'}))
    assert outcome_state({'price_only':1,'instruments':1})=='partial'


def test_live_launcher_ignores_unrelated_demo_environment(tmp_path,monkeypatch):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('v101_live',Path(__file__).resolve().parents[2]/'scripts/run_workspace_live.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    config=tmp_path/'private.env';config.write_text('AKSHARE_TIMEOUT_SECONDS=8\n');config.chmod(0o600)
    monkeypatch.setenv('MARKET_PROVIDER','mock');monkeypatch.setenv('MINUTE_BARS_ENABLED','true')
    env,root=module.prepare(config,tmp_path/'data')
    assert env['MARKET_PROVIDER']=='public_composite' and env['MINUTE_BARS_ENABLED']=='false'
    assert env['AUTH_ENABLED']=='true' and env['AUTO_CREATE_SCHEMA']=='false'
    assert root.is_dir() and 'mock' not in env['MARKET_PROVIDER']


def test_live_launcher_allows_explicit_local_registration_only_with_invite(tmp_path):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('v101_live_registration',Path(__file__).resolve().parents[2]/'scripts/run_workspace_live.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    config=tmp_path/'private.env'
    config.write_text('REGISTRATION_ENABLED=true\nREGISTRATION_INVITE_CODE=local-test-invite\n')
    config.chmod(0o600)
    env,_=module.prepare(config,tmp_path/'data')
    assert env['REGISTRATION_ENABLED']=='true'
    assert env['REGISTRATION_INVITE_CODE']=='local-test-invite'


def test_price_only_history_can_be_repaired_when_full_volume_source_recovers(v101_db):
    from app.models import DailyBar,Instrument
    from app.providers.types import BarRecord
    from app.services.market_service import MarketService
    from app.providers.data_contract import require_current_history
    from sqlalchemy import select
    inst=Instrument(ts_code='512480.SH',symbol='512480',name='测试ETF',enabled=True)
    v101_db.add(inst);v101_db.flush()
    old=date(2022,1,4)
    v101_db.add(DailyBar(instrument_id=inst.id,trade_date=old,adjust='none',open=1,high=2,low=1,close=1.2,volume=None,source='akshare:sina:v101',quality_hash='c'*64));v101_db.flush()
    seen=[]
    def recovered(code,start,end):
        seen.append(start)
        return [BarRecord(ts_code=code,trade_date=old,open=1,high=2,low=1,close=1.2,volume=2000,amount=2400,source='tushare:fund_daily:v101')]
    settings=Settings(_env_file=None).model_copy(update={'market_provider':'composite'})
    out=MarketService(SimpleNamespace(name='tushare',fetch_daily_bars=recovered),settings).refresh_daily_bars(v101_db,lookback_days=420)
    assert not out['failures'] and seen[0]<=old
    assert v101_db.scalar(select(DailyBar)).volume==2000
    require_current_history(v101_db,settings)


def test_worker_keeps_supervising_job_when_sqlite_heartbeat_is_busy(monkeypatch):
    from app.workspace import worker
    from sqlalchemy.exc import OperationalError
    polls=iter([None,0,0]);seen=[]
    process=SimpleNamespace(poll=lambda:next(polls),pid=54321)
    def busy():seen.append('attempted');raise OperationalError('test',{},Exception('database is locked'))
    monkeypatch.setattr(worker,'heartbeat',busy);monkeypatch.setattr(worker.time,'sleep',lambda _:None)
    monkeypatch.setattr(worker,'STOP',False)
    worker.monitor_job(process)
    assert seen==['attempted']


def test_worker_unexpected_monitor_error_still_cleans_owned_child(monkeypatch):
    from app.workspace import worker
    called=[]
    process=SimpleNamespace(poll=lambda:None,pid=54321)
    def broken():raise ValueError('synthetic monitor error')
    monkeypatch.setattr(worker,'heartbeat',broken)
    monkeypatch.setattr(worker,'stop_job_process',lambda p: called.append(p.pid))
    monkeypatch.setattr(worker,'STOP',False)
    with pytest.raises(ValueError):worker.monitor_job(process)
    assert called==[54321]


def test_coverage_does_not_label_unverified_fetch_as_source_time(v101_db):
    from app.models import Instrument, QuoteSnapshot
    from app.workspace.data_sources import inspect_sources
    inst=Instrument(ts_code='512480.SH',symbol='512480',name='测试ETF',enabled=True)
    v101_db.add(inst);v101_db.flush()
    observed=datetime(2026,9,4,15,0,tzinfo=TZ)
    v101_db.add(QuoteSnapshot(instrument_id=inst.id,quote_time=observed,fetched_at=observed,
        timestamp_verified=False,price=1.2,source='akshare',is_realtime=False,
        degraded_reason='source_timestamp_missing_observed_at_fetch',quality_hash='a'*64))
    v101_db.flush()
    coverage=inspect_sources(v101_db,Settings(_env_file=None))['coverage']['quotes'][0]
    assert coverage['last_source_time'] is None
    assert coverage['last_fetch_time'] is not None
