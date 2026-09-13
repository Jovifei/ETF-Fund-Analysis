"""Typed normalization must not turn unknown price bases into qualified history."""
from types import SimpleNamespace
from datetime import date
import pytest
from app.providers.data_contract import assess_history, price_history_issue


def candle(**kw):
    return SimpleNamespace(**{**dict(trade_date=date(2026,9,10),open=1.2,high=1.3,low=1.1,close=1.2,
        volume=1000,amount=1200,source='akshare:em:v101',adjust='none'),**kw})


@pytest.mark.parametrize('adjust',[None,'banana','',False])
def test_unsupported_price_basis_fails_closed(adjust):
    assert price_history_issue([candle(adjust=adjust)])=='unknown_price_basis'


def test_numeric_strings_do_not_raise_or_use_lexical_ohlc_order():
    assert price_history_issue([candle(open='2',high='10',low='1',close='9')]) is None
    assert price_history_issue([candle(open='10',high='2',low='1',close='2')])=='invalid_ohlc'
    assert not assess_history([candle(volume='1000',amount='1200')])


def test_invalid_dates_and_unknown_amount_are_rejected_not_exceptions():
    assert price_history_issue([candle(trade_date=None)])=='invalid_history_date'
    assert 'amount_missing_for_shared_signals' in assess_history([candle(amount='not-a-number')])


def test_factor_masks_are_materialized_not_deepcopied_in_dataframe_attrs():
    from test_audit_data_20260912 import frame
    from app.utils.feature_store import build_feature_frame
    from app.core.config import get_settings
    import json
    import numpy as np
    raw=frame();raw.loc[180,'volume']=np.nan
    rich=build_feature_frame(raw,get_settings().load_strategy()['indicator']).frame
    assert rich.loc[199,'cmf20']!=rich.loc[199,'cmf20']
    assert np.isfinite(rich.loc[199,'rsi14'])
    # Pandas deep-copies attrs for every slice/concat/reduction. A per-row mask
    # grid here multiplied walk-forward runtime; the mask is already in values.
    assert len(json.dumps(rich.attrs)) < 512
    assert rich.attrs['input_validity_policy']=='raw-dependency-mask-v1'
