#!/usr/bin/env python3
"""Empirical factor evaluation on US equity ETF cross-border proxies (513100.SH & 513500.SH).

Calculates multi-horizon ICs, directional accuracy, net Sharpe (with Open execution & 20 bps friction),
and closed-trade ledger performance specifically for US equity exposure.
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKTREE_ROOT / "backend"))

from app.services.strategy_evaluation.backtest_harness import (
    calc_daily_portfolio_sharpe,
    calc_max_drawdown,
    simulate_closed_trades_ledger,
    simulate_daily_portfolio_net_returns,
    wilson_score_interval,
)
from app.services.strategy_evaluation.momentum_engine import (
    calc_forward_returns,
    calc_momentum,
    calc_volatility_annualized,
)

DB_PATH = Path(r"F:\ETF_Data\ETF-Fund-Analysis\db\research.sqlite3")
OUT_DIR = WORKTREE_ROOT / "research" / "calc_decision" / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)
HORIZONS = [1, 3, 7, 20, 60]
COST_BPS_ONE_WAY = 10.0


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def calc_td9_signal(close: pd.Series) -> pd.Series:
    sig = pd.Series(0.0, index=close.index)
    c4 = close.shift(4)
    bull_count = 0
    bear_count = 0
    for i in range(len(close)):
        if pd.isna(c4.iloc[i]):
            continue
        if close.iloc[i] > c4.iloc[i]:
            bull_count += 1
            bear_count = 0
        elif close.iloc[i] < c4.iloc[i]:
            bear_count += 1
            bull_count = 0
        else:
            bull_count = 0
            bear_count = 0

        if bear_count == 9:
            sig.iloc[i] = 1.0  # Buy setup completed
        elif bull_count == 9:
            sig.iloc[i] = -1.0
    return sig


def load_us_etf_bars() -> pd.DataFrame:
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        df = pd.read_sql_query(
            """
            SELECT i.ts_code, i.name, d.trade_date, d.open, d.high, d.low, d.close, d.volume
            FROM daily_bars d
            JOIN instruments i ON i.id = d.instrument_id
            WHERE i.ts_code IN ('513100.SH', '513500.SH')
            ORDER BY i.ts_code, d.trade_date ASC
            """,
            conn,
        )
    finally:
        conn.close()

    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


def add_us_factors(df: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for code, g in df.groupby("ts_code"):
        g = g.sort_values("trade_date").reset_index(drop=True)
        g = calc_forward_returns(g, HORIZONS)
        c = g["close"]
        h = g["high"]
        l = g["low"]

        # Momentum
        g["mom_20"] = calc_momentum(c, 20)
        g["mom_60"] = calc_momentum(c, 60)
        g["mom_120"] = calc_momentum(c, 120)
        g["mom_252"] = calc_momentum(c, 252)
        g["tsmom_12m"] = np.where(g["mom_252"] > 0, 1.0, 0.0)

        # Volatility
        vol20 = calc_volatility_annualized(c, 20)
        g["tsmom_volscaled"] = np.where(g["mom_252"] > 0, 1.0 / vol20.replace(0, np.nan), 0.0)

        # Moving average
        ma20 = c.rolling(20, min_periods=20).mean()
        ma60 = c.rolling(60, min_periods=60).mean()
        g["dual_ma_20_60"] = np.where(ma20 > ma60, 1.0, 0.0)

        # Donchian channel
        hh20 = h.shift(1).rolling(20).max()
        ll10 = l.shift(1).rolling(10).min()
        pos = np.zeros(len(g))
        curr = 0.0
        for i in range(len(g)):
            if pd.isna(hh20.iloc[i]) or pd.isna(ll10.iloc[i]):
                continue
            if c.iloc[i] > hh20.iloc[i]:
                curr = 1.0
            elif c.iloc[i] < ll10.iloc[i]:
                curr = 0.0
            pos[i] = curr
        g["turtle_20_10"] = pos

        # MACD
        dif = ema(c, 12) - ema(c, 26)
        dea = ema(dif, 9)
        g["macd"] = np.where(dif > dea, 1.0, 0.0)

        # Mean reversion z-score
        m20 = c.rolling(20).mean()
        s20 = c.rolling(20).std(ddof=1)
        z = (c - m20) / s20.replace(0, np.nan)
        g["z_mr_20"] = -z.clip(-3, 3)

        # TD9 setup
        g["td9_setup"] = calc_td9_signal(c)

        parts.append(g)

    return pd.concat(parts, ignore_index=True)


def evaluate_asset_factor(df: pd.DataFrame, factor_col: str, factor_kind: str) -> dict[str, Any]:
    sub = df.dropna(subset=[factor_col]).copy()
    if len(sub) < 50:
        return {}

    # Signal mapping: for continuous, signal = 1 if score > 0
    if factor_kind == "continuous":
        sig_series = pd.Series(np.where(sub[factor_col] > 0, 1.0, 0.0), index=sub.index)
    else:
        sig_series = pd.Series(np.where(sub[factor_col] > 0, 1.0, 0.0), index=sub.index)

    # 1. Daily net returns with Next-day Open execution & 10 bps one-way fee
    net_daily = simulate_daily_portfolio_net_returns(sub, sig_series, cost_bps_one_way=COST_BPS_ONE_WAY)
    eq_series = (1.0 + net_daily).cumprod()
    sh = calc_daily_portfolio_sharpe(net_daily)
    mdd = calc_max_drawdown(eq_series)

    # 2. Closed trades ledger
    trades = simulate_closed_trades_ledger(sub, sig_series, cost_bps_one_way=COST_BPS_ONE_WAY)
    trade_stats = {}
    if trades:
        net_pnls = [t["net_return"] for t in trades]
        pos_pnls = [r for r in net_pnls if r > 0]
        neg_pnls = [r for r in net_pnls if r < 0]
        tot = len(net_pnls)
        trade_stats = {
            "total_trades": tot,
            "net_win_rate": round(len(pos_pnls) / tot * 100, 2) if tot > 0 else 0.0,
            "profit_factor": round(sum(pos_pnls) / abs(sum(neg_pnls)), 3) if neg_pnls and sum(neg_pnls) != 0 else None,
            "net_expectancy_bps": round(float(np.mean(net_pnls)) * 10000.0, 1) if tot > 0 else 0.0,
        }

    # 3. Multi-horizon IC and hit rate
    horizon_metrics = {}
    for h in HORIZONS:
        fwd_col = f"fwd_{h}"
        valid = sub.dropna(subset=[factor_col, fwd_col])
        if len(valid) > 20:
            ic = float(valid[factor_col].corr(valid[fwd_col], method="spearman"))
            pos_count = int((valid[fwd_col] > 0).sum())
            n = len(valid)
            hr = pos_count / n if n > 0 else float("nan")
            ci_lo, ci_hi = wilson_score_interval(pos_count, n)
            horizon_metrics[f"h{h}"] = {
                "ic": round(ic, 4) if not math.isnan(ic) else 0.0,
                "hit_rate": round(hr * 100, 2),
                "wilson_ci": [round(ci_lo * 100, 2), round(ci_hi * 100, 2)],
            }

    return {
        "factor": factor_col,
        "net_sharpe": round(sh, 3) if not math.isnan(sh) else 0.0,
        "max_drawdown": round(mdd * 100, 2),
        "trade_stats": trade_stats,
        "horizons": horizon_metrics,
    }


def main() -> None:
    print("--- Evaluating US Equity ETF Cross-Border Factors (513100.SH / 513500.SH) ---")
    df = load_us_etf_bars()
    df_feat = add_us_factors(df)

    factors = [
        ("tsmom_12m", "binary"),
        ("tsmom_volscaled", "continuous"),
        ("turtle_20_10", "binary"),
        ("dual_ma_20_60", "binary"),
        ("macd", "binary"),
        ("z_mr_20", "continuous"),
        ("td9_setup", "binary"),
    ]

    all_results = {}
    for code, g in df_feat.groupby("ts_code"):
        name = g["name"].iloc[0]
        n_bars = len(g)
        print(f"\nEvaluating {code} ({name}) - {n_bars} bars:")
        asset_res = {}
        for fac_name, fac_kind in factors:
            res = evaluate_asset_factor(g, fac_name, fac_kind)
            asset_res[fac_name] = res
            print(
                f"  [{fac_name:16s}] Net Sharpe: {res.get('net_sharpe', 0):+.3f} | MDD: {res.get('max_drawdown', 0):.1f}% | "
                f"WinRate: {res.get('trade_stats', {}).get('net_win_rate', 'n/a')}% | "
                f"Expectancy: {res.get('trade_stats', {}).get('net_expectancy_bps', 'n/a')} bps"
            )
        all_results[code] = {
            "name": name,
            "bars": n_bars,
            "date_range": [g["trade_date"].min().strftime("%Y-%m-%d"), g["trade_date"].max().strftime("%Y-%m-%d")],
            "factors": asset_res,
        }

    out_json = OUT_DIR / "us_etf_empirical_metrics.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\nSaved US ETF factor metrics to {out_json}")


if __name__ == "__main__":
    main()
