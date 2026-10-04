from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.utils.indicators_v05 import calculate_indicators


def _frame(close: list[float], volume: list[float]) -> pd.DataFrame:
    c = np.asarray(close, dtype=float)
    v = np.asarray(volume, dtype=float)
    return pd.DataFrame({
        "trade_date": pd.bdate_range("2026-01-05", periods=len(c)).date,
        "open": c,
        "high": c + 0.5,
        "low": c - 0.5,
        "close": c,
        "volume": v,
        "amount": c * v,
    })


def test_obv_slope_public_field_is_recent_net_directional_volume_balance():
    cfg = get_settings().load_strategy()["indicator"]
    result = calculate_indicators(_frame(list(range(1, 81)), [100.0] * 80), cfg)
    assert result.values["obv_slope_5"] == 1.0
    assert result.frame["obv_slope_5"].iloc[:5].isna().all()
    assert result.frame["obv_slope_5"].dropna().between(-1.0, 1.0).all()


def test_obv_flow_unknown_volume_window_stays_unknown_not_zero():
    cfg = get_settings().load_strategy()["indicator"]
    volume = [100.0] * 80
    volume[-3] = float("nan")
    result = calculate_indicators(_frame(list(range(1, 81)), volume), cfg)
    assert pd.isna(result.frame["obv_slope_5"].iloc[-1])
    assert result.values["obv_slope_5"] is None
