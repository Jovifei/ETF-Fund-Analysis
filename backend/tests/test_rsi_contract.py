from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.core.config import get_settings
from app.utils.advanced_indicators import rsi as advanced_rsi
from app.utils.indicators import calculate_indicators as calculate_base
from app.utils.indicators_v05 import calculate_indicators as calculate_rich
from app.utils.rsi_contract import project_rsi


def _frame(close: list[float]) -> pd.DataFrame:
    values = np.asarray(close, dtype=float)
    return pd.DataFrame({
        "trade_date": pd.bdate_range("2026-01-05", periods=len(values)).date,
        "open": values,
        "high": values + 0.5,
        "low": values - 0.5,
        "close": values,
        "volume": np.full(len(values), 1000.0),
        "amount": values * 1000.0,
    })


@pytest.mark.parametrize(("close", "expected"), [
    (list(map(float, range(1, 81))), 100.0),
    (list(map(float, range(80, 0, -1))), 0.0),
    ([10.0] * 80, 50.0),
])
def test_all_rsi_windows_share_frame_scalar_and_v05_contract(close, expected):
    cfg = get_settings().load_strategy()["indicator"]
    base = calculate_base(_frame(close), cfg)
    rich = calculate_rich(_frame(close), cfg)
    for window in (6, 12, 14):
        key = f"rsi{window}"
        assert float(base.frame.iloc[-1][key]) == expected
        assert base.values[key] == expected
        assert float(rich.frame.iloc[-1][key]) == expected
        assert rich.values[key] == expected
    if expected == 100.0:
        assert "RSI 超买" in base.values["technical_reasons"]
    if expected == 0.0:
        assert "RSI 弱势" in base.values["technical_reasons"]


def test_rsi_warmup_and_nonfinite_observation_are_neutral_not_directional():
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, np.inf, 8.0, 9.0, 10.0])
    projected = project_rsi(values, 6)
    assert projected.iloc[:6].tolist() == [50.0] * 6
    assert projected.iloc[6] == 50.0
    assert np.isfinite(projected.to_numpy()).all()


def test_advanced_and_base_helpers_are_the_same_project_contract():
    series = pd.Series(np.linspace(1.0, 80.0, 80))
    assert advanced_rsi(series, 14).equals(project_rsi(series, 14))
