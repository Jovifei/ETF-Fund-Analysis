"""Read-model regressions from the September 14 audit; no provider or production DB."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
import math

import pandas as pd
import pytest
from sqlalchemy import create_engine, event, insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.models import DailyBar, Instrument, QuoteSnapshot, DecisionBoardSnapshot
from app.services.decision_board_service import DecisionBoardService
from app.services.support_resistance_service import SupportResistanceService


@pytest.fixture
def isolated():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        inst=Instrument(ts_code='998801.SH',symbol='998801',kind='ETF',name='fixture',enabled=True)
        db.add(inst);db.flush()
        yield db, inst
    engine.dispose()


def add_bar(db, inst, day=date(2026,9,14), **kw):
    row=DailyBar(instrument_id=inst.id,trade_date=day,open=2.,high=2.1,low=1.9,close=2.,
                 volume=100.,amount=200.,source='akshare:em:v101',adjust='none',quality_hash='fixture')
    for k,v in kw.items():setattr(row,k,v)
    db.add(row);db.flush()
    return row


def test_sr_is_read_not_silently_lost_to_static_self_error(isolated,monkeypatch):
    db,inst=isolated;add_bar(db,inst)
    service=DecisionBoardService()
    expected={'nearest_support':{'price':1.9},'nearest_resistance':{'price':2.1}}
    monkeypatch.setattr(service.support_resistance,'latest',lambda *a:expected)
    monkeypatch.setattr(service.support_resistance,'latest_or_compute',lambda *a:expected)
    _,levels=service._history_and_levels(db,inst.id)
    assert levels == expected
    assert not db.new and not db.dirty


@pytest.mark.parametrize('horizon',[1,3,5,10])
def test_read_projection_keeps_anomaly_counts(horizon):
    payload={'rows':[{'ts_code':'998801.SH','grade':'数据异常'}]}
    result=DecisionBoardService._select_horizon(payload,horizon)
    assert result['counts']['数据异常']==1
    assert sum(result['counts'].values())==len(result['rows'])
    assert DecisionBoardService._empty_payload(horizon)['counts']['数据异常']==0


def test_quote_fetch_time_cannot_hide_yesterdays_source_time():
    now=datetime(2026,9,14,14,30,tzinfo=get_settings().timezone)
    quote=SimpleNamespace(quote_time=now-timedelta(days=1),fetched_at=now,
                          timestamp_verified=True,is_realtime=True,degraded_reason=None)
    state,reason=DecisionBoardService._status(object(),quote,now)
    assert state=='stale' and reason=='quote_stale_at_snapshot_generation'


def test_missing_forecasts_do_not_mean_ten_flat_future_candles():
    assert DecisionBoardService._forecast_scenario([{'date':'2026-09-14','close':2.}],{})==[]


def test_old_forecast_cannot_be_rebased_onto_new_close():
    forecasts={'1':{'as_of_date':'2026-09-11','expected_return':.03}}
    assert DecisionBoardService._forecast_scenario([{'date':'2026-09-14','close':2.}],forecasts)==[]


def test_partial_forecast_stops_at_last_real_anchor():
    forecasts={'3':{'as_of_date':'2026-09-14','expected_return':.03,'model_version':'v1'}}
    result=DecisionBoardService._forecast_scenario([{'date':'2026-09-14','close':2.}],forecasts)
    assert len(result)==3
    assert result[-1]['close']==pytest.approx(2.06)
    assert result[0]['is_forecast'] is True


def test_latest_query_materializes_only_latest_enabled_records(isolated):
    db,inst=isolated
    disabled=Instrument(ts_code='998802.SH',symbol='998802',kind='ETF',name='disabled',enabled=False)
    db.add(disabled);db.flush()
    start=datetime(2026,9,14,10,0,tzinfo=get_settings().timezone)
    db.execute(insert(QuoteSnapshot),[{'instrument_id':ident,'quote_time':start+timedelta(seconds=i),
               'price':2.,'source':'fixture','quality_hash':'fixture'} for ident in (inst.id,disabled.id) for i in range(120)])
    loaded=[]
    def onload(row,ctx):loaded.append(row.id)
    event.listen(QuoteSnapshot,'load',onload)
    try:
        result=DecisionBoardService._latest_by_instrument(db,QuoteSnapshot,QuoteSnapshot.quote_time,QuoteSnapshot.id)
    finally:event.remove(QuoteSnapshot,'load',onload)
    assert set(result)=={inst.id}
    assert len(loaded)==1


def test_pruning_projects_identifiers_not_snapshot_json(isolated):
    db,_=isolated
    now=datetime(2026,9,14,15,30,tzinfo=get_settings().timezone)
    db.execute(insert(DecisionBoardSnapshot),[{'snapshot_id':str(i),'generated_at':now-timedelta(days=i),
       'next_refresh_at':now,'freshness':'stale','payload_json':{'large':'x'*1000}} for i in range(50)])
    loaded=[]
    def onload(row,ctx):loaded.append(row.id)
    event.listen(DecisionBoardSnapshot,'load',onload)
    try:DecisionBoardService()._prune_snapshot_dates(db)
    finally:event.remove(DecisionBoardSnapshot,'load',onload)
    assert loaded==[]


def test_sr_preserves_unknown_and_true_zero_amount(isolated):
    db,inst=isolated
    add_bar(db,inst,day=date(2026,9,11),volume=None,amount=None)
    add_bar(db,inst,amount=0.)
    frame=SupportResistanceService()._sr_frame(db,inst.id)
    assert pd.isna(frame.iloc[0]['volume']) and pd.isna(frame.iloc[0]['amount'])
    assert frame.iloc[1]['amount']==0.


def test_snapshot_contract_rejects_old_versions_without_rewriting_them():
    from app.services.snapshot_contract import snapshot_issues
    s=get_settings();cfg=s.load_strategy()
    row=SimpleNamespace(version='old',feature_schema_version=cfg['feature_schema_version'],
                        config_hash='wrong',as_of_date=date(2026,9,11))
    issues=snapshot_issues(row,s,date(2026,9,14),kind='indicator')
    assert {'indicator_version_mismatch','indicator_config_mismatch','indicator_date_mismatch'} <= set(issues)
    assert row.version=='old'



def test_sr_does_not_reuse_a_snapshot_after_a_same_day_price_revision(isolated):
    db,inst=isolated
    bar=add_bar(db,inst)
    service=SupportResistanceService()
    service.compute(db,inst.id)
    assert service.latest(db,inst.id) is not None
    bar.close=2.05;db.flush()
    assert service.latest(db,inst.id) is None


def test_daily_close_wins_over_an_old_quote_and_labels_the_return_date(isolated):
    from app.services.return_observation import observed_returns
    db,inst=isolated
    add_bar(db,inst,day=date(2026,9,10),close=1.95,open=1.95,pre_close=1.9)
    add_bar(db,inst,day=date(2026,9,11),close=2.,pre_close=1.95)
    add_bar(db,inst,pre_close=2.,close=2.1)
    now=datetime(2026,9,14,16,0,tzinfo=get_settings().timezone)
    quote=SimpleNamespace(quote_time=now-timedelta(days=3),fetched_at=now,pct_change=-12.,degraded_reason=None)
    value=observed_returns(db,get_settings(),inst.id,quote,now)
    assert value['value']==pytest.approx(.05)
    assert value['as_of_date']=='2026-09-14' and value['basis']=='confirmed_daily_close'
    assert value['previous_as_of_date']=='2026-09-11'


def test_quote_without_a_source_timestamp_does_not_become_today(isolated):
    from app.services.return_observation import observed_returns
    db,inst=isolated
    add_bar(db,inst,day=date(2026,9,11),pre_close=1.95)
    now=datetime(2026,9,14,14,30,tzinfo=get_settings().timezone)
    quote=SimpleNamespace(quote_time=now,fetched_at=now,pct_change=10.,
        degraded_reason='source_timestamp_missing_observed_at_fetch')
    value=observed_returns(db,get_settings(),inst.id,quote,now)
    assert value['as_of_date']=='2026-09-11' and value['target_trade_date']=='2026-09-14'


def test_legacy_board_is_explained_without_mutating_the_saved_record(isolated):
    db, inst = isolated
    now = datetime(2026, 9, 14, 16, 0, tzinfo=get_settings().timezone)
    snapshot = DecisionBoardSnapshot(snapshot_id='legacy-board', generated_at=now,
        next_refresh_at=now, freshness='fresh', payload_json={'freshness':'fresh',
        'rows':[{'ts_code':inst.ts_code,'grade':'可试探','freshness':'fresh'}]})
    db.add(snapshot);db.flush()
    result = DecisionBoardService().read_latest(db)
    assert result['rows'][0]['grade']=='数据异常'
    assert result['read_contract']=='legacy_snapshot_requires_rebuild'
    assert result['counts']['数据异常']==1
    assert snapshot.payload_json['rows'][0]['grade']=='可试探'
    assert not db.dirty


def test_verified_instant_is_compared_in_market_timezone():
    from datetime import timezone
    now=datetime(2026,9,14,0,2,tzinfo=get_settings().timezone)
    quote=SimpleNamespace(quote_time=now.astimezone(timezone.utc),fetched_at=now,
        timestamp_verified=True,is_realtime=True,degraded_reason=None)
    state,_=DecisionBoardService._status(object(),quote,now)
    # This is a freshness helper, not the trading-session/actionable gate.
    assert state=='fresh'


def test_unknown_volume_disables_profile_but_keeps_price_structure():
    from app.utils.support_resistance import build_support_resistance
    frame=pd.DataFrame({'open':[2.]*60,'high':[2.1]*60,'low':[1.9]*60,
        'close':[2.]*60,'volume':[100.]*59+[float('nan')]})
    result=build_support_resistance(frame)
    assert result['volume_profile_approx'] is None
    assert result['levels']
