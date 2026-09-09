"""Chart periods are server-side OHLC aggregation, never relabeled daily bars."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.workspace.candle_periods import aggregate_bars, chart_studies


def rows():
    return [dict(date=day,open=o,high=h,low=l,close=c,volume=v,amount=v*10 if v is not None else None,source='fixture',is_partial=False)
            for day,o,h,l,c,v in [('2026-08-28',10,12,9,11,100),('2026-08-31',11,15,10,14,200),('2026-09-01',14,16,13,15,None),('2026-09-04',15,17,14,16,400)]]


def test_calendar_week_ohlc_missing_volume_and_no_synthetic_dates():
    result=aggregate_bars(rows(),'1w',now=datetime(2026,9,9,tzinfo=ZoneInfo('Asia/Shanghai')))
    assert len(result)==2
    assert result[-1]['date']=='2026-09-04'
    assert [result[-1][k] for k in ('open','high','low','close')]==[11,17,10,16]
    assert result[-1]['volume'] is None
    assert result[-1]['source_bar_count']==3
    assert result[-1]['is_partial'] is False


def test_month_and_current_period_partial_are_not_forecast_horizons():
    result=aggregate_bars(rows(),'1mo',now=datetime(2026,9,9,tzinfo=ZoneInfo('Asia/Shanghai')))
    assert result[0]['period_start']=='2026-08-01'
    assert result[0]['close']==14
    assert result[1]['is_partial'] is True
    assert result[1]['volume'] is None


def test_daily_identity_and_invalid_period_rejected():
    import pytest
    raw=rows()
    assert aggregate_bars(raw,'1d')==raw
    with pytest.raises(ValueError): aggregate_bars(raw,'1h')


def test_studies_use_price_pivots_not_oscillator_values_and_are_research_only():
    import math
    from datetime import date,timedelta
    raw=[dict(date=(date(2025,1,1)+timedelta(days=i)).isoformat(),open=100+math.sin(i)*2,close=100+math.sin(i)*2,high=104+math.sin(i)*2,low=96+math.sin(i)*2,volume=None,amount=None,source='fixture') for i in range(130)]
    result=chart_studies(raw,{},'1d')
    assert result['actionable'] is False
    assert result['nearest_support'] and result['nearest_resistance']
    assert all(70<level['price']<130 for level in result['levels'])
    assert result['volume_profile_approx'] is None
    assert result['chan_zone_approx']['qualified'] is False
    assert any(item['key']=='kdj_j' and '价格' in item['explanation'] for item in result['readings'])
