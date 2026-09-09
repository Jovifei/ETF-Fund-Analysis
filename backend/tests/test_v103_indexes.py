from datetime import date, timedelta, datetime, UTC
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.core.config import get_settings
from app.providers.index_history import decode, tushare_index, akshare_index
from app.providers.base import ProviderError
from app.providers.types import BarRecord
from app.models import MarketContextRegistry
from app.workspace.models import WorkspacePreference
from app.workspace import index_history
from app.workspace.worker import bounded_step_summary


def test_index_decoder_rejects_close_only_or_wrong_identity():
    with pytest.raises(ProviderError):
        decode([{'date':'2026-09-01','close':3000}], 'sh000300',date(2026,1,1),date(2026,9,8),'test')
    with pytest.raises(ProviderError):
        decode([{'ts_code':'000001.SH','trade_date':'20260901','open':1,'close':1,'high':1,'low':1}],
               'sh000300',date(2026,1,1),date(2026,9,8),'test',tushare=True)


def test_tushare_index_identity_units_and_dates():
    def call(**kw):
        assert kw['ts_code']=='000985.CSI'
        return [{'ts_code':'000985.CSI','trade_date':'20260901','open':3000,'close':3001,'high':3020,'low':2990,'vol':3,'amount':5}]
    p=SimpleNamespace(pro=SimpleNamespace(index_daily=call),_records=lambda x:x)
    bar=tushare_index(p,'sh000985',date(2026,1,1),date(2026,9,8))[0]
    assert bar.volume==300 and bar.amount==5000 and bar.trade_date==date(2026,9,1)


def test_cache_is_durable_idempotent_and_failure_preserves_history(db_session):
    db=db_session; ident='test-index-'+uuid4().hex[:8]
    registry=MarketContextRegistry(context_id=ident,label='测试指数',region='CN',context_kind='index',
        source_symbol='sh000001',is_tradable_proxy=False,enabled=True,display_order=999,
        verification_status='verified',source_priority=['test'],freshness_rule='test')
    db.add(registry);db.flush()
    class Provider:
        name='test'
        fail=False
        def fetch_index_bars(self,symbol,start,end):
            if self.fail: raise TimeoutError('must not be echoed')
            return [BarRecord(symbol,end-timedelta(days=i),3000,3010,2990,3001,source='test') for i in range(5)]
    p=Provider();settings=get_settings()
    index_history.refresh(db,settings,p,uuid4().hex)
    value=index_history.read(db,settings,ident)
    assert value['available'] and len(value['bars'])==5
    assert value['summary']['change_ratio']==0 and value['actionable'] is False
    before=value['data_hash'];p.fail=True
    result=index_history.refresh(db,settings,p,uuid4().hex)
    assert result['status']=='partial'
    assert index_history.read(db,settings,ident)['data_hash']==before
    # Read does not touch the provider, and never synthesizes OHLC from point history.
    assert value['bars'][-1]['open']==3000
    cache=db.get(WorkspacePreference,index_history.PREFIX+ident)
    cache.settings_json={**cache.settings_json,'data_hash':'a'*64};db.flush()
    assert index_history.read(db,settings,ident)['available'] is False
    db.rollback()


def test_worker_keeps_only_bounded_sanitized_index_failures():
    outcome = {
        'status': 'partial',
        'instruments': 2,
        'requested': 3,
        'failures': [
            {'context_id': 'cn-csi-all', 'reason': 'CapabilityUnavailable', 'raw': 'token=do-not-store'},
            {'context_id': 'BAD/ID', 'reason': 'ProviderError: secret=do-not-store'},
        ],
    }
    summary = bounded_step_summary(outcome)
    assert summary['failures'] == [{'context_id': 'cn-csi-all', 'reason': 'CapabilityUnavailable'}]
    assert 'raw' not in summary
