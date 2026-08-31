from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.utils.feature_store import build_feature_frame
from app.utils.support_resistance import build_support_resistance


def _frame(rows: int = 280) -> pd.DataFrame:
    x = np.arange(rows, dtype=float)
    close = 1.2 + x * 0.0012 + np.sin(x / 8.0) * 0.055
    open_ = close + np.sin(x / 5.0) * 0.008
    high = np.maximum(open_, close) + 0.018
    low = np.minimum(open_, close) - 0.018
    volume = 1_000_000 + (np.sin(x / 6.0) + 1.4) * 450_000
    raw = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2025-01-02", periods=rows).date,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "amount": volume * close,
        }
    )
    return build_feature_frame(raw, get_settings().load_strategy()["indicator"]).frame


def test_support_resistance_returns_price_levels_and_semantic_boundaries():
    result = build_support_resistance(_frame())
    assert result["qualified"] is True
    assert result["nearest_support"] is not None
    assert result["nearest_resistance"] is not None
    assert result["nearest_support"]["price"] <= result["current_price"]
    assert result["nearest_resistance"]["price"] > result["current_price"]
    assert result["levels"]
    methods = {method for level in result["levels"] for method in level["methods"]}
    assert any(method.startswith("MA") for method in methods)
    assert "成交密集峰估算" in methods
    assert "never converted directly to prices" in result["semantics"]["oscillator_levels"]
    assert "not a complete Chan-theory" in result["semantics"]["chan"]


def test_support_resistance_fails_closed_on_short_history():
    result = build_support_resistance(_frame(25))
    assert result["qualified"] is False
    assert result["reason"] == "history_too_short"
    assert result["levels"] == []
