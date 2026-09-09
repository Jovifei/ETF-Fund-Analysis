from datetime import date
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from app.models import Instrument
from app.providers.catalog import catalog_records
from app.workspace.catalog_search import search_terms
from app.workspace.read_model import search_instruments
from app.core.config import get_settings

def test_sector_aliases_separate_nonmetal_from_nonferrous():
    terms, info=search_terms("非金属")
    assert "建材" in terms and "有色" not in terms
    assert info["method"]=="sector_alias"
    assert "半导体" in search_terms("元器件")[0]

def test_related_search_keeps_nontracked_catalog_and_benchmark(db_session):
    db=db_session
    a=Instrument(ts_code="599941.SH",symbol="599941",name="电子研究ETF",kind="ETF",enabled=False,metadata_json={"market_cap_cny":8e8})
    b=Instrument(ts_code="599942.SH",symbol="599942",name="新产品",kind="ETF",enabled=False,benchmark="中证半导体指数")
    db.add_all([a,b]);db.flush()
    result=search_instruments(db,get_settings(),"元器件",100,None)
    assert {"599941.SH","599942.SH"} <= {x["ts_code"] for x in result["items"]}
    assert result["provider_called"] is False
    assert not a.enabled and not b.enabled
    result=search_instruments(db,get_settings(),"元器件",100,None,min_scale=5e8,include_unknown=False)
    assert {x["ts_code"] for x in result["items"]}=={"599941.SH"}
    db.rollback()

def test_small_primary_catalog_uses_ths_category_instead_of_giving_up():
    calls=[]
    def empty(**kwargs): calls.append(kwargs);return []
    def ths(**kwargs):
        if kwargs['symbol']=='LOF': return []
        return [{'基金代码':str(510000+i),'基金名称':f'完整目录{i}'} for i in range(120)]
    ak=SimpleNamespace(fund_etf_spot_em=lambda: [{'代码':'510000','名称':'首选简称'}],fund_lof_spot_em=empty,fund_etf_category_sina=empty,fund_etf_category_ths=ths)
    rows=catalog_records(SimpleNamespace(name='akshare',ak=ak,_records=lambda x:x))
    assert len(rows)==120 and rows.coverage['ETF']['source'].endswith('fund_etf_category_ths')
    assert rows[0].name=='首选简称'
    assert all(not row.enabled for row in rows)

def test_prepare_plan_is_read_only_and_unknown_sizes_are_last(db_session):
    from app.workspace.storage import prepare_plan
    db_session.add_all([Instrument(ts_code='599991.SH',symbol='599991',name='tiny',kind='ETF',enabled=False,metadata_json={}), Instrument(ts_code='599992.SH',symbol='599992',name='large',kind='ETF',enabled=False,metadata_json={'market_cap_cny':1e12})]);db_session.flush()
    result=prepare_plan(db_session,limit=1)
    assert result['codes']==['599992.SH'] and not result['writes']
    assert not db_session.scalar(select(Instrument).where(Instrument.ts_code=='599992.SH')).enabled
    db_session.rollback()
