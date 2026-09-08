"""Partial name-based catalogs must not stop full-category source fallback."""
from types import SimpleNamespace
from app.providers.catalog import catalog_records
from app.providers.composite import CompositeProvider


def sources():
    def denied(**kwargs):
        raise PermissionError("fixture-only permission failure")
    primary = SimpleNamespace(name='tushare',_records=lambda value:value,
        pro=SimpleNamespace(etf_basic=denied,fund_basic=lambda **_:[{'ts_code':'510300.SH','name':'沪深300ETF'}]))
    secondary = SimpleNamespace(name='akshare',_records=lambda value:value,
        ak=SimpleNamespace(fund_etf_spot_em=lambda:[{'代码':'511880','名称':'银华日利'}],
            fund_lof_spot_em=lambda:[],fund_etf_category_sina=lambda **_:[]))
    return primary, secondary


def test_name_only_catalog_continues_audited_fallback():
    provider=CompositeProvider(list(sources()))
    rows=catalog_records(provider)
    assert {row.ts_code for row in rows} == {'510300.SH','511880.SH'}
    assert all(row.enabled is False for row in rows)
    assert rows.coverage['ETF']['source']=='akshare:fund_etf_spot_em'
    assert provider.last_trace[0].status=='partial'
    assert provider.last_trace[1].status=='fallback_used'


def test_name_fallback_is_preserved_but_never_certified_when_all_others_fail():
    primary, secondary=sources()
    secondary.ak.fund_etf_spot_em=lambda:[]
    provider=CompositeProvider([primary,secondary])
    rows=catalog_records(provider)
    assert len(rows)==1 and rows[0].ts_code=='510300.SH'
    assert rows.coverage['ETF']['source'] is None
    assert provider.last_trace[0].status=='partial'


def test_empty_dedicated_etf_catalog_is_missing_not_success():
    primary,_=sources()
    primary.pro.etf_basic=lambda **_:[]
    rows=catalog_records(primary)
    assert rows.coverage['ETF']['source'] is None
