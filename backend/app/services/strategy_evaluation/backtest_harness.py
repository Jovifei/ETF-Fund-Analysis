from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Tuple
import numpy as np
import pandas as pd


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

    z = 1.959963984540054  # 95%
    if confidence == 0.90:
        z = 1.6448536269514722
    elif confidence == 0.99:
        z = 2.5758293035489004

    p = float(hits) / float(total)
    denom = 1.0 + (z * z) / float(total)
    center = (p + (z * z) / (2.0 * float(total))) / denom
    margin = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * float(total))) / float(total))) / denom

    lo = max(0.0, center - margin)
    hi = min(1.0, center + margin)
    return float(lo), float(hi)


def calc_max_drawdown(equity_series: pd.Series) -> float:
    """Calculate maximum peak-to-trough drawdown of an equity curve."""
    if equity_series.empty:
        return 0.0
    cummax = equity_series.cummax()
    dd = (equity_series - cummax) / cummax.replace(0, np.nan)
    min_dd = float(dd.min())
    return min_dd if not math.isnan(min_dd) else 0.0


def calc_daily_portfolio_sharpe(daily_returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Calculate annualized Sharpe ratio from daily net return series."""
    valid = daily_returns.dropna()
    if len(valid) < 20:
        return float("nan")
    mean_ret = float(valid.mean())
    std_ret = float(valid.std(ddof=1))
    if std_ret <= 1e-8 or not math.isfinite(std_ret):
        return float("nan")
    daily_rf = (1.0 + risk_free_rate) ** (1.0 / 252.0) - 1.0
    return float((mean_ret - daily_rf) / std_ret * math.sqrt(252))


def simulate_daily_portfolio_net_returns(
    panel: pd.DataFrame,
    weights_series: pd.Series,
    initial_capital: float = 100000.0,
    cost_bps_one_way: float = 10.0,
) -> pd.Series:
    """Simulate daily portfolio net returns based on target weights decided at Day t Close,

    executed at Day t+1 Open with 1-way trading costs, and marked to market at Day t+1 Close.
    """
    df = panel.copy()
    ts_code = str(df["ts_code"].iloc[0]) if "ts_code" in df and not df.empty else "ASSET"
    df["ts_code"] = ts_code
    df["target_weight"] = weights_series.reindex(df.index).fillna(0.0)
    df = df.sort_values("trade_date").reset_index(drop=True)

    unique_dates = df["trade_date"].drop_duplicates().sort_values().tolist()
    if len(unique_dates) < 2:
        return pd.Series(index=df.index, dtype=float)

    weights_map = {
        (str(r["trade_date"].strftime("%Y-%m-%d") if hasattr(r["trade_date"], "strftime") else str(r["trade_date"])[:10]), str(r["ts_code"])): float(r["target_weight"])
        for _, r in df.iterrows()
    }

    res = simulate_portfolio_ledger_daily(
        panel=df,
        weights_map=weights_map,
        initial_capital=initial_capital,
        cost_bps_one_way=cost_bps_one_way,
    )
    return res["daily_net_returns"]


def simulate_portfolio_ledger_daily(
    panel: pd.DataFrame,
    weights_map: dict[tuple[str, str], float],
    initial_capital: float = 100000.0,
    cost_bps_one_way: float = 10.0,
) -> dict[str, Any]:
    """Unified daily portfolio cash and positions ledger simulation.

    Guarantees:
    1. Capital budget constraint: sum(target_weights) <= 1.0. Unallocated weight stays as cash (0 interest).
    2. Execution: Orders executed at Day t+1 Open. If Open price is missing/NaN/<=0, asset is UNTRADABLE (no 1.0 fallback!).
    3. Frictional accounting: Fees charged on actual traded value (10 bps one-way).
    4. Exact valuation: Day-end NAV strictly equals cash balance + sum of position values.
    5. Distinction between executed order lines and true closed round-trip trades (via FIFO matching).
    """
    fee_rate = cost_bps_one_way / 10000.0
    df = panel.copy()

    df["date_str"] = df["trade_date"].apply(
        lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x)[:10]
    )
    df["code_str"] = df["ts_code"].astype(str)

    unique_dates = sorted(df["date_str"].unique())
    if len(unique_dates) < 2:
        empty_s = pd.Series([0.0], index=unique_dates)
        return {
            "daily_net_returns": empty_s,
            "equity_series": pd.Series([initial_capital], index=unique_dates),
            "trades": [],
            "round_trip_trades": [],
            "order_count": 0,
            "max_drawdown": 0.0,
            "annualized_sharpe": 0.0,
            "is_bankrupt": False,
            "daily_ledger": [],
        }

    price_lookup: dict[tuple[str, str], tuple[float, float]] = {}
    for _, row in df.iterrows():
        d = row["date_str"]
        c = row["code_str"]
        o_val = float(row["open"]) if not pd.isna(row["open"]) else float("nan")
        c_val = float(row["close"]) if not pd.isna(row["close"]) else float("nan")
        price_lookup[(d, c)] = (o_val, c_val)

    curr_cash = float(initial_capital)
    curr_equity = float(initial_capital)
    positions: dict[str, float] = {}  # ts_code -> shares
    last_known_close: dict[str, float] = {}

    equity_records: list[float] = [curr_equity]
    return_records: list[float] = [0.0]
    trades: list[dict[str, Any]] = []
    daily_ledger: list[dict[str, Any]] = [{
        "trade_date": unique_dates[0],
        "cash": curr_cash,
        "positions_value": 0.0,
        "nav": curr_equity,
        "daily_fee": 0.0,
        "daily_turnover": 0.0,
        "daily_return": 0.0,
    }]
    is_bankrupt = False

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
            daily_ledger.append({
                "trade_date": d_next,
                "cash": 0.0,
                "positions_value": 0.0,
                "nav": 0.0,
                "daily_fee": 0.0,
                "daily_turnover": 0.0,
                "daily_return": 0.0,
            })
            continue

        # 1. Overnight gap on existing positions: Close(d_curr) -> Open(d_next)
        pre_trade_positions_value = 0.0
        pre_trade_asset_values: dict[str, float] = {}
        for code, shares in list(positions.items()):
            if shares <= 0.0:
                continue
            p_next = price_lookup.get((d_next, code))
            if p_next is not None and not math.isnan(p_next[0]) and p_next[0] > 0:
                open_val = p_next[0]
            else:
                p_curr = price_lookup.get((d_curr, code))
                if p_curr and not math.isnan(p_curr[1]) and p_curr[1] > 0:
                    open_val = p_curr[1]
                else:
                    open_val = last_known_close.get(code, 0.0)

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
            daily_ledger.append({
                "trade_date": d_next,
                "cash": 0.0,
                "positions_value": 0.0,
                "nav": 0.0,
                "daily_fee": 0.0,
                "daily_turnover": 0.0,
                "daily_return": 0.0,
            })
            continue

        # 2. Target weights decided at Close(d_curr)
        raw_weights: dict[str, float] = weights_by_date.get(d_curr, {}).copy()

        sum_w = sum(raw_weights.values())
        if sum_w > 1.0:
            target_weights = {c: w / sum_w for c, w in raw_weights.items()}
        else:
            target_weights = raw_weights.copy()

        target_asset_values: dict[str, float] = {
            c: pre_trade_equity * target_weights.get(c, 0.0)
            for c in set(list(pre_trade_asset_values.keys()) + list(target_weights.keys()))
        }

        daily_fee = 0.0
        daily_turnover = 0.0

        # 3. Rebalance at Open(d_next)
        # Sells/Trims first
        for code, target_val in list(target_asset_values.items()):
            pre_val = pre_trade_asset_values.get(code, 0.0)
            delta = target_val - pre_val
            if delta < -1e-6:
                p_next = price_lookup.get((d_next, code))
                if p_next is None or math.isnan(p_next[0]) or p_next[0] <= 0:
                    continue
                o_price = p_next[0]
                trade_amt = abs(delta)
                shares_sold = min(positions.get(code, 0.0), trade_amt / o_price)
                if shares_sold <= 0:
                    continue
                actual_trade_amt = shares_sold * o_price
                fee = actual_trade_amt * fee_rate
                curr_cash += (actual_trade_amt - fee)
                positions[code] = max(0.0, positions.get(code, 0.0) - shares_sold)
                if positions[code] <= 1e-6:
                    del positions[code]
                daily_fee += fee
                daily_turnover += actual_trade_amt
                trades.append({
                    "trade_date": d_next,
                    "ts_code": code,
                    "side": "sell",
                    "price": o_price,
                    "shares": shares_sold,
                    "trade_amount": actual_trade_amt,
                    "fee": fee,
                })

        # Buys/Adds second
        for code, target_val in list(target_asset_values.items()):
            pre_val = pre_trade_asset_values.get(code, 0.0)
            delta = target_val - pre_val
            if delta > 1e-6:
                p_next = price_lookup.get((d_next, code))
                if p_next is None or math.isnan(p_next[0]) or p_next[0] <= 0:
                    continue
                o_price = p_next[0]
                trade_amt = delta
                needed_cash = trade_amt * (1.0 + fee_rate)
                if curr_cash < needed_cash:
                    trade_amt = max(0.0, curr_cash / (1.0 + fee_rate))
                if trade_amt > 1e-6:
                    shares_bought = trade_amt / o_price
                    actual_trade_amt = shares_bought * o_price
                    fee = actual_trade_amt * fee_rate
                    curr_cash -= (actual_trade_amt + fee)
                    positions[code] = positions.get(code, 0.0) + shares_bought
                    daily_fee += fee
                    daily_turnover += actual_trade_amt
                    trades.append({
                        "trade_date": d_next,
                        "ts_code": code,
                        "side": "buy",
                        "price": o_price,
                        "shares": shares_bought,
                        "trade_amount": actual_trade_amt,
                        "fee": fee,
                    })

        # 4. Intraday price movement: Open(d_next) -> Close(d_next)
        post_positions_value = 0.0
        for code, shares in list(positions.items()):
            p_next = price_lookup.get((d_next, code))
            if p_next is not None and not math.isnan(p_next[1]) and p_next[1] > 0:
                c_price = p_next[1]
                last_known_close[code] = c_price
            elif p_next is not None and not math.isnan(p_next[0]) and p_next[0] > 0:
                c_price = p_next[0]
            else:
                p_curr = price_lookup.get((d_curr, code))
                if p_curr and not math.isnan(p_curr[1]) and p_curr[1] > 0:
                    c_price = p_curr[1]
                else:
                    c_price = last_known_close.get(code, 0.0)

            post_positions_value += shares * c_price

        new_equity = curr_cash + post_positions_value
        if new_equity <= 0.0:
            is_bankrupt = True
            new_equity = 0.0

        daily_ret = (new_equity / curr_equity - 1.0) if curr_equity > 0 else 0.0
        curr_equity = new_equity
        equity_records.append(curr_equity)
        return_records.append(daily_ret)
        daily_ledger.append({
            "trade_date": d_next,
            "cash": round(curr_cash, 4),
            "positions_value": round(post_positions_value, 4),
            "nav": round(curr_equity, 4),
            "daily_fee": round(daily_fee, 4),
            "daily_turnover": round(daily_turnover, 4),
            "daily_return": round(daily_ret, 6),
        })

    eq_series = pd.Series(equity_records, index=unique_dates)
    ret_series = pd.Series(return_records, index=unique_dates)

    mdd = calc_max_drawdown(eq_series)
    sh = calc_daily_portfolio_sharpe(ret_series)

    # Reconstruct true closed round-trip trades via FIFO matching
    round_trip_trades: list[dict[str, Any]] = []
    buy_queues: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        code = t["ts_code"]
        if t["side"] == "buy":
            buy_queues.setdefault(code, []).append({
                "trade_date": t["trade_date"],
                "shares": t["shares"],
                "price": t["price"],
                "fee_per_share": t["fee"] / t["shares"] if t["shares"] > 0 else 0.0,
            })
        elif t["side"] == "sell":
            rem_sold = t["shares"]
            while rem_sold > 1e-6 and buy_queues.get(code):
                earliest_buy = buy_queues[code][0]
                matched_shares = min(rem_sold, earliest_buy["shares"])
                entry_date = earliest_buy["trade_date"]
                exit_date = t["trade_date"]
                entry_price = earliest_buy["price"]
                exit_price = t["price"]
                buy_fee = matched_shares * earliest_buy["fee_per_share"]
                sell_fee = matched_shares * (t["fee"] / t["shares"] if t["shares"] > 0 else 0.0)
                gross_pnl = (exit_price - entry_price) * matched_shares
                net_pnl = gross_pnl - (buy_fee + sell_fee)
                net_ret = (exit_price / entry_price - 1.0) - (2.0 * fee_rate)
                round_trip_trades.append({
                    "ts_code": code,
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "shares": matched_shares,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "gross_pnl": gross_pnl,
                    "fees": buy_fee + sell_fee,
                    "net_pnl": net_pnl,
                    "net_return": net_ret,
                })
                rem_sold -= matched_shares
                earliest_buy["shares"] -= matched_shares
                if earliest_buy["shares"] <= 1e-6:
                    buy_queues[code].pop(0)

    return {
        "daily_net_returns": ret_series,
        "equity_series": eq_series,
        "trades": trades,
        "round_trip_trades": round_trip_trades,
        "order_count": len(trades),
        "max_drawdown": mdd,
        "annualized_sharpe": sh,
        "is_bankrupt": is_bankrupt,
        "daily_ledger": daily_ledger,
    }


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

        if math.isnan(next_open) or next_open <= 0:
            continue

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
