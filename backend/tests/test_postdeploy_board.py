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


def test_sr_frame_excludes_unsettled_same_day_daily_bar_until_1515(isolated):
    db, inst = isolated
    add_bar(db, inst, day=date(2026, 9, 11))
    add_bar(db, inst, day=date(2026, 9, 14))
    service = SupportResistanceService()
    before = datetime(2026, 9, 14, 14, 30, tzinfo=get_settings().timezone)
    settled = datetime(2026, 9, 14, 15, 15, tzinfo=get_settings().timezone)

    assert service._sr_frame(db, inst.id, as_of=before).iloc[-1]['trade_date'] == date(2026, 9, 11)
    assert service._sr_frame(db, inst.id, as_of=settled).iloc[-1]['trade_date'] == date(2026, 9, 14)


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


def test_sr_snapshot_contains_versioned_daily_structures_and_get_stays_read_only(isolated):
    from app.models import SupportResistanceSnapshot
    from app.workspace.candle_periods import transform_chart
    from app.workspace.read_model import chart_data

    db, inst = isolated
    dates = pd.bdate_range("2026-01-05", periods=120)
    highs = [104.0] * 120
    lows = [102.0] * 120
    for index in (10, 45, 80, 110):
        highs[index] = 106.0
    for index in (25, 60, 95):
        lows[index] = 100.0
    rows = [DailyBar(instrument_id=inst.id, trade_date=day.date(), open=103.0, high=highs[i], low=lows[i],
        close=103.0, pre_close=103.0, volume=None, amount=None, source="mock:structure", adjust="none",
        quality_hash=f"structure-{i}") for i, day in enumerate(dates)]
    db.add_all(rows)
    db.flush()
    service = SupportResistanceService()

    assert service.latest(db, inst.id) is None
    assert not db.new and not db.dirty
    assert db.query(SupportResistanceSnapshot).filter_by(instrument_id=inst.id).count() == 0

    computed = service.compute(db, inst.id)
    persisted = service.latest(db, inst.id)

    assert computed["method_version"] == "support-resistance-v4-structure"
    assert computed["structures"]["boxes"][0]["state"] == "confirmed"
    assert computed["structures"]["actionable"] is False
    assert persisted is not None and persisted["structures"]["input_hash"] == computed["structures"]["input_hash"]

    settings = get_settings()
    observed_at = datetime.combine(dates[-1].date(), datetime.min.time(), tzinfo=settings.timezone) + timedelta(hours=16)
    chart = chart_data(db, settings, inst.ts_code, "1d", 260, as_of=observed_at)
    assert chart["research_price_structures"]["qualified"] is True
    assert chart["research_price_structures"]["price_basis_id"] == chart["research_price_basis_id"]
    assert chart["price_structures"]["boxes"][0]["structure_id"] == computed["structures"]["boxes"][0]["structure_id"]

    earlier = chart_data(db, settings, inst.ts_code, "1d", 260, as_of=observed_at - timedelta(days=1))
    assert earlier["research_price_structures"]["reason"] == "snapshot_after_as_of"
    weekly = transform_chart(chart, "1w", settings.load_strategy()["indicator"], 260, now=observed_at)
    assert weekly["research_price_structures"]["reason"] == "interval_unsupported"

    from app.services.decision_board_service import DecisionBoardService
    provisional_day = (dates[-1] + pd.offsets.BDay(1)).date()
    provisional_at = datetime.combine(provisional_day, datetime.min.time(), tzinfo=settings.timezone) + timedelta(hours=10, minutes=29)
    DecisionBoardService(settings).record_provisional_input(db, ts_code=inst.ts_code,
        observed_at=provisional_at, source="mock:intraday", timestamp_verified=True,
        open_price=108.0, high_price=108.2, low_price=107.8, last_price=108.0,
        volume=100.0, amount=10800.0, pct_change_percent_points=0.1)
    intraday = chart_data(db, settings, inst.ts_code, "1d", 260, as_of=provisional_at + timedelta(minutes=1))
    shown_box = intraday["research_price_structures"]["boxes"][0]
    stored = db.query(SupportResistanceSnapshot).filter_by(instrument_id=inst.id).one()

    assert shown_box["state"] == "confirmed"
    assert shown_box["intraday_state"]["state"] == "breakout_attempt"
    assert shown_box["intraday_state"]["side"] == "upper"
    assert "intraday_state" not in stored.payload_json["structures"]["boxes"][0]
    assert not db.dirty


