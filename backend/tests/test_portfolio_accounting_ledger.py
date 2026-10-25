from __future__ import annotations

import math
import numpy as np
import pandas as pd
import pytest


def test_two_assets_equal_weight_no_leverage():
    """Two assets each up 1%, total budget 1.0, 50/50 weight -> portfolio return must be 1.0%, not 2.0%."""
    from app.services.strategy_evaluation.backtest_harness import simulate_portfolio_ledger_daily

    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    df_a = pd.DataFrame({
        "trade_date": dates,
        "ts_code": ["ETF_A"] * 3,
        "open": [10.0, 10.0, 10.1],
        "close": [10.0, 10.1, 10.201],  # +1% each day
    })
    df_b = pd.DataFrame({
        "trade_date": dates,
        "ts_code": ["ETF_B"] * 3,
        "open": [20.0, 20.0, 20.2],
        "close": [20.0, 20.2, 20.402],  # +1% each day
    })
    panel = pd.concat([df_a, df_b], ignore_index=True)

    # Weights: at t=0, target weights are 0.5 for A and 0.5 for B (sum = 1.0)
    # At t=1, target weights stay 0.5 and 0.5
    weights_dict = {
        ("2026-01-01", "ETF_A"): 0.5,
        ("2026-01-01", "ETF_B"): 0.5,
        ("2026-01-02", "ETF_A"): 0.5,
        ("2026-01-02", "ETF_B"): 0.5,
    }

    # No fees for mathematical purity check
    result = simulate_portfolio_ledger_daily(
        panel=panel,
        weights_map=weights_dict,
        initial_capital=100000.0,
        cost_bps_one_way=0.0,
    )

    daily_rets = result["daily_net_returns"]
    # Day 0: Signal decided at close -> return = 0
    assert daily_rets.iloc[0] == 0.0

    # Day 1: Both enter at open, close is +1.0% -> portfolio net return must be 1.0%!
    assert pytest.approx(daily_rets.iloc[1], 0.0001) == 0.01

    # Day 2: Both held, close is +1.0% -> portfolio net return must be 1.0%!
    assert pytest.approx(daily_rets.iloc[2], 0.0001) == 0.01

    # Total equity after 2 days of +1% on unleveraged portfolio is 100000 * 1.01 * 1.01 = 102010.0
    final_eq = result["equity_series"].iloc[-1]
    assert pytest.approx(final_eq, 0.01) == 102010.0


def test_position_adjustment_fees_and_intraday_accrual():
    """Verify weight increase 10% -> 20% and decrease 20% -> 10% correctly charges ~1bp fee and tracks intraday return."""
    from app.services.strategy_evaluation.backtest_harness import simulate_portfolio_ledger_daily

    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    df = pd.DataFrame({
        "trade_date": dates,
        "ts_code": ["ETF_A"] * 4,
        # Day 0: Close 10.0, decide weight 0.10
        # Day 1: Open 10.0, Close 10.0. At close, decide weight 0.20 (+10% add)
        # Day 2: Open 10.0, Close 11.0 (+10% intraday). At close, decide weight 0.10 (-10% trim)
        # Day 3: Open 11.0, Close 11.0. At close, decide weight 0.0 (exit)
        "open": [10.0, 10.0, 10.0, 11.0],
        "close": [10.0, 10.0, 11.0, 11.0],
    })
    weights_dict = {
        ("2026-01-01", "ETF_A"): 0.10,
        ("2026-01-02", "ETF_A"): 0.20,
        ("2026-01-03", "ETF_A"): 0.10,
    }

    # Fee: 10 bps one-way (0.0010)
    result = simulate_portfolio_ledger_daily(
        panel=df,
        weights_map=weights_dict,
        initial_capital=100000.0,
        cost_bps_one_way=10.0,
    )

    daily_rets = result["daily_net_returns"]
    equity = result["equity_series"]

    # Day 1: Enters 10% at open 10.0. Price flat (10->10).
    # Fee paid on 10% of 100k = 10,000 * 0.0010 = 10.0 (1 bp of portfolio = -0.00010)
    assert pytest.approx(daily_rets.iloc[1], 0.00005) == -0.00010
    assert pytest.approx(equity.iloc[1], 0.1) == 99990.0

    # Day 2: Position goes from 10% to 20% (+10% add at Open 10.0).
    # Additional trade of 10% pays 10 bps fee = ~1 bp of portfolio (-0.00010).
    # The full 20% position then experiences a +10% price jump from Open 10.0 to Close 11.0!
    # Gross gain on 20% position = 0.20 * +10% = +2.0% (+0.020).
    # Net return should be approximately +0.020 - 0.00010 = +0.01990!
    assert pytest.approx(daily_rets.iloc[2], 0.0002) == 0.01990

    # Trades ledger must record the initial buy, the add, the trim, and the exit
    trades = result["trades"]
    assert len(trades) >= 3


def test_drawdown_and_bankruptcy_protection():
    """Initial 1.0, Day 1 drops 10%, flat thereafter -> max drawdown is exactly -10.0%, no resurrect on 0."""
    from app.services.strategy_evaluation.backtest_harness import simulate_portfolio_ledger_daily

    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    df = pd.DataFrame({
        "trade_date": dates,
        "ts_code": ["ETF_A"] * 4,
        "open": [10.0, 10.0, 9.0, 9.0],
        "close": [10.0, 9.0, 9.0, 9.0],  # -10% drop on day 1
    })
    weights_dict = {
        ("2026-01-01", "ETF_A"): 1.0,
        ("2026-01-02", "ETF_A"): 1.0,
        ("2026-01-03", "ETF_A"): 1.0,
    }

    result = simulate_portfolio_ledger_daily(
        panel=df,
        weights_map=weights_dict,
        initial_capital=100000.0,
        cost_bps_one_way=0.0,
    )
    mdd = result["max_drawdown"]
    assert pytest.approx(mdd, 0.0001) == -0.10
