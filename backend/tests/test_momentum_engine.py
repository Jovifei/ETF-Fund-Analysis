from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_momentum_and_volatility_math():
    from app.services.strategy_evaluation.momentum_engine import (
        calc_cross_sectional_ranks,
        calc_momentum,
        calc_volatility_annualized,
        compute_dual_momentum_weights,
        compute_volatility_target_weight,
    )

    # 1. Momentum calculation
    prices = pd.Series([1.0, 1.1, 1.2, 1.3, 1.4, 1.5])
    mom = calc_momentum(prices, lookback=2)
    assert pd.isna(mom.iloc[0])
    assert pd.isna(mom.iloc[1])
    assert pytest.approx(mom.iloc[2], 0.0001) == (1.2 / 1.0 - 1.0)
    assert pytest.approx(mom.iloc[5], 0.0001) == (1.5 / 1.3 - 1.0)

    # 2. Volatility calculation
    # Daily returns: 1% each day -> std is 0
    constant_rets = pd.Series([0.01] * 30)
    vol_zero = calc_volatility_annualized(constant_rets, window=20)
    assert pytest.approx(vol_zero.iloc[-1], 0.0001) == 0.0

    # Alternating returns: +2%, -2%
    alt_rets = pd.Series([0.02, -0.02] * 15)
    vol_alt = calc_volatility_annualized(alt_rets, window=20)
    expected_std = alt_rets.iloc[-20:].std(ddof=1) * np.sqrt(252)
    assert pytest.approx(vol_alt.iloc[-1], 0.0001) == expected_std

    # 3. Volatility target position sizing (M2)
    # Target 15% vol, max 1.0
    w_normal = compute_volatility_target_weight(trend_state=1, vol=0.15, target_vol=0.15, max_weight=1.0)
    assert pytest.approx(w_normal, 0.001) == 1.0

    w_high_vol = compute_volatility_target_weight(trend_state=1, vol=0.30, target_vol=0.15, max_weight=1.0)
    assert pytest.approx(w_high_vol, 0.001) == 0.5  # Sizing cut in half when volatility doubles!

    w_low_vol_capped = compute_volatility_target_weight(trend_state=1, vol=0.05, target_vol=0.15, max_weight=1.0)
    assert pytest.approx(w_low_vol_capped, 0.001) == 1.0  # Capped at max_weight

    w_downtrend = compute_volatility_target_weight(trend_state=0, vol=0.15, target_vol=0.15, max_weight=1.0)
    assert w_downtrend == 0.0  # Cash when trend is flat/down

    # 4. Cross-sectional ranking (C0)
    scores = {"ETF_A": 0.20, "ETF_B": -0.05, "ETF_C": 0.15, "ETF_D": 0.05}
    ranks = calc_cross_sectional_ranks(scores)
    assert ranks["ETF_A"] == 1.0  # Highest
    assert ranks["ETF_B"] == 0.0  # Lowest
    assert 0.0 < ranks["ETF_D"] < ranks["ETF_C"] < 1.0

    # 5. Dual Momentum (C1)
    # ETF_A: rank top, M252 > 0 -> receives weight
    # ETF_C: rank top, but M252 <= 0 -> filtered out (allocated to cash!)
    ts_trends = {"ETF_A": 1, "ETF_B": 0, "ETF_C": 0, "ETF_D": 1}
    dual_weights = compute_dual_momentum_weights(scores, ts_trends, top_k=2)
    assert dual_weights["ETF_A"] == 0.5
    assert dual_weights["ETF_C"] == 0.0  # Filtered by absolute momentum!
    assert dual_weights["ETF_B"] == 0.0
    assert dual_weights["ETF_D"] == 0.0
    # Sum of weights is 0.5 -> Remaining 0.5 is CASH in bear market


def test_momentum_strategy_generator_abstain():
    from app.services.strategy_evaluation.momentum_engine import MomentumStrategyEngine

    engine = MomentumStrategyEngine()
    # Short series: only 10 bars, looking for 120-day momentum
    short_df = pd.DataFrame({
        "trade_date": [f"2026-01-{i:02d}" for i in range(1, 11)],
        "close": [1.0 + i * 0.01 for i in range(1, 11)],
        "ret_1": [0.01] * 10,
    })
    res = engine.evaluate_single_asset_tsmom(
        ts_code="510300.SH",
        df=short_df,
        lookback=252,
        vol_lookback=20,
    )
    assert res.is_abstain()
    assert "insufficient_history" in str(res.missing_reason)
    assert res.target_weight == 0.0
