from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.models import DailyBar, Instrument, IndicatorSnapshot, ForecastSnapshot
from app.workspace import data_health, read_model, research_outlook
from app.utils.hashing import stable_hash


@pytest.fixture
def isolated():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        inst=Instrument(ts_code='998871.SH',symbol='998871',name='read fixture',kind='ETF',enabled=True)
        db.add(inst);db.flush()
        yield db,inst
    engine.dispose()


def bar(db,inst,day,close=2.):
    obj=DailyBar(instrument_id=inst.id,trade_date=day,open=close,high=close*1.01,low=close*.99,
        close=close,volume=100.,amount=200.,source='akshare:em:v101',adjust='none',quality_hash='fixture')
    db.add(obj);db.flush();return obj


def test_detail_rejects_old_version_instead_of_showing_it_as_current(isolated,monkeypatch):
    db,inst=isolated;day=date(2026,9,14);bar(db,inst,day)
    db.add(IndicatorSnapshot(instrument_id=inst.id,as_of_date=day,version='old',values_json={'rsi14':99},
        technical_score=50.,risk_score=50.,trend_label='fixture',data_quality=1.,input_hash='x'*64))
    db.add(ForecastSnapshot(instrument_id=inst.id,as_of_date=day,horizon=1,model_version='old',
        input_hash='x'*64,expected_return=.75))
    db.flush()
    monkeypatch.setattr(read_model,'chart_data',lambda *a,**k:{'bars':[{'date':day.isoformat(),'close':2.,'source':'fixture','indicators':{'rsi14':50}}]})
    monkeypatch.setattr(read_model,'holdings_view',lambda *a,**k:{'items':[]})
    result=read_model.instrument_detail(db,get_settings(),inst.ts_code,None)
    assert result['forecasts']=={}
    assert result['indicator_values']['rsi14']==50
    assert 'indicator_version_mismatch' in result['snapshot_issues']['indicator']
    assert result['indicator_basis']=='historical_price_display'


def test_health_reports_target_coverage_not_just_max_date(isolated):
    db,inst=isolated
    second=Instrument(ts_code='998872.SH',symbol='998872',name='older',kind='ETF',enabled=True)
    db.add(second);db.flush()
    bar(db,inst,date(2026,9,14));bar(db,second,date(2026,9,11))
    now=datetime(2026,9,14,16,0,tzinfo=get_settings().timezone)
    result=data_health.read(db,get_settings(),now=now)
    daily=next(p for p in result['panels'] if p['key']=='daily')
    assert daily['target_trade_date']=='2026-09-14'
    assert daily['target_covered_instruments']==1
    assert daily['target_missing_instruments']==1
    assert daily['covered_instruments']==2


def test_research_cache_invalidated_on_same_day_revision(isolated,monkeypatch):
    from app.workspace.models import WorkspacePreference
    db,inst=isolated;row=bar(db,inst,date(2026,9,11))
    settings=get_settings()
    rows=research_outlook.input_rows(db,inst.id)
    cached=research_outlook.compute(rows,settings)
    # A valid empty/short research cache still has version + input identity.
    db.add(WorkspacePreference(owner_scope=research_outlook.PREFIX+inst.ts_code,user_id=None,
        settings_json={**cached,'ts_code':inst.ts_code}))
    db.flush()
    assert research_outlook.read(db,[inst.ts_code],settings)[inst.ts_code]['cache_status']=='input_matched'
    row.close=2.01;db.flush()
    result=research_outlook.read(db,[inst.ts_code],settings)[inst.ts_code]
    assert result['cache_status']=='invalidated'
    assert result['forecasts']=={}


def test_portfolio_correlation_rejects_unexplained_split(isolated,monkeypatch):
    db,inst=isolated
    other=Instrument(ts_code='998872.SH',symbol='998872',name='peer',kind='ETF',enabled=True)
    db.add(other);db.flush()
    for i in range(55):
        day=date(2025,1,1)+timedelta(days=i)
        bar(db,inst,day,(2+i*.001) / (3 if i>30 else 1))
        bar(db,other,day,2+i*.002)
    monkeypatch.setattr(read_model,'holdings_view',lambda *a,**k:{'items':[
        {'ts_code':inst.ts_code,'weight':.5,'theme':'test'},
        {'ts_code':other.ts_code,'weight':.5,'theme':'test'}], 'pricing_complete':True})
    result=read_model.portfolio_risk(db,get_settings(),None)
    assert result['history_issues'][inst.ts_code]=='unexplained_price_discontinuity'
    assert result['correlations'][0]['correlation'] is None
