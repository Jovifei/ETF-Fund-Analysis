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


def test_missing_atr_field_uses_observed_ohlc_atr_not_price_percentage():
    frame = _frame()
    expected = frame["atr"].iloc[-1]
    frame = frame.drop(columns=["atr", "atr14"], errors="ignore")

    result = build_support_resistance(frame)

    assert result["atr14"] == round(float(expected), 6)
    assert result["atr_basis"] == "wilder_14_from_ohlc"
    assert result["atr14"] != round(float(frame.iloc[-1]["close"]) * 0.02, 6)


def test_support_resistance_exposes_pivot_touches_separately_from_references():
    result = build_support_resistance(_frame())

    assert result["structural_levels"]
    assert result["dynamic_references"]
    assert result["volatility_references"]
    assert all(level["category"] == "price_structure" for level in result["structural_levels"])
    assert all(level["touch_count"] <= len(level["touch_ids"]) for level in result["structural_levels"])


def test_oscillator_confirmations_add_features_but_not_independent_touches():
    from app.utils.support_resistance import _pivot_indexes

    frame = _frame()
    index = _pivot_indexes(frame["high"], window=2, kind="high")[-1]
    frame.loc[index - 1, "macd_hist"] = 1.0
    frame.loc[index, "macd_hist"] = 2.0
    frame.loc[index + 1, "macd_hist"] = 1.0
    frame.loc[index, "macd_dif"] = 1.0
    frame.loc[index, "macd_dea"] = 0.0
    frame.loc[index, "kdj_j"] = 90.0
    frame.loc[index, "rsi14"] = 70.0

    result = build_support_resistance(frame)
    touch_id = f"pivot:high:{frame.iloc[index]['trade_date']}"
    level = next(item for item in result["structural_levels"] if touch_id in item["touch_ids"])

    assert level["confirmations"] >= 4
    assert level["touch_count"] == len(level["touch_ids"])


def test_support_resistance_method_version_fits_existing_database_column():
    from app.models import SupportResistanceSnapshot
    from app.services.support_resistance_service import METHOD_VERSION

    max_length = SupportResistanceSnapshot.__table__.c.method_version.type.length

    assert len(METHOD_VERSION) <= max_length
