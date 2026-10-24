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


def simulate_daily_portfolio_net_returns(
    df: pd.DataFrame,
    signals: pd.Series,
    cost_bps_one_way: float = 10.0,
) -> pd.Series:
    """Simulate daily portfolio net returns with next-day open price execution and fee deduction.

    - Signal at close of day t.
    - Entry day t+1: Enters at Open[t+1], holds to Close[t+1]. Return = (Close/Open - 1) - fee.
    - Intermediate holding days: Close[t+k] / Close[t+k-1] - 1.
    - Exit day t+m+1: Exits at Open[t+m+1] from previous Close. Return = (Open/Close - 1) - fee.
    - Cash days: Return = 0.0.
    """
    n = len(df)
    net_returns = pd.Series(0.0, index=df.index)
    if n < 2 or len(signals) != n:
        return net_returns

    one_way_fee = cost_bps_one_way / 10000.0

    in_position = False
    entry_idx = -1

    for i in range(n - 1):
        sig = float(signals.iloc[i]) if not pd.isna(signals.iloc[i]) else 0.0
        open_next = float(df["open"].iloc[i + 1])
        close_next = float(df["close"].iloc[i + 1])
        close_curr = float(df["close"].iloc[i])

        if not in_position and sig > 0:
            # Enter at next open
            in_position = True
            entry_idx = i + 1
            if open_next > 0:
                gross = close_next / open_next - 1.0
                net_returns.iloc[i + 1] = gross - one_way_fee
        elif in_position and sig > 0:
            # Hold through next day
            if close_curr > 0:
                net_returns.iloc[i + 1] = close_next / close_curr - 1.0
        elif in_position and sig <= 0:
            # Exit at next open (respecting T+1: cannot exit on same day as entry)
            if i + 1 > entry_idx:
                in_position = False
                if close_curr > 0:
                    gross = open_next / close_curr - 1.0
                    net_returns.iloc[i + 1] = gross - one_way_fee
            else:
                # T+1 constraint forces holding until at least day after entry
                if close_curr > 0:
                    net_returns.iloc[i + 1] = close_next / close_curr - 1.0
        else:
            # Cash day
            net_returns.iloc[i + 1] = 0.0

    return net_returns


def simulate_multi_asset_portfolio_net_returns(
    panel: pd.DataFrame,
    weight_col: str,
    cost_bps_one_way: float = 10.0,
) -> pd.Series:
    """Simulate multi-asset daily net portfolio returns with open execution and fee deduction.

    For each asset:
    - Weight w[t] is determined at day t close.
    - If entering from 0 to w[t] > 0: executes at open[t+1], return = (close[t+1]/open[t+1] - 1 - fee) * w[t].
    - If holding: return = (close[t+1]/close[t] - 1) * min(w[t], w[t-1]).
    - If exiting from w[t-1] to 0: executes at open[t+1], return = (open[t+1]/close[t] - 1 - fee) * w[t-1].
    - Cash earns 0.0.
    """
    one_way_fee = cost_bps_one_way / 10000.0
    asset_pnls: list[pd.DataFrame] = []

    for code, g in panel.groupby("ts_code"):
        g = g.sort_values("trade_date").copy()
        n = len(g)
        if n < 2:
            continue
        weights = g[weight_col].fillna(0.0).values
        opens = g["open"].values
        closes = g["close"].values
        dates = g["trade_date"].values

        pnl = np.zeros(n)
        for i in range(n - 1):
            w_curr = float(weights[i])
            w_prev = float(weights[i - 1]) if i > 0 else 0.0
            o_next = float(opens[i + 1])
            c_next = float(closes[i + 1])
            c_curr = float(closes[i])

            if w_curr > 0 and w_prev == 0:
                if o_next > 0:
                    ret = (c_next / o_next - 1.0) - one_way_fee
                    pnl[i + 1] = ret * w_curr
            elif w_curr > 0 and w_prev > 0:
                if c_curr > 0:
                    ret = (c_next / c_curr - 1.0)
                    pnl[i + 1] = ret * min(w_curr, w_prev)
            elif w_curr == 0 and w_prev > 0:
                if c_curr > 0:
                    ret = (o_next / c_curr - 1.0) - one_way_fee
                    pnl[i + 1] = ret * w_prev
            else:
                pnl[i + 1] = 0.0

        asset_pnls.append(pd.DataFrame({"trade_date": dates, "pnl": pnl}))

    if not asset_pnls:
        return pd.Series(dtype=float)

    all_pnls = pd.concat(asset_pnls, ignore_index=True)
    daily_port_pnl = all_pnls.groupby("trade_date")["pnl"].sum()
    return daily_port_pnl


def simulate_closed_trades_ledger(
    df: pd.DataFrame,
    signals: pd.Series,
    cost_bps_one_way: float = 10.0,
) -> list[dict[str, Any]]:
    """Simulate a realistic closed-trade ledger for China ETFs."""
    if len(df) != len(signals):
        raise ValueError("df and signals must have the same length")

    one_way_fee = cost_bps_one_way / 10000.0
    trades: list[dict[str, Any]] = []

    in_position = False
    entry_idx = -1
    entry_date = ""
    entry_price = 0.0

    n = len(df)
    for i in range(n - 1):
        sig = float(signals.iloc[i]) if not pd.isna(signals.iloc[i]) else 0.0
        next_open = float(df["open"].iloc[i + 1])
        next_date = str(pd.to_datetime(df["trade_date"].iloc[i + 1]).date())

        if not in_position and sig > 0:
            in_position = True
            entry_idx = i + 1
            entry_date = next_date
            entry_price = next_open
        elif in_position and sig <= 0:
            if i + 1 > entry_idx:
                exit_price = next_open
                gross_ret = exit_price / entry_price - 1.0
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
