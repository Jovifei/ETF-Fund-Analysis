from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.utils.indicators import calculate_indicators


def test_indicator_contract_is_finite():
    strategy = get_settings().load_strategy()
    rng = np.random.default_rng(42)
    closes = 1.0 * np.cumprod(1 + rng.normal(0.0004, 0.009, 280))
    rows = []
    day = date(2025, 1, 1)
    for idx, close in enumerate(closes):
        current = day + timedelta(days=idx)
        rows.append(
            {
                "trade_date": current,
                "open": close * 0.998,
                "high": close * 1.012,
                "low": close * 0.988,
                "close": close,
                "volume": 1_000_000 + idx * 500,
            }
        )
    result = calculate_indicators(pd.DataFrame(rows), strategy["indicator"])
    assert 0 <= result.technical_score <= 100
    assert 0 <= result.risk_score <= 100
    assert result.data_quality >= 95
    assert result.values["ma60"] is not None
    assert result.values["macd_hist"] is not None
    assert result.values["kdj_j"] is not None
    assert result.values["rsi14"] is not None
    assert isinstance(result.values["td_buy_setup"], int)
