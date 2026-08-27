from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.forecast_service import similarity_forecast
from app.utils.indicators import calculate_indicators


def test_similarity_forecast_has_bounded_outputs():
    rng = np.random.default_rng(7)
    close = 2.0 * np.cumprod(1 + rng.normal(0.0003, 0.012, 520))
    frame = pd.DataFrame(
        {
            "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(len(close))],
            "open": close * (1 + rng.normal(0, 0.002, len(close))),
            "high": close * 1.014,
            "low": close * 0.986,
            "close": close,
            "volume": rng.integers(500_000, 4_000_000, len(close)),
        }
    )
    indicators = calculate_indicators(frame, get_settings().load_strategy()["indicator"])
    result = similarity_forecast(
        indicators.frame,
        horizon=5,
        neighbors=80,
        minimum_neighbors=25,
        maximum_confidence=55,
    )
    assert result.sample_count >= 25
    assert result.p_up is not None and 0 <= result.p_up <= 1
    assert result.q10 <= result.q50 <= result.q90
    assert 0 <= result.confidence <= 55
    assert "no_lookahead_rule" in result.diagnostics
