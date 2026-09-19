from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.providers.akshare import AKShareProvider
from app.providers.data_contract import assess_history, history_issues, price_history_issue, qualified_research_history, trailing_unverified_history
from app.services.etf_1430_service import ETF1430WorkbenchService
from app.utils.input_lineage import history_digest
from app.utils.feature_store import build_feature_frame
from test_v103_history import instrument


def bar(i=0, close=1.2, **kw):
    row=dict(trade_date=date(2026,7,20)+timedelta(days=i), open=close, high=close*1.01, low=close*.99, close=close, volume=1000, amount=1200, source='fixture:units-verified', adjust='none')
    row.update(kw)
    return SimpleNamespace(**row)

@pytest.mark.parametrize('v,a',[(1000,1200),(100000,120000),(1000,1190)])
def test_vwap_ratio_never_qualifies_absolute_units(v,a):
    volume,amount,source=AKShareProvider._sina_volume_fields(1.2,v,a)
    assert volume is None and amount is None and source != 'akshare:sina:v102'

def test_old_promoted_sina_rows_are_quarantined_not_mutated(db_session):
    from app.models import DailyBar
    item=instrument(db_session)
    rows=db_session.scalars(select(DailyBar).where(DailyBar.instrument_id==item.id).order_by(DailyBar.trade_date)).all()
    for row in rows: row.source='akshare:sina:v102'
    db_session.flush()
    reasons=history_issues(db_session,get_settings().model_copy(update={'market_provider':'akshare'}),[item.id])
    assert reasons[item.id]=='sina_absolute_units_unverified'
    assert all(row.volume==1000 for row in rows)
    db_session.rollback()

def test_unexplained_588200_break_blocks_returns_not_raw_display():
    rows=[bar(close=3.539),bar(1,1.349)]
    assert price_history_issue(rows)=='unexplained_price_discontinuity'
    assert rows[0].close==3.539 and rows[1].close==1.349

def test_amount_missing_is_qualification_failure():
    assert 'amount_missing_for_shared_signals' in assess_history([bar(amount=None)])


def test_trailing_price_only_rows_keep_last_qualified_history_scope():
    qualified = [bar(i, close=1.2 + i * 0.001, source='akshare:em:v101') for i in range(5)]
    tail = [bar(5, close=1.21, source='akshare:sina:v101', volume=None, amount=None)]
    scope = trailing_unverified_history(qualified + tail)
    assert scope is not None
    assert scope['qualified_through'] == qualified[-1].trade_date
    assert scope['tail_rows'] == 1


def test_interleaved_price_only_rows_do_not_get_a_stale_scope():
    rows = [
        bar(0, source='akshare:em:v101'),
        bar(1, source='akshare:sina:v101', volume=None, amount=None),
        bar(2, source='akshare:em:v101'),
    ]
    assert trailing_unverified_history(rows) is None


def test_official_split_makes_history_issue_only_the_unverified_tail(db_session):
    from app.models import DailyBar, Instrument

    existing = db_session.scalar(select(Instrument).where(Instrument.ts_code == "512000.SH"))
    if existing is not None:
        db_session.execute(delete(DailyBar).where(DailyBar.instrument_id == existing.id))
        db_session.delete(existing)
        db_session.flush()
    inst = Instrument(ts_code="512000.SH", symbol="512000", name="split fixture", kind="ETF", enabled=True)
    db_session.add(inst)
    db_session.flush()
    db_session.add_all([
        DailyBar(instrument_id=inst.id, trade_date=date(2025, 8, 1), open=1.13, high=1.14, low=1.12, close=1.138,
                 volume=1000, amount=2000, source="akshare:em:v101", adjust="none", quality_hash="before"),
        DailyBar(instrument_id=inst.id, trade_date=date(2025, 8, 4), open=0.57, high=0.58, low=0.56, close=0.572,
                 volume=2000, amount=2000, source="akshare:em:v101", adjust="none", quality_hash="after"),
        DailyBar(instrument_id=inst.id, trade_date=date(2025, 8, 5), open=0.57, high=0.58, low=0.56, close=0.571,
                 volume=None, amount=None, source="akshare:sina:v101", adjust="none", quality_hash="tail"),
    ])
    db_session.flush()
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    issues = history_issues(db_session, settings, [inst.id])
    assert issues[inst.id] == "price_only_history_units_unverified"
    research_rows, stale_scope = qualified_research_history(
        db_session.scalars(select(DailyBar).where(DailyBar.instrument_id == inst.id).order_by(DailyBar.trade_date)).all(),
        inst.ts_code,
    )
    assert stale_scope["qualified_through"] == date(2025, 8, 4)
    assert price_history_issue(research_rows[:2]) is None
    db_session.rollback()


