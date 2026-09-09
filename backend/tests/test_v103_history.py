from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from app.core.config import get_settings
from app.models import DailyBar, Instrument, IndicatorSnapshot
from app.services.indicator_service import IndicatorService
from app.workspace.read_model import chart_data, instrument_detail


def instrument(db, missing_volume=False, legacy=False):
    code = '59' + str(int(uuid4().hex[:5], 16) % 10000).zfill(4) + '.SH'
    inst = Instrument(ts_code=code, symbol=code[:6], name='history test', kind='ETF', enabled=True)
    db.add(inst); db.flush()
    for i in range(80):
        price = 2 + i * .01
        db.add(DailyBar(instrument_id=inst.id, trade_date=date(2025,1,1)+timedelta(days=i),
            open=price, high=price+.1, low=price-.1, close=price+.02,
            volume=None if missing_volume else 1000, amount=None if missing_volume else 2000,
            source='akshare' if legacy else 'akshare:sina:v101' if missing_volume else 'fixture:v103',
            adjust='none', quality_hash=str(i)))
    db.flush()
    return inst


def test_missing_volume_does_not_block_price_chart_or_detail(db_session):
    db = db_session
    inst = instrument(db, missing_volume=True)
    settings = get_settings().model_copy(update={'market_provider':'akshare'})
    result = chart_data(db,settings,inst.ts_code,'1d',100)
    assert result['bars'][-1]['indicators']['macd_dif'] is not None
    detail = instrument_detail(db,settings,inst.ts_code,None)
    assert detail['indicator_values']['macd_dif'] is not None
    assert detail['quote']['price'] == pytest.approx(2.81)
    assert detail['quote']['status'] == 'historical_close'
    assert detail['actionable'] is False
    assert detail['forecasts'] == {}
    assert result['bars'][-1]['volume'] is None
    db.rollback()


def test_legacy_units_only_hide_volume_not_price_indicators(db_session):
    inst = instrument(db_session,legacy=True)
    settings=get_settings().model_copy(update={'market_provider':'akshare'})
    result=chart_data(db_session,settings,inst.ts_code,'1d',100)
    assert result['bars'][-1]['indicators']['ma20'] is not None
    assert result['bars'][-1]['volume'] is None
    assert result['actionable'] is False
    db_session.rollback()


def test_shared_indicator_refresh_skips_bad_asset_not_whole_universe(db_session):
    good=instrument(db_session)
    bad=instrument(db_session,missing_volume=True)
    settings=get_settings().model_copy(update={'market_provider':'akshare'})
    outcome=IndicatorService(settings).refresh_all(db_session)
    assert db_session.scalar(select(IndicatorSnapshot).where(IndicatorSnapshot.instrument_id==good.id)) is not None
    assert db_session.scalar(select(IndicatorSnapshot).where(IndicatorSnapshot.instrument_id==bad.id)) is None
    assert any(item['ts_code']==bad.ts_code for item in outcome['failures'])
    db_session.rollback()


def test_eligibility_scope_does_not_mutate_instruments(db_session):
    from app.providers.data_contract import history_issues
    good=instrument(db_session); bad=instrument(db_session,missing_volume=True)
    settings=get_settings().model_copy(update={'market_provider':'akshare'})
    issues=history_issues(db_session,settings)
    assert good.id not in issues and bad.id in issues
    assert good.enabled and bad.enabled
    db_session.rollback()


def test_original_board_keeps_price_labels_without_publishing_grade(db_session):
    from app.services.decision_board_service import DecisionBoardService
    inst=instrument(db_session, missing_volume=True)
    settings=get_settings().model_copy(update={'market_provider':'akshare'})
    built=DecisionBoardService(settings).refresh(db_session)
    row=next(r for r in built.payload['rows'] if r['ts_code']==inst.ts_code)
    assert row['data_status']=='historical_price_only'
    assert row['macd']['label'] != 'MACD不足'
    assert row['grade']=='数据异常' and row['actionable'] is False
    assert row['history'][-1]['volume'] is None
    db_session.rollback()
