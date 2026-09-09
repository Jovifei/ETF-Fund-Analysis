import math
from datetime import date,timedelta
from copy import deepcopy
import pytest
from app.core.config import get_settings
from app.workspace.research_outlook import compute


def samples():
    return [dict(date=(date(2023,1,1)+timedelta(days=i)).isoformat(),open=100+math.sin(i/8)*8,high=111+math.sin(i/8),low=89+math.sin(i/8),close=100+math.sin(i/8)*8,adjust='none',source='fixture') for i in range(500)]


def test_research_month_is_a_real_twenty_session_target_not_canonical_promotion():
    result=compute(samples(),get_settings())
    assert set(result['forecasts'])=={'1','5','20'}
    assert result['not_strategy_output'] is True and result['actionable'] is False
    for horizon,f in result['forecasts'].items():
        assert f['horizon']==int(horizon)
        assert f['calibration_status']=='not_calibrated'
        assert f['sample_count']>=25 and f['q10']<=f['q50']<=f['q90']
    assert result['forecasts']['20']['expected_return']!=result['forecasts']['1']['expected_return']


def test_bad_or_short_input_is_not_filled():
    assert compute(samples()[:10],get_settings())['status']=='unavailable'
    rows=samples();rows[3]['high']=0
    with pytest.raises(ValueError):compute(rows,get_settings())
    rows=samples();rows.append(rows[-1])
    with pytest.raises(ValueError):compute(rows,get_settings())
    rows=samples();rows[1]['source']='mock'
    with pytest.raises(ValueError):compute(rows,get_settings())
    rows=samples();rows[1]['adjust']='qfq'
    with pytest.raises(ValueError):compute(rows,get_settings())


def test_mock_input_never_becomes_qualified_by_settings():
    from app.core.config import Settings
    rows=samples()
    for row in rows:row['source']='mock'
    result=compute(rows,Settings(market_provider='akshare'))
    assert result['qualification']=='mock' and not result['actionable']