def test_sr_same_day_revisions_are_append_only_and_previous_payload_remains_readable(isolated):
    from app.models import SupportResistanceSnapshotRevision

    db, inst = isolated
    add_bar(db, inst, day=date(2026, 9, 11), close=2.0, high=2.1, low=1.9)
    service = SupportResistanceService()

    first = service.compute(db, inst.id)
    first_revision = db.query(SupportResistanceSnapshotRevision).one()
    first_payload_hash = first_revision.payload_hash

    row = db.query(DailyBar).filter_by(instrument_id=inst.id).one()
    row.close = 2.05
    db.flush()
    second = service.compute(db, inst.id)

    revisions = db.query(SupportResistanceSnapshotRevision).order_by(
        SupportResistanceSnapshotRevision.generated_at,
        SupportResistanceSnapshotRevision.id,
    ).all()
    assert len(revisions) == 2
    assert revisions[0].payload_hash == first_payload_hash
    assert revisions[0].payload_json != revisions[1].payload_json
    assert revisions[0].revision_id != revisions[1].revision_id
    assert second["method_version"] == revisions[1].method_version
    current = service.latest(db, inst.id)
    assert current is not None
    assert current["revision_id"] == revisions[1].revision_id

    db.delete(revisions[1])
    db.flush()
    assert service.latest(db, inst.id) is None


def test_sr_identical_compute_reuses_one_immutable_revision(isolated):
    from app.models import SupportResistanceSnapshotRevision

    db, inst = isolated
    add_bar(db, inst, day=date(2026, 9, 11), close=2.0, high=2.1, low=1.9)
    service = SupportResistanceService()

    service.compute(db, inst.id)
    first = db.query(SupportResistanceSnapshotRevision).one()
    service.compute(db, inst.id)

    revisions = db.query(SupportResistanceSnapshotRevision).all()
    assert len(revisions) == 1
    assert revisions[0].revision_id == first.revision_id
    assert service.latest(db, inst.id)["revision_id"] == first.revision_id


def test_sr_latest_fails_closed_when_current_payload_is_tampered(isolated):
    from app.models import SupportResistanceSnapshot

    db, inst = isolated
    add_bar(db, inst, day=date(2026, 9, 11), close=2.0, high=2.1, low=1.9)
    service = SupportResistanceService()
    service.compute(db, inst.id)
    snapshot = db.query(SupportResistanceSnapshot).one()
    snapshot.payload_json = {**snapshot.payload_json, "tampered": True}
    db.flush()

    assert service.latest(db, inst.id) is None
    assert not db.new and not db.dirty


def test_sr_revision_publication_failure_keeps_previous_current(monkeypatch, isolated):
    from app.models import SupportResistanceSnapshotRevision
    from app.utils.hashing import stable_hash

    db, inst = isolated
    add_bar(db, inst, day=date(2026, 9, 11), close=2.0, high=2.1, low=1.9)
    service = SupportResistanceService()
    service.compute(db, inst.id)
    db.commit()
    previous = service.latest(db, inst.id)
    revised_service = SupportResistanceService()
    revised_service.config_hash = stable_hash({"revision": "new-config"})
    original_add = db.add

    def fail_revision(value):
        if isinstance(value, SupportResistanceSnapshotRevision):
            raise RuntimeError("revision publication failed")
        return original_add(value)

    monkeypatch.setattr(db, "add", fail_revision)
    with pytest.raises(RuntimeError, match="revision publication failed"):
        revised_service.compute(db, inst.id)
    db.rollback()

    current = service.latest(db, inst.id)
    assert current is not None
    assert current["revision_id"] == previous["revision_id"]
    assert not db.new and not db.dirty

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
