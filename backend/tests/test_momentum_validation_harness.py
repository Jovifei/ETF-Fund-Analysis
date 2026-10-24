from __future__ import annotations

import math
import numpy as np
import pandas as pd
import pytest


def test_wilson_score_interval():
    from app.services.strategy_evaluation.backtest_harness import wilson_score_interval

    # Zero or empty
    lo, hi = wilson_score_interval(0, 0)
    assert math.isnan(lo) and math.isnan(hi)

    # TD9 test in report: 134 hits out of 239 signals
    lo, hi = wilson_score_interval(134, 239, confidence=0.95)
    # Wilson interval for 134/239 (56.07%) is approximately 49.7% to 62.2%
    assert pytest.approx(lo, 0.01) == 0.497
    assert pytest.approx(hi, 0.01) == 0.622
    assert lo < 0.5607 < hi


def test_calc_daily_portfolio_sharpe_and_drawdown():
    from app.services.strategy_evaluation.backtest_harness import (
        calc_daily_portfolio_sharpe,
        calc_max_drawdown,
    )

    # Constant positive return series -> std is 0 -> Sharpe is nan or safe
    const = pd.Series([0.001] * 50)
    sh_const = calc_daily_portfolio_sharpe(const)
    assert math.isnan(sh_const)

    # Normal random-like return series
    rets = pd.Series([0.01, -0.005, 0.008, -0.002, 0.015, -0.01] * 10)
    sh = calc_daily_portfolio_sharpe(rets)
    assert isinstance(sh, float)
    assert not math.isnan(sh)

    # Equity curve with 20% drawdown: 1.0 -> 1.2 -> 0.96 -> 1.1
    # Peak is 1.2, trough is 0.96 -> drawdown = (0.96 - 1.2) / 1.2 = -0.20 (-20%)
    equity = pd.Series([1.0, 1.2, 0.96, 1.1])
    mdd = calc_max_drawdown(equity)
    assert pytest.approx(mdd, 0.0001) == -0.20


def test_closed_trades_ledger():
    from app.services.strategy_evaluation.backtest_harness import simulate_closed_trades_ledger

    # Create dummy price series:
    # Day 0: Price 10.0, signal 1.0
    # Day 1: Open 10.0 (Buy executed with 10bps fee), Close 11.0, signal 1.0
    # Day 2: Open 11.0, Close 11.0, signal 0.0 (Exit signal at close)
    # Day 3: Open 11.0 (Sell executed with 10bps fee), Close 11.0
    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    df = pd.DataFrame({
        "trade_date": dates,
        "open": [10.0, 10.0, 11.0, 11.0],
        "close": [10.0, 11.0, 11.0, 11.0],
        "ret_1": [0.0, 0.10, 0.0, 0.0],
    })
    signals = pd.Series([1.0, 1.0, 0.0, 0.0], index=df.index)

    ledger = simulate_closed_trades_ledger(df, signals, cost_bps_one_way=10.0)
    assert len(ledger) == 1
    trade = ledger[0]
    assert trade["entry_date"] == str(dates[1].date())
    assert trade["exit_date"] == str(dates[3].date())
    assert trade["gross_return"] == pytest.approx(0.10, 0.001)  # 11.0 / 10.0 - 1 = +10%
    # Net return should deduct approx 20 bps roundtrip fee
    assert trade["net_return"] < trade["gross_return"]
    assert trade["net_return"] > 0.09
    assert trade["net_pnl_positive"] is True
