from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.utils.feature_store import build_feature_frame
from app.utils.input_validity import INPUT_VALIDITY_POLICY


def _frame(rows: int = 120) -> pd.DataFrame:
    x = np.arange(rows, dtype=float)
    close = 100 + x * 0.08 + np.sin(x / 4.0) * 2.2
    open_price = close + np.sin(x / 7.0) * 0.3
    high = np.maximum(open_price, close) + 1.0 + np.sin(x / 9.0) * 0.15
    low = np.minimum(open_price, close) - 1.0 - np.cos(x / 11.0) * 0.12
    volume = 1000 + x * 7 + (np.sin(x / 5.0) + 1.2) * 100
    return pd.DataFrame({
        "trade_date": pd.bdate_range("2025-01-02", periods=rows).date,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": volume * close,
    })


def test_neutral_display_warmups_are_not_counted_as_mature_research_features():
    cfg = get_settings().load_strategy()["indicator"]
    rich = build_feature_frame(_frame(), cfg).frame
    assert rich.attrs["input_validity_policy"] == INPUT_VALIDITY_POLICY

    assert rich["rsi14"].iloc[:14].isna().all()
    assert pd.notna(rich["rsi14"].iloc[14])

    assert rich["plus_di14"].iloc[:14].isna().all()
    assert rich["minus_di14"].iloc[:14].isna().all()
    assert pd.notna(rich["plus_di14"].iloc[14])
    assert pd.notna(rich["minus_di14"].iloc[14])

    assert rich["adx14"].iloc[:27].isna().all()
    assert pd.notna(rich["adx14"].iloc[27])

    assert rich["cci20"].iloc[:19].isna().all()
    assert pd.notna(rich["cci20"].iloc[19])
    assert rich["wr14"].iloc[:13].isna().all()
    assert pd.notna(rich["wr14"].iloc[13])
    assert rich["wr28"].iloc[:27].isna().all()
    assert pd.notna(rich["wr28"].iloc[27])

    assert rich["mfi14"].iloc[:14].isna().all()
    assert pd.notna(rich["mfi14"].iloc[14])
    assert rich["cmf20"].iloc[:19].isna().all()
    assert pd.notna(rich["cmf20"].iloc[19])

    assert rich["rsrs_beta"].iloc[:17].isna().all()
    assert pd.notna(rich["rsrs_beta"].iloc[17])
    assert rich["rsrs_zscore"].iloc[:46].isna().all()
    assert pd.notna(rich["rsrs_zscore"].iloc[46])


def test_missing_price_contaminates_price_and_money_flow_windows_instead_of_neutralizing():
    cfg = get_settings().load_strategy()["indicator"]
    raw = _frame()
    raw.loc[90, "high"] = np.nan
    rich = build_feature_frame(raw, cfg).frame

    for key in (
        "rsi14", "plus_di14", "minus_di14", "adx14", "cci20", "wr14", "wr28",
        "mfi14", "cmf20", "rsrs_beta", "rsrs_zscore", "obv_slope_5",
    ):
        assert pd.isna(rich.loc[90, key]), key

    # Price-only gaps do not get rewritten as valid neutral flow observations.
    assert pd.isna(rich.loc[90, "mfi14"])
    assert pd.isna(rich.loc[90, "cmf20"])
