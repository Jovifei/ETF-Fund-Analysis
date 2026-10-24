from __future__ import annotations

import math
import numpy as np
import pandas as pd
import pytest


def test_forward_return_window_alignment():
    """Verify that h-day forward return strictly measures Day 1 to Day h, NOT Day h to Day 2h."""
    from app.services.strategy_evaluation.momentum_engine import calc_forward_returns

    # Create 15 days of price data: P_t = 100 * (1.01)^t (1% compound daily return)
    daily_ret = 0.01
    prices = [100.0 * ((1.0 + daily_ret) ** t) for t in range(15)]
    df = pd.DataFrame({
        "trade_date": pd.date_range("2026-01-01", periods=15, freq="D"),
        "close": prices,
        "ret_1": [daily_ret] * 15,
    })

    fwd_df = calc_forward_returns(df, horizons=[1, 3, 7])

    # At t=0:
    # 1-day forward return should be P_1 / P_0 - 1 = (1.01)^1 - 1 = 0.01
    assert pytest.approx(fwd_df["fwd_1"].iloc[0], 0.0001) == (1.0 + daily_ret) ** 1 - 1.0

    # 3-day forward return at t=0 should be P_3 / P_0 - 1 = (1.01)^3 - 1 = 0.030301
    assert pytest.approx(fwd_df["fwd_3"].iloc[0], 0.0001) == (1.0 + daily_ret) ** 3 - 1.0

    # 7-day forward return at t=0 should be P_7 / P_0 - 1 = (1.01)^7 - 1
    # NOT P_14 / P_7 - 1 !
    expected_7d = (1.0 + daily_ret) ** 7 - 1.0
    assert pytest.approx(fwd_df["fwd_7"].iloc[0], 0.0001) == expected_7d

    # At t=7: 7-day forward return should be P_14 / P_7 - 1
    assert pytest.approx(fwd_df["fwd_7"].iloc[7], 0.0001) == expected_7d

    # At t=8: fewer than 7 days remain, so fwd_7 must be NaN
    assert pd.isna(fwd_df["fwd_7"].iloc[8])


def test_portfolio_net_daily_returns_with_open_execution_and_fees():
    """Verify daily net return series uses open price execution and deducts transaction costs."""
    from app.services.strategy_evaluation.backtest_harness import simulate_daily_portfolio_net_returns

    # Create 5 days:
    # Day 0: Signal at close = 1.0
    # Day 1: Open 100, Close 105. Signal at close = 1.0
    # Day 2: Open 105, Close 110. Signal at close = 0.0 (Exit signal)
    # Day 3: Open 112, Close 112. Signal at close = 0.0
    # Day 4: Open 112, Close 112. Signal at close = 0.0
    dates = pd.date_range("2026-01-01", periods=5, freq="D")
    df = pd.DataFrame({
        "trade_date": dates,
        "open": [100.0, 100.0, 105.0, 112.0, 112.0],
        "close": [100.0, 105.0, 110.0, 112.0, 112.0],
        "ret_1": [0.0, 0.05, 0.047619, 0.018182, 0.0],
    })
    signals = pd.Series([1.0, 1.0, 0.0, 0.0, 0.0], index=df.index)
    fee_bps = 10.0  # 10 bps one-way fee = 0.0010

    net_daily = simulate_daily_portfolio_net_returns(df, signals, cost_bps_one_way=fee_bps)

    # Day 0: No position yet (signal generated at close) -> return = 0.0
    assert net_daily.iloc[0] == 0.0

    # Day 1: Enters at Open 100.0, holds to Close 105.0 -> gross ret = 105/100 - 1 = +0.05
    # Deducts entry fee of 10 bps (0.0010) -> net ret ~ 0.0490
    assert pytest.approx(net_daily.iloc[1], 0.0001) == 0.05 - 0.0010

    # Day 2: Holds through day: Close 110.0 / Close 105.0 - 1 -> ret ~ +0.047619 (no trade fee)
    assert pytest.approx(net_daily.iloc[2], 0.0001) == 110.0 / 105.0 - 1.0

    # Day 3: Exit at Open 112.0 from previous Close 110.0 -> gross ret = 112/110 - 1 ~ 0.018182
    # Deducts exit fee of 10 bps (0.0010)
    assert pytest.approx(net_daily.iloc[3], 0.0001) == (112.0 / 110.0 - 1.0) - 0.0010

    # Day 4: Cash -> return = 0.0
    assert net_daily.iloc[4] == 0.0


def test_dual_momentum_vs_cross_sectional_fair_ablation():
    """Verify C0 and C1 use the exact same selection count (Top-K) for fair comparison."""
    from app.services.strategy_evaluation.momentum_engine import (
        compute_cross_sectional_top_k_weights,
        compute_dual_momentum_weights,
    )

    scores = {"ETF_A": 0.25, "ETF_B": 0.15, "ETF_C": 0.10, "ETF_D": 0.05, "ETF_E": -0.10}
    # Both use Top 3
    top_k = 3

    # C0: Pure Cross-Sectional Momentum
    w_c0 = compute_cross_sectional_top_k_weights(scores, top_k=top_k)
    assert pytest.approx(w_c0["ETF_A"], 0.001) == 1.0 / 3.0
    assert pytest.approx(w_c0["ETF_B"], 0.001) == 1.0 / 3.0
    assert pytest.approx(w_c0["ETF_C"], 0.001) == 1.0 / 3.0
    assert w_c0["ETF_D"] == 0.0
    assert w_c0["ETF_E"] == 0.0
    assert sum(w_c0.values()) == pytest.approx(1.0, 0.001)

    # C1: Dual Momentum (same top 3 candidates, but gated by absolute trend)
    # ETF_C has negative 12m trend (ts_trends = 0)
    ts_trends = {"ETF_A": 1, "ETF_B": 1, "ETF_C": 0, "ETF_D": 1, "ETF_E": 0}
    w_c1 = compute_dual_momentum_weights(scores, ts_trends, top_k=top_k)

    assert pytest.approx(w_c1["ETF_A"], 0.001) == 1.0 / 3.0
    assert pytest.approx(w_c1["ETF_B"], 0.001) == 1.0 / 3.0
    assert w_c1["ETF_C"] == 0.0  # Filtered by absolute trend! Allocated to cash!
    assert w_c1["ETF_D"] == 0.0
    assert w_c1["ETF_E"] == 0.0
    # Total equity is 2/3, remaining 1/3 is in cash
    assert sum(w_c1.values()) == pytest.approx(2.0 / 3.0, 0.001)
