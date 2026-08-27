from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.utils.advanced_indicators import cmf, mfi, obv, rsrs
from app.utils.indicators_v05 import calculate_indicators


def test_indicator_contract_is_finite():
    strategy = get_settings().load_strategy()
    rng = np.random.default_rng(42)
    closes = 1.0 * np.cumprod(1 + rng.normal(0.0004, 0.009, 280))
    rows = []
    day = date(2025, 1, 1)
    for idx, close in enumerate(closes):
        current = day + timedelta(days=idx)
        rows.append({
            "trade_date": current,
            "open": close * 0.998,
            "high": close * 1.012,
            "low": close * 0.988,
            "close": close,
            "volume": 1_000_000 + idx * 500,
        })
    result = calculate_indicators(pd.DataFrame(rows), strategy["indicator"])
    assert 0 <= result.technical_score <= 100
    assert 0 <= result.risk_score <= 100
    assert result.data_quality >= 95
    assert result.values["ma60"] is not None
    assert result.values["macd_hist"] is not None
    assert result.values["kdj_j"] is not None
    assert result.values["rsi14"] is not None
    assert result.values["adx14"] is not None
    assert result.values["mfi14"] is not None
    assert result.values["cmf20"] is not None
    assert result.values["wr14"] is not None
    assert result.values["rsrs_zscore"] is not None
    assert result.values["box_position_20"] is not None
    assert result.values["chip_method"] == "volume_profile_approx"
    assert result.values["chip_is_estimated"] is True
    assert result.values["chip_peak_price"] is not None
    assert 0 <= result.values["chip_winner_ratio"] <= 1
    assert isinstance(result.values["td_buy_setup"], int)


def test_obv_known_sequence():
    close = pd.Series([1.0, 2.0, 1.0, 1.0, 3.0])
    volume = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    assert obv(close, volume).tolist() == [0.0, 20.0, -10.0, -10.0, 40.0]


def test_rsrs_linear_high_low_has_expected_beta_and_r2():
    low = pd.Series(np.linspace(1.0, 120.0, 120))
    high = low * 2.0 + 1.0
    beta, r2, raw, zscore = rsrs(high, low, regression_window=18, zscore_window=60)
    assert abs(float(beta.iloc[-1]) - 2.0) < 1e-10
    assert abs(float(r2.iloc[-1]) - 1.0) < 1e-10
    assert abs(float(raw.iloc[-1]) - 2.0) < 1e-10
    assert abs(float(zscore.iloc[-1])) < 1e-10


def test_mfi_and_cmf_confirm_persistent_buying_pressure():
    high = pd.Series(np.linspace(10.2, 12.2, 40))
    low = high - 0.8
    close = high - 0.05
    volume = pd.Series(np.linspace(1_000_000, 1_500_000, 40))
    assert float(mfi(high, low, close, volume, 14).iloc[-1]) >= 99.0
    assert float(cmf(high, low, close, volume, 20).iloc[-1]) > 0.7
