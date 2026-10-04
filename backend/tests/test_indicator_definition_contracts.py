from __future__ import annotations

import numpy as np
import pandas as pd

from app.utils.advanced_indicators import adx_dmi, cmf, obv, rsrs, true_range
from app.utils.indicator_contract import INDICATOR_DEFINITION_CONTRACT_VERSION, INDICATOR_DEFINITIONS
from app.utils.indicators import _atr, _kdj, calculate_indicators


def _frame(rows: int = 90) -> pd.DataFrame:
    x = np.arange(rows, dtype=float)
    close = 100.0 + x * 0.2 + np.sin(x / 5.0)
    return pd.DataFrame({
        "trade_date": pd.bdate_range("2026-01-05", periods=rows).date,
        "open": close - 0.2,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": 1000.0 + x * 10.0,
    })


def test_definition_contract_version_and_scope_are_explicit():
    assert INDICATOR_DEFINITION_CONTRACT_VERSION == "indicator-definitions-v1"
    assert INDICATOR_DEFINITIONS["td_setup"]["scope"] == "setup_only_not_full_td_sequential"
    assert INDICATOR_DEFINITIONS["td_setup"]["trading_signal"] is False
    assert INDICATOR_DEFINITIONS["macd"]["histogram_scale"] == 2.0
    assert INDICATOR_DEFINITIONS["obv"]["first_value"] == 0.0


def test_macd_histogram_uses_project_double_bar_convention():
    result = calculate_indicators(_frame(), {})
    dif = result.frame["macd_dif"].to_numpy(float)
    dea = result.frame["macd_dea"].to_numpy(float)
    hist = result.frame["macd_hist"].to_numpy(float)
    np.testing.assert_allclose(hist, 2.0 * (dif - dea), rtol=0, atol=1e-12)


def test_atr_warmup_and_smoothing_match_project_contract():
    frame = _frame(40)
    high, low, close = frame["high"], frame["low"], frame["close"]
    actual = _atr(high, low, close, 14)
    expected = true_range(high, low, close).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    assert actual.iloc[:13].isna().all()
    np.testing.assert_allclose(actual.iloc[13:].to_numpy(float), expected.iloc[13:].to_numpy(float), rtol=0, atol=1e-12)


def test_adx_public_series_zero_fills_project_warmup():
    frame = _frame(40)
    adx, plus_di, minus_di = adx_dmi(frame["high"], frame["low"], frame["close"], 14)
    assert (adx.iloc[:13] == 0.0).all()
    assert (plus_di.iloc[:13] == 0.0).all()
    assert (minus_di.iloc[:13] == 0.0).all()
    assert np.isfinite(adx.to_numpy()).all()


def test_obv_starts_at_zero_and_accumulates_signed_volume():
    close = pd.Series([10.0, 11.0, 10.0, 10.0, 12.0])
    volume = pd.Series([100.0, 200.0, 300.0, 400.0, 500.0])
    assert obv(close, volume).tolist() == [0.0, 200.0, -100.0, -100.0, 400.0]


def test_kdj_uses_seed_50_rolling_from_first_observation_and_unclipped_j():
    high = pd.Series([11.0, 12.0, 13.0])
    low = pd.Series([9.0, 9.0, 9.0])
    close = pd.Series([11.0, 12.0, 13.0])
    k, d, j = _kdj(high, low, close, period=9, initial=50.0)
    assert round(float(k.iloc[0]), 6) == round(2 / 3 * 50 + 1 / 3 * 100, 6)
    assert round(float(d.iloc[0]), 6) == round(2 / 3 * 50 + 1 / 3 * k.iloc[0], 6)
    assert float(j.iloc[-1]) > 100.0


def test_cmf_flat_range_is_neutral_zero():
    high = pd.Series([10.0] * 25)
    low = pd.Series([10.0] * 25)
    close = pd.Series([10.0] * 25)
    volume = pd.Series([100.0] * 25)
    assert (cmf(high, low, close, volume, 20) == 0.0).all()


def test_rsrs_raw_is_beta_times_r2_under_project_ols_definition():
    low = pd.Series(np.linspace(10.0, 30.0, 90))
    high = 2.0 * low + 1.0
    beta, r2, raw, z = rsrs(high, low, 18, 60)
    mask = beta.notna() & r2.notna() & raw.notna()
    np.testing.assert_allclose(raw[mask].to_numpy(float), (beta[mask] * r2[mask]).to_numpy(float), rtol=0, atol=1e-12)
    assert np.isfinite(z.to_numpy()).all()
