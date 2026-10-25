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
    Note: Standard Wilson interval assumes independent Bernoulli trials; for overlapping forward
    horizons or cross-correlated assets, it represents descriptive uncertainty, not formal alpha proof.
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


def simulate_portfolio_ledger_daily(
    panel: pd.DataFrame,
    weights_map: dict[tuple[str, str], float],
    initial_capital: float = 100000.0,
    cost_bps_one_way: float = 10.0,
) -> dict[str, Any]:
    """Simulate a rigorous, unified portfolio cash & position ledger with Open execution and fees.

    - Unleveraged budget: sum(w_i) <= 1.0 at all times. Remaining is cash (earns 0.0).
    - Decisions formed at Close(t); orders executed at Open(t+1).
    - Positions experience overnight gap (Close(t) -> Open(t+1)) before rebalance.
    - At Open(t+1):
      * Trims/Exits execute first: proceeds increase cash, minus fee.
      * Adds/Entries execute second: cost deducted from cash, minus fee.
      * Fee is charged on actual delta traded: |delta_V| * fee_rate (10 bps = 0.0010).
    - Positions then experience intraday return from Open(t+1) to Close(t+1).
    - Daily net return = Equity(t+1) / Equity(t) - 1.
    - Bankruptcy protection: if Equity <= 0, stops at 0.0 (no resurrection).
    """
    fee_rate = cost_bps_one_way / 10000.0

    # Ensure date strings in YYYY-MM-DD
    panel_df = panel.copy()
    panel_df["date_str"] = pd.to_datetime(panel_df["trade_date"]).dt.strftime("%Y-%m-%d")

    unique_dates = sorted(panel_df["date_str"].unique())
    if len(unique_dates) < 2:
        return {
            "daily_net_returns": pd.Series(0.0, index=unique_dates),
            "equity_series": pd.Series(initial_capital, index=unique_dates),
            "trades": [],
            "max_drawdown": 0.0,
            "annualized_sharpe": float("nan"),
            "is_bankrupt": False,
        }

    # Pre-index price lookup: (date_str, ts_code) -> (open, close)
    price_lookup: dict[tuple[str, str], tuple[float, float]] = {}
    for _, row in panel_df.iterrows():
        d = str(row["date_str"])
        c = str(row["ts_code"])
        o_val = float(row["open"]) if not pd.isna(row["open"]) else float("nan")
        c_val = float(row["close"]) if not pd.isna(row["close"]) else float("nan")
        price_lookup[(d, c)] = (o_val, c_val)

    # State tracking
    curr_cash = float(initial_capital)
    curr_equity = float(initial_capital)
    # positions: ts_code -> shares (float)
    positions: dict[str, float] = {}

    equity_records: list[float] = [curr_equity]
    return_records: list[float] = [0.0]
    trades: list[dict[str, Any]] = []
    is_bankrupt = False

    # Pre-index weights by date for O(1) daily lookup
    weights_by_date: dict[str, dict[str, float]] = {}
    for (d, c), w in weights_map.items():
        if w > 0.0 and math.isfinite(w):
            weights_by_date.setdefault(d, {})[c] = float(w)

    for k in range(len(unique_dates) - 1):
        d_curr = unique_dates[k]
        d_next = unique_dates[k + 1]

        if is_bankrupt or curr_equity <= 0.0:
            is_bankrupt = True
            curr_equity = 0.0
            equity_records.append(0.0)
            return_records.append(0.0)
            continue

        # 1. Overnight gap on existing positions: Close(d_curr) -> Open(d_next)
        pre_trade_positions_value = 0.0
        pre_trade_asset_values: dict[str, float] = {}
        for code, shares in list(positions.items()):
            if shares <= 0.0:
                continue
            p_next = price_lookup.get((d_next, code))
            if p_next is None or math.isnan(p_next[0]) or p_next[0] <= 0:
                # Missing open: fallback to yesterday close
                p_curr = price_lookup.get((d_curr, code))
                open_val = p_curr[1] if (p_curr and not math.isnan(p_curr[1])) else 1.0
            else:
                open_val = p_next[0]

            val = shares * open_val
            pre_trade_asset_values[code] = val
            pre_trade_positions_value += val

        pre_trade_equity = curr_cash + pre_trade_positions_value
        if pre_trade_equity <= 0.0:
            is_bankrupt = True
            curr_equity = 0.0
            positions.clear()
            equity_records.append(0.0)
            return_records.append(0.0)
            continue

        # 2. Target weights decided at Close(d_curr)
        raw_weights: dict[str, float] = weights_by_date.get(d_curr, {}).copy()

        # Budget constraint: sum(w) <= 1.0
        sum_w = sum(raw_weights.values())
        if sum_w > 1.0:
            target_weights = {c: w / sum_w for c, w in raw_weights.items()}
        else:
            target_weights = raw_weights.copy()

        # Target value for each asset
        target_asset_values: dict[str, float] = {
            c: pre_trade_equity * target_weights.get(c, 0.0)
            for c in set(list(pre_trade_asset_values.keys()) + list(target_weights.keys()))
        }

        # 3. Rebalance at Open(d_next)
        # Sells/Trims first
        for code, target_val in list(target_asset_values.items()):
            pre_val = pre_trade_asset_values.get(code, 0.0)
            delta = target_val - pre_val
            if delta < -1e-6:
                trade_amt = abs(delta)
                p_next = price_lookup.get((d_next, code))
                o_price = p_next[0] if (p_next and not math.isnan(p_next[0]) and p_next[0] > 0) else 1.0
                fee = trade_amt * fee_rate
                shares_sold = trade_amt / o_price
                curr_cash += (trade_amt - fee)
                positions[code] = max(0.0, positions.get(code, 0.0) - shares_sold)
                if positions[code] <= 1e-6:
                    del positions[code]
                trades.append({
                    "trade_date": d_next,
                    "ts_code": code,
                    "side": "sell",
                    "price": o_price,
                    "shares": shares_sold,
                    "trade_amount": trade_amt,
                    "fee": fee,
                })

        # Buys/Adds second
        for code, target_val in list(target_asset_values.items()):
            pre_val = pre_trade_asset_values.get(code, 0.0)
            delta = target_val - pre_val
            if delta > 1e-6:
                trade_amt = delta
                needed_cash = trade_amt * (1.0 + fee_rate)
                if curr_cash < needed_cash:
                    trade_amt = max(0.0, curr_cash / (1.0 + fee_rate))
                if trade_amt > 1e-6:
                    fee = trade_amt * fee_rate
                    p_next = price_lookup.get((d_next, code))
                    o_price = p_next[0] if (p_next and not math.isnan(p_next[0]) and p_next[0] > 0) else 1.0
                    shares_bought = trade_amt / o_price
                    curr_cash -= (trade_amt + fee)
                    positions[code] = positions.get(code, 0.0) + shares_bought
                    trades.append({
                        "trade_date": d_next,
                        "ts_code": code,
                        "side": "buy",
                        "price": o_price,
                        "shares": shares_bought,
                        "trade_amount": trade_amt,
                        "fee": fee,
                    })

        # 4. Intraday price movement: Open(d_next) -> Close(d_next)
        post_positions_value = 0.0
        for code, shares in list(positions.items()):
            p_next = price_lookup.get((d_next, code))
            if p_next is None or math.isnan(p_next[1]) or p_next[1] <= 0:
                # Fallback to open
                c_price = p_next[0] if (p_next and not math.isnan(p_next[0])) else 1.0
            else:
                c_price = p_next[1]
            post_positions_value += shares * c_price

        new_equity = curr_cash + post_positions_value
        if new_equity <= 0.0:
            is_bankrupt = True
            new_equity = 0.0

        daily_ret = (new_equity / curr_equity - 1.0) if curr_equity > 0 else 0.0
        curr_equity = new_equity
        equity_records.append(curr_equity)
        return_records.append(daily_ret)

    eq_series = pd.Series(equity_records, index=unique_dates)
    ret_series = pd.Series(return_records, index=unique_dates)

    mdd = calc_max_drawdown(eq_series)
    sh = calc_daily_portfolio_sharpe(ret_series)

    return {
        "daily_net_returns": ret_series,
        "equity_series": eq_series,
        "trades": trades,
        "max_drawdown": mdd,
        "annualized_sharpe": sh,
        "is_bankrupt": is_bankrupt,
    }


