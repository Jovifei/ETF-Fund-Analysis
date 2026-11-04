"""Deterministic regression tests for 2026-10-26 audit gate remediation.

Covers:
1. P0: Missing open price is untradable; never fallback to 1.0 (prevents 100x equity distortion or 99% crash).
2. P0: Missing open on exit cannot sell; position is retained without artificial liquidation.
3. Corporate action split adjustment: prices scaled across 1:5 split without -80% drop.
4. Volatility calculation invariance: prices scaled by 10x produce identical annualized return volatility.
"""
from __future__ import annotations

import math
from datetime import date
import numpy as np
import pandas as pd
import pytest


def test_missing_open_is_untradable_never_fallback_to_one():
    """An asset priced at 100.0 with missing Open must NOT execute at 1.0 (which would buy 100x shares)."""
    from app.services.strategy_evaluation.backtest_harness import simulate_portfolio_ledger_daily

    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    df = pd.DataFrame({
        "trade_date": dates,
        "ts_code": ["EXPENSIVE_ETF"] * 3,
        # Day 0: Close 100.0, decide weight 1.0
        # Day 1: Open NaN (suspended), Close 100.0
        # Day 2: Open 100.0, Close 100.0
        "open": [100.0, np.nan, 100.0],
        "close": [100.0, 100.0, 100.0],
    })
    weights_dict = {
        ("2026-01-01", "EXPENSIVE_ETF"): 1.0,
        ("2026-01-02", "EXPENSIVE_ETF"): 1.0,
    }

    result = simulate_portfolio_ledger_daily(
        panel=df,
        weights_map=weights_dict,
        initial_capital=100000.0,
        cost_bps_one_way=0.0,
    )

    # Day 1: Open is NaN -> Untradable! Cannot buy at 1.0!
    # Equity on Day 1 must remain 100,000.0 (all cash), not 10,000,000.0!
    eq_day1 = result["equity_series"].iloc[1]
    assert eq_day1 == pytest.approx(100000.0, abs=1.0)
    # Day 2: Open is valid 100.0 -> Buys 1,000 shares at 100.0
    eq_day2 = result["equity_series"].iloc[2]
    assert eq_day2 == pytest.approx(100000.0, abs=1.0)


def test_missing_open_on_sell_cannot_liquidate_at_one():
    """Held position cannot be dumped at 1.0 when open is NaN; position must be retained."""
    from app.services.strategy_evaluation.backtest_harness import simulate_portfolio_ledger_daily

    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    df = pd.DataFrame({
        "trade_date": dates,
        "ts_code": ["HELD_ETF"] * 4,
        # Day 0: Close 50.0, decide weight 1.0
        # Day 1: Open 50.0, Close 50.0 -> Enters position
        # Day 2: Open NaN (suspended), Close 50.0. Decide weight 0.0 (exit)
        # Day 3: Open 50.0, Close 50.0 -> Exits position
        "open": [50.0, 50.0, np.nan, 50.0],
        "close": [50.0, 50.0, 50.0, 50.0],
    })
    weights_dict = {
        ("2026-01-01", "HELD_ETF"): 1.0,
        ("2026-01-02", "HELD_ETF"): 0.0,
        ("2026-01-03", "HELD_ETF"): 0.0,
    }

    result = simulate_portfolio_ledger_daily(
        panel=df,
        weights_map=weights_dict,
        initial_capital=100000.0,
        cost_bps_one_way=0.0,
    )

    # Day 2: Open is NaN, sell cannot execute at 1.0. Position is kept.
    # Equity must stay at 100,000.0, not drop to 2,000.0!
    eq_day2 = result["equity_series"].iloc[2]
    assert eq_day2 == pytest.approx(100000.0, abs=1.0)