def test_forecast_frame_uses_officially_adjusted_history_before_unverified_tail(db_session):
    from app.models import DailyBar, Instrument
    from app.services.forecast_service import ForecastService

    existing = db_session.scalar(select(Instrument).where(Instrument.ts_code == "512000.SH"))
    if existing is not None:
        db_session.execute(delete(DailyBar).where(DailyBar.instrument_id == existing.id))
        db_session.delete(existing)
        db_session.flush()
    inst = Instrument(ts_code="512000.SH", symbol="512000", name="split forecast fixture", kind="ETF", enabled=True)
    db_session.add(inst)
    db_session.flush()
    for index in range(210):
        current = date(2025, 1, 1) + timedelta(days=index)
        price = 1.2 + index * 0.001
        db_session.add(DailyBar(
            instrument_id=inst.id, trade_date=current, open=price, high=price + 0.01,
            low=price - 0.01, close=price, volume=1000, amount=2000,
            source="akshare:em:v101", adjust="none", quality_hash=str(index),
        ))
    db_session.add_all([
        DailyBar(instrument_id=inst.id, trade_date=date(2025, 8, 1), open=1.13, high=1.14, low=1.12, close=1.138,
                 volume=1000, amount=2000, source="akshare:em:v101", adjust="none", quality_hash="split-before"),
        DailyBar(instrument_id=inst.id, trade_date=date(2025, 8, 4), open=0.57, high=0.58, low=0.56, close=0.572,
                 volume=2000, amount=2000, source="akshare:em:v101", adjust="none", quality_hash="split-after"),
        DailyBar(instrument_id=inst.id, trade_date=date(2025, 8, 5), open=0.57, high=0.58, low=0.56, close=0.571,
                 volume=None, amount=None, source="akshare:sina:v101", adjust="none", quality_hash="split-tail"),
    ])
    db_session.flush()
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    frames = ForecastService(settings)._frames(db_session, [inst])
    assert inst.id in frames
    assert frames[inst.id].iloc[-1]["trade_date"] == date(2025, 8, 4)
    db_session.rollback()

@pytest.mark.parametrize('when,stamp',[(datetime(2026,9,12,14,30),datetime(2026,9,12,14,30)), (datetime(2026,9,11,14,30),datetime(2026,9,12,14,30))])
def test_1430_weekend_future_never_actionable(when,stamp):
    settings=get_settings().model_copy(update={'market_provider':'akshare'})
    quote=SimpleNamespace(source='fixture:realtime',price=1.2,quote_time=stamp.replace(tzinfo=settings.timezone),is_realtime=True,timestamp_verified=True,degraded_reason=None)
    result=ETF1430WorkbenchService(settings)._qualification(quote,when.replace(tzinfo=settings.timezone))
    assert not result['actionable']
    assert ('not_a_trading_day' in result['reasons']) or ('quote_from_future' in result['reasons'])
    assert 'historical_1430_backtest_not_qualified' in result['reasons']

def test_full_input_hash_changes_when_early_price_changes():
    rows=[bar(i) for i in range(700)]
    before=history_digest(rows)
    rows[0].close=1.21
    assert history_digest(rows)!=before

def frame(volume=True,amount=True):
    n=200;p=1.2+np.arange(n)*.001+np.sin(np.arange(n))*.01
    return pd.DataFrame(dict(trade_date=pd.date_range('2025-01-01',periods=n),open=p,high=p+.02,low=p-.02,close=p,volume=np.arange(n)+1000 if volume else np.full(n,np.nan),amount=p*(np.arange(n)+1000) if amount else np.full(n,np.nan)))

def test_missing_volume_not_neutral_money_flow_or_coverage():
    rich=build_feature_frame(frame(False,False),get_settings().load_strategy()['indicator']).frame
    for key in ['mfi14','cmf20','volume_ratio','amount_ratio','obv_slope_5','volume_breakout','vp_peak_distance']:
        assert rich[key].isna().all(),key
    assert rich['rsi14'].notna().any() and rich['ma20'].notna().any()

def test_missing_one_row_masks_dependent_window_not_price():
    raw=frame();raw.loc[180,'volume']=np.nan
    rich=build_feature_frame(raw,get_settings().load_strategy()['indicator']).frame
    assert rich.loc[180:194,'mfi14'].isna().all()
    assert rich.loc[199,'cmf20']!=rich.loc[199,'cmf20']
    assert rich.loc[199,'ma20']==rich.loc[199,'ma20']

def test_amount_not_volume_mask_is_independent():
    rich=build_feature_frame(frame(True,False),get_settings().load_strategy()['indicator']).frame
    assert rich['amount_ratio'].isna().all() and rich['vwap20'].isna().all()
    assert pd.notna(rich.iloc[-1]['cmf20'])