def simulate_daily_portfolio_net_returns(
    df: pd.DataFrame,
    signals: pd.Series,
    cost_bps_one_way: float = 10.0,
) -> pd.Series:
    """Convenience single-asset wrapper over the unified portfolio ledger engine."""
    ts_code = str(df["ts_code"].iloc[0]) if "ts_code" in df and not df.empty else "ASSET"
    weights_map: dict[tuple[str, str], float] = {}
    for i in range(len(df)):
        d_str = pd.to_datetime(df["trade_date"].iloc[i]).strftime("%Y-%m-%d")
        sig = float(signals.iloc[i]) if not pd.isna(signals.iloc[i]) else 0.0
        weights_map[(d_str, ts_code)] = 1.0 if sig > 0 else 0.0

    df_named = df.copy()
    df_named["ts_code"] = ts_code
    res = simulate_portfolio_ledger_daily(
        panel=df_named,
        weights_map=weights_map,
        initial_capital=100000.0,
        cost_bps_one_way=cost_bps_one_way,
    )
    return res["daily_net_returns"]


def simulate_closed_trades_ledger(
    df: pd.DataFrame,
    signals: pd.Series,
    cost_bps_one_way: float = 10.0,
) -> list[dict[str, Any]]:
    """Simulate realistic closed trades ledger for China ETFs."""
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
