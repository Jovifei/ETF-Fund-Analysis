from __future__ import annotations

import math
from typing import Any, Tuple

import numpy as np
import pandas as pd

from app.services.strategy_evaluation.contracts import EvaluationMetrics


def wilson_score_interval(
    hits: int,
    total: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion.

    Used to avoid misleading point estimates when sample count is low (e.g. TD9 events).
    """
    if total <= 0 or hits < 0:
        return float("nan"), float("nan")

    # z-critical value: 1.95996 for 95%
    z = 1.959963984540054 if confidence == 0.95 else 1.6448536269514722
    p = hits / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = p + z2 / (2.0 * total)
    spread = z * math.sqrt(p * (1.0 - p) / total + z2 / (4.0 * total * total))
    lower = max(0.0, (center - spread) / denom)
    upper = min(1.0, (center + spread) / denom)
    return float(lower), float(upper)


def calc_daily_portfolio_sharpe(daily_returns: pd.Series) -> float:
    """Calculate annualized Sharpe ratio from daily strategy returns over a fixed date range."""
    clean = daily_returns.dropna()
    if len(clean) < 20:
        return float("nan")
    std = float(clean.std(ddof=1))
    if std <= 0.0 or not math.isfinite(std):
        return float("nan")
    mean = float(clean.mean())
    return float(math.sqrt(252) * mean / std)


def calc_max_drawdown(equity_series: pd.Series) -> float:
    """Calculate maximum drawdown from an equity curve: min((equity - peak) / peak)."""
    clean = equity_series.dropna()
    if len(clean) < 2:
        return 0.0
    peak = clean.cummax()
    dd = (clean - peak) / peak
    return float(dd.min())


def simulate_closed_trades_ledger(
    df: pd.DataFrame,
    signals: pd.Series,
    cost_bps_one_way: float = 10.0,
) -> list[dict[str, Any]]:
    """Simulate a realistic closed-trade ledger for China ETFs.

    - Signal at close of day t.
    - Earliest execution at open of day t+1.
    - Roundtrip transaction cost: 2 * cost_bps_one_way (default 20 bps: 10 bps buy + 10 bps sell).
    - T+1 sell constraint: shares bought on day t+1 cannot be sold on day t+1.
    """
    if len(df) != len(signals):
        raise ValueError("df and signals must have the same length")

    one_way_fee = cost_bps_one_way / 10000.0
    trades: list[dict[str, Any]] = []

    in_position = False
    entry_idx = -1
    entry_date = ""
    entry_price = 0.0

    n = len(df)
    # Align signals to next-day open
    # Day i generates signal[i] at close; trade executes at Day i+1 open
    for i in range(n - 1):
        sig = float(signals.iloc[i]) if not pd.isna(signals.iloc[i]) else 0.0
        next_open = float(df["open"].iloc[i + 1])
        next_date = str(pd.to_datetime(df["trade_date"].iloc[i + 1]).date())

        if not in_position and sig > 0:
            # Enter trade at next open
            in_position = True
            entry_idx = i + 1
            entry_date = next_date
            entry_price = next_open
        elif in_position and sig <= 0:
            # Must respect T+1: cannot exit on same day as entry
            if i + 1 > entry_idx:
                exit_price = next_open
                gross_ret = exit_price / entry_price - 1.0
                # Net of buy fee and sell fee
                net_ret = ((exit_price * (1.0 - one_way_fee)) / (entry_price * (1.0 + one_way_fee))) - 1.0
                holding_days = (i + 1) - entry_idx
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": next_date,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "gross_return": gross_ret,
                    "net_return": net_ret,
                    "net_pnl_positive": net_ret > 0.0,
                    "holding_days": holding_days,
                })
                in_position = False

    return trades
