from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.forecast_service import similarity_forecast
from app.utils.feature_store import FEATURE_SCHEMA_VERSION, build_feature_frame, feature_columns_for_horizon


def _bars(rows: int = 420) -> pd.DataFrame:
    index = np.arange(rows, dtype=float)
    close = 1.0 + index * 0.0015 + np.sin(index / 9.0) * 0.035
    open_price = close * (1.0 + np.sin(index / 5.0) * 0.002)
    high = np.maximum(open_price, close) * 1.012
    low = np.minimum(open_price, close) * 0.988
    volume = 1_000_000 + (np.sin(index / 7.0) + 1.2) * 350_000
    return pd.DataFrame(
        {
            "trade_date": [date(2024, 1, 1) + timedelta(days=int(value)) for value in index],
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "amount": volume * close,
        }
    )


def test_similarity_forecast_builds_endpoint_and_path_corridors():
    frame = build_feature_frame(_bars(), {}).frame
    result = similarity_forecast(
        frame,
        horizon=5,
        neighbors=60,
        minimum_neighbors=25,
        maximum_confidence=55,
        feature_columns=feature_columns_for_horizon(5, frame.columns),
    )
    assert result.p_up is not None
    assert result.expected_return is not None
    assert result.diagnostics["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert result.diagnostics["calibration_claim"] == "research_only_not_calibrated"
    corridor = result.corridor
    assert corridor["interval_method"] == "local_conformal_research_v1"
    assert corridor["path_low_price_q50"] <= corridor["path_high_price_q50"]
    assert corridor["terminal_price_q10"] <= corridor["terminal_price_q50"] <= corridor["terminal_price_q90"]
    assert 0 <= corridor["corridor_position"] <= 100
    assert "current row never enters candidates" in result.diagnostics["no_lookahead_rule"]


def test_forecast_short_history_fails_closed():
    frame = build_feature_frame(_bars(80), {}).frame
    result = similarity_forecast(
        frame,
        horizon=20,
        neighbors=60,
        minimum_neighbors=25,
        maximum_confidence=55,
    )
    assert result.p_up is None
    assert result.confidence == 0
    assert result.diagnostics["reason"] == "history_too_short"