def test_volatility_scale_invariance_returns_vs_prices():
    """Annualized volatility must be computed on returns, making it invariant to absolute price level."""
    from app.services.strategy_evaluation.momentum_engine import calc_volatility_annualized

    # Scenario: two assets with identical percentage returns, but one trades at 1.0 and other at 100.0
    rets = pd.Series([0.01, -0.02, 0.015, -0.01, 0.005] * 5)
    prices_low = (1.0 + rets).cumprod() * 1.0
    prices_high = (1.0 + rets).cumprod() * 100.0

    vol_rets_low = calc_volatility_annualized(prices_low.pct_change().dropna(), window=20)
    vol_rets_high = calc_volatility_annualized(prices_high.pct_change().dropna(), window=20)

    # Both must be identical
    assert vol_rets_low.iloc[-1] == pytest.approx(vol_rets_high.iloc[-1], abs=1e-5)

    # Passing prices directly would produce a 100x difference, which is a critical bug!
    vol_err_low = calc_volatility_annualized(prices_low, window=20)
    vol_err_high = calc_volatility_annualized(prices_high, window=20)
    assert not (vol_err_low.iloc[-1] == pytest.approx(vol_err_high.iloc[-1], abs=1e-5))


def test_corporate_action_split_adjustment_for_513100():
    """513100.SH 1:5 split on 2022-01-14 must scale historical prices by 1/5 to prevent -80% jump."""
    from app.providers.corporate_action_contract import research_history_rows
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(trade_date=date(2022, 1, 12), open=5.160, high=5.200, low=5.100, close=5.192, pre_close=5.101, volume=1000, amount=5192, adjust="none", source="test"),
        SimpleNamespace(trade_date=date(2022, 1, 14), open=1.010, high=1.020, low=1.010, close=1.015, pre_close=5.192, volume=5000, amount=5075, adjust="none", source="test"),
    ]

    adj_rows = research_history_rows(rows, "513100.SH")
    assert len(adj_rows) == 2
    # Pre-split price 5.192 should be scaled by 1/5 = ~1.0384
    assert adj_rows[0].close == pytest.approx(5.192 / 5.0, abs=0.001)
    # Day-over-day return across split: 1.015 / (5.192 / 5) - 1 = -2.25%, NOT -80.45%!
    ret_pct = adj_rows[1].pct_change
    assert ret_pct == pytest.approx(-2.25, abs=0.05)


def test_forward_returns_missing_data_not_imputed_as_zero():
    """Missing or NaN returns inside the forward window must evaluate to NaN, not artificially filled with 0.0."""
    from app.services.strategy_evaluation.momentum_engine import calc_forward_returns

    dates = pd.date_range("2026-01-01", periods=6, freq="D")
    df = pd.DataFrame({
        "trade_date": dates,
        # Day 2 return is NaN (suspended/missing)
        "ret_1": [0.01, 0.02, np.nan, 0.01, 0.02, 0.01],
    })

    fwd_df = calc_forward_returns(df, horizons=[3])
    # Day 0 forward 3 days needs Day 1, Day 2, Day 3 returns. Since Day 2 is NaN, Day 0 fwd_3 must be NaN!
    assert pd.isna(fwd_df["fwd_3"].iloc[0])
    # Day 2 forward 3 days needs Day 3, Day 4, Day 5 returns (0.01, 0.02, 0.01). All valid!
    assert not pd.isna(fwd_df["fwd_3"].iloc[2])
    expected = (1.0 + 0.01) * (1.0 + 0.02) * (1.0 + 0.01) - 1.0
    assert fwd_df["fwd_3"].iloc[2] == pytest.approx(expected, abs=1e-5)


def test_momentum_engine_abstains_on_invalid_current_close():
    """MomentumStrategyEngine must abstain with invalid_close_price when current close is <= 0 or NaN."""
    from app.services.strategy_evaluation.momentum_engine import MomentumStrategyEngine

    engine = MomentumStrategyEngine()
    dates = pd.date_range("2025-01-01", periods=300, freq="D")

    # Case 1: current close is NaN
    df_nan = pd.DataFrame({
        "trade_date": dates,
        "close": [1.0] * 299 + [np.nan],
        "ret_1": [0.0] * 300,
    })
    res_nan = engine.evaluate_single_asset_tsmom("510300.SH", df_nan)
    assert res_nan.is_abstain()
    assert res_nan.missing_reason == "invalid_close_price"

    # Case 2: current close is <= 0
    df_zero = pd.DataFrame({
        "trade_date": dates,
        "close": [1.0] * 299 + [0.0],
        "ret_1": [0.0] * 300,
    })
    res_zero = engine.evaluate_single_asset_tsmom("510300.SH", df_zero)
    assert res_zero.is_abstain()
    assert res_zero.missing_reason == "invalid_close_price"
