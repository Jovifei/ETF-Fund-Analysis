"""PR-F：支撑压力区域化 + TD9 价格确认（后端口径）。"""
from __future__ import annotations

import pandas as pd
import pytest

from app.utils.support_resistance import build_support_resistance


def _frame(rows: int = 160, seed: int = 5) -> pd.DataFrame:
    import numpy as np

    rng = np.random.default_rng(seed)
    close = 2.0 + np.abs(np.cumsum(rng.normal(0, 0.015, rows)))
    frame = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=rows).date,
            "open": close + rng.normal(0, 0.004, rows),
            "high": close + np.abs(rng.normal(0, 0.008, rows)),
            "low": close - np.abs(rng.normal(0, 0.008, rows)),
            "close": close,
            "volume": rng.integers(1e5, 1e6, rows).astype(float),
            "amount": rng.integers(1e8, 1e9, rows).astype(float),
            "td_buy_setup": 0,
            "td_sell_setup": 0,
        }
    )
    frame.loc[40:47, "td_sell_setup"] = range(1, 9)  # 触发一次 TD9 卖出确认
    frame.loc[40:47, "high"] = frame.loc[40:47, "close"] + 0.15  # 抬高对应高点
    return frame


def test_levels_carry_clustered_zone_fields():
    result = build_support_resistance(_frame())
    assert result["qualified"] is True
    assert result["levels"], "levels expected"
    for level in result["levels"][:6]:
        assert "zone_low" in level and "zone_high" in level
        assert level["zone_basis"] == "clustered_price_span"
        assert level["zone_low"] <= level["price"] <= level["zone_high"]
    assert "default_zone_tolerance" in result and result["default_zone_tolerance"] > 0


def test_td9_exhaustion_confirmation_creates_level_method():
    result = build_support_resistance(_frame())
    all_methods = [method for level in result["levels"] for method in level["methods"]]
    assert "TD9卖出耗竭确认" in all_methods


def test_td9_without_setup_counts_has_no_confirmation():
    frame = _frame()
    frame["td_buy_setup"] = 0
    frame["td_sell_setup"] = 0
    result = build_support_resistance(frame)
    all_methods = [method for level in result["levels"] for method in level["methods"]]
    assert "TD9卖出耗竭确认" not in all_methods
    assert "TD9买入耗竭确认" not in all_methods
