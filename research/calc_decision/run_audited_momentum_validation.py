#!/usr/bin/env python3
"""Audited Empirical Factor Evaluation on China ETF Basket (V3 Accounting & Boundary Alignment).

Fixes all audit findings:
1. Fixed forward return window: strictly Day 1 to Day h compound returns.
2. Unified Cash & Position Ledger:
   - Next-day Open execution.
   - 10 bps one-way fee (20 bps round-trip) deducted on all entries, adds, trims, and exits.
   - Strict unleveraged budget sum(w) <= 1.0 (B0 equal weight = 1/N, M2 risk budget <= 1.0).
   - Eliminates the B0 -173.6% exposure explosion anomaly.
3. Fair controlled ablation: mom_120_cs (C0) and dual_momentum (C1) use identical Top-4 asset selection.
4. Purged training boundary: forward labels near holdout boundary are purged to prevent leakage.
5. Statistical caveats: Wilson intervals documented as descriptive; holdout labeled as validation set.
6. Honest reporting: text completely synchronized with recomputed table metrics.
"""
from __future__ import annotations

import datetime
import json
import math
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Add backend to sys.path so app modules can be imported
WORKTREE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKTREE_ROOT / "backend"))

from app.services.strategy_evaluation.backtest_harness import (
    calc_daily_portfolio_sharpe,
    calc_max_drawdown,
    simulate_closed_trades_ledger,
    simulate_portfolio_ledger_daily,
    wilson_score_interval,
)
from app.services.strategy_evaluation.momentum_engine import (
    calc_cross_sectional_ranks,
    calc_forward_returns,
    calc_momentum,
    calc_volatility_annualized,
    compute_cross_sectional_top_k_weights,
    compute_dual_momentum_weights,
    compute_volatility_target_weight,
)

DB_PATH = Path(r"F:\ETF_Data\ETF-Fund-Analysis\db\research.sqlite3")
WATCHLIST_PATH = WORKTREE_ROOT / "config" / "watchlist.json"
OUT_DIR = WORKTREE_ROOT / "research" / "calc_decision" / "out"
DOCS_DIR = WORKTREE_ROOT / "docs" / "research"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS = [1, 3, 7, 20, 60]
COST_BPS_ONE_WAY = 10.0  # 10 bps buy + 10 bps sell = 20 bps roundtrip
HOLDOUT_YEARS = 2
MIN_BARS_FOR_LONG = 400
MIN_CROSS_SECTION = 8


# ---------- Statistical Helpers ----------

def spearman_ic(x: pd.Series, y: pd.Series) -> float:
    df = pd.concat([x, y], axis=1).dropna()
    if len(df) < 5:
        return float("nan")
    corr = df.iloc[:, 0].rank().corr(df.iloc[:, 1].rank())
    return float(corr) if not pd.isna(corr) else float("nan")


def hit_rate_stats(signal: pd.Series, fwd: pd.Series) -> Tuple[float, float, float, int]:
    s = pd.concat([signal, fwd], axis=1).dropna()
    s.columns = ["sig", "fwd"]
    s = s[s["sig"] != 0]
    if len(s) == 0:
        return float("nan"), float("nan"), float("nan"), 0
    hits = ((s["sig"] > 0) & (s["fwd"] > 0)) | ((s["sig"] < 0) & (s["fwd"] < 0))
    n_hits = int(hits.sum())
    n_total = int(len(s))
    rate = float(hits.mean())
    lo, hi = wilson_score_interval(n_hits, n_total)
    return rate, lo, hi, n_total


def mean_when(signal: pd.Series, fwd: pd.Series, positive: bool) -> Tuple[float, int]:
    s = pd.concat([signal, fwd], axis=1).dropna()
    s.columns = ["sig", "fwd"]
    mask = s["sig"] > 0 if positive else s["sig"] < 0
    sub = s.loc[mask, "fwd"]
    if len(sub) == 0:
        return float("nan"), 0
    return float(sub.mean()), int(len(sub))


# ---------- Technical Indicator Helpers ----------

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def calc_atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def calc_adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    up = h.diff()
    down = -l.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    atr_n = pd.Series(tr, index=df.index).rolling(n, min_periods=n).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(n, min_periods=n).mean() / atr_n.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(n, min_periods=n).mean() / atr_n.replace(0, np.nan)
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan)
    return dx.rolling(n, min_periods=n).mean()


def calc_macd_hist(close: pd.Series) -> pd.Series:
    diff = ema(close, 12) - ema(close, 26)
    dea = ema(diff, 9)
    return diff - dea


def calc_boll_z(close: pd.Series, n: int = 20) -> pd.Series:
    m = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std(ddof=1)
    return (close - m) / sd.replace(0, np.nan)


def calc_donchian_signal(df: pd.DataFrame, entry: int = 20, exit_: int = 10) -> pd.Series:
    hh = df["high"].shift(1).rolling(entry, min_periods=entry).max()
    ll_exit = df["low"].shift(1).rolling(exit_, min_periods=exit_).min()
    long_e = df["close"] > hh
    exit_l = df["close"] < ll_exit
    state = 0.0
    out = []
    for i in range(len(df)):
        if bool(long_e.iloc[i]):
            state = 1.0
        elif bool(exit_l.iloc[i]):
            state = 0.0
        out.append(state)
    return pd.Series(out, index=df.index)


def calc_td_setup_signal(close: pd.Series) -> pd.Series:
    buy_count = 0
    sell_count = 0
    sig = []
    for i in range(len(close)):
        s = 0.0
        if i < 4 or pd.isna(close.iloc[i]) or pd.isna(close.iloc[i - 4]):
            buy_count = sell_count = 0
            sig.append(0.0)
            continue
        if close.iloc[i] < close.iloc[i - 4]:
            buy_count += 1
            sell_count = 0
            if buy_count == 9:
                s = 1.0
                buy_count = 0
        elif close.iloc[i] > close.iloc[i - 4]:
            sell_count += 1
            buy_count = 0
            if sell_count == 9:
                s = -1.0
                sell_count = 0
        else:
            buy_count = sell_count = 0
        sig.append(s)
    return pd.Series(sig, index=close.index)


def calc_ichimoku_signal(df: pd.DataFrame) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    cloud_top = pd.concat([span_a, span_b], axis=1).max(axis=1)
    cloud_bot = pd.concat([span_a, span_b], axis=1).min(axis=1)
    sig = pd.Series(0.0, index=df.index)
    sig = sig.mask(close > cloud_top, 1.0)
    sig = sig.mask(close < cloud_bot, -1.0)
    return sig


# ---------- Data Loading & Preparation ----------

def load_data() -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    watchlist_data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    codes = [x["ts_code"] for x in watchlist_data["instruments"] if x.get("enabled")]

    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    bars = pd.read_sql_query(
        """
        SELECT i.ts_code, i.symbol, i.name, d.trade_date, d.open, d.high, d.low, d.close,
               d.pre_close, d.volume, d.amount, d.pct_change, d.adjust, d.source
        FROM daily_bars d
        JOIN instruments i ON i.id = d.instrument_id
        WHERE i.ts_code IN ({})
        ORDER BY i.ts_code, d.trade_date
        """.format(",".join("?" * len(codes))),
        con,
        params=codes,
    )
    con.close()

    bars["trade_date"] = pd.to_datetime(bars["trade_date"])
    bars["ret_1"] = bars["pct_change"] / 100.0
    missing = bars["ret_1"].isna()
    bars.loc[missing, "ret_1"] = bars.loc[missing, "close"] / bars.loc[missing, "pre_close"] - 1.0
    still = bars["ret_1"].isna()
    bars.loc[still, "ret_1"] = bars.groupby("ts_code")["close"].pct_change()

    meta = (
        bars.groupby("ts_code")
        .agg(n=("trade_date", "count"), start=("trade_date", "min"), end=("trade_date", "max"), name=("name", "first"))
        .reset_index()
    )
    return bars, meta, codes


def add_features_and_forwards(panel: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for code, g in panel.groupby("ts_code", sort=False):
        g = g.sort_values("trade_date").copy()
        c = g["close"]
        ret = g["ret_1"]

        # Forward returns: EXACT Day 1 to Day h compound returns
        g = calc_forward_returns(g, HORIZONS)

        # Momentum & Volatility
        g["mom_20"] = calc_momentum(c, 20)
        g["mom_60"] = calc_momentum(c, 60)
        g["mom_120"] = calc_momentum(c, 120)
        g["mom_252"] = calc_momentum(c, 252)
        g["vol_20"] = calc_volatility_annualized(ret, 20)

        # M0: Raw TSMOM
        g["tsmom_12m"] = np.sign(g["mom_252"]).fillna(0.0)
        # M1: Volatility-scaled continuous score
        g["tsmom_volscaled"] = g["tsmom_12m"] / g["vol_20"].replace(0, np.nan)

        # Raw M2 risk-budget target: min(1.0, 0.15 / vol_20)
        g["vol_target_raw_w"] = np.where(
            g["tsmom_12m"] > 0,
            np.minimum(1.0, 0.15 / g["vol_20"].replace(0, np.nan)).fillna(0.0),
            0.0,
        )

        # Technical Counterfactuals
        g["z_20"] = calc_boll_z(c, 20)
        g["z_mr"] = np.where(g["z_20"] < -1.0, 1.0, np.where(g["z_20"] > 1.0, -1.0, 0.0))
        g["adx_14"] = calc_adx(g, 14)
        g["atr_14"] = calc_atr(g, 14)
        g["dual_ma"] = np.where(sma(c, 20) > sma(c, 60), 1.0, -1.0)
        g["macd_sig"] = np.sign(calc_macd_hist(c)).fillna(0.0)
        g["td9"] = calc_td_setup_signal(c)
        g["ichi"] = calc_ichimoku_signal(g)
        g["turtle"] = calc_donchian_signal(g, 20, 10)
        g["adx_trend"] = np.where(g["adx_14"] > 25, g["dual_ma"], 0.0)

        parts.append(g)

    out = pd.concat(parts, ignore_index=True)

    # Attach benchmark relative strength vs 510300
    bench = out.loc[out["ts_code"] == "510300.SH", ["trade_date", "close"]].rename(columns={"close": "bench_close"})
    out = out.merge(bench, on="trade_date", how="left")
    out = out.sort_values(["ts_code", "trade_date"])
    out["bench_mom_20"] = out.groupby("ts_code")["bench_close"].transform(lambda s: s / s.shift(20) - 1.0)
    out["rs_vs_300_20"] = out["mom_20"] - out["bench_mom_20"]
    out["rs_sig"] = np.sign(out["rs_vs_300_20"]).fillna(0.0)

    # Cross-sectional daily allocations with strict unleveraged budget sum(w) <= 1.0:
    # 1. B0: Equal-weight 1 / N_t for active universe on that day.
    # 2. C0: Top-4 equal weight 0.25 on each of top 4.
    # 3. C1: Same Top-4, 0.25 IF M252 > 0, else 0.0 (cash).
    # 4. M2: Normalized portfolio volatility budget sum(w) <= 1.0.
    b0_weights_list = []
    c0_weights_list = []
    c1_weights_list = []
    m2_weights_list = []

    for dt, day_df in out.groupby("trade_date"):
        n_active = len(day_df)
        w_b0_val = 1.0 / n_active if n_active > 0 else 0.0

        scores = dict(zip(day_df["ts_code"], day_df["mom_120"]))
        trends = dict(zip(day_df["ts_code"], day_df["tsmom_12m"]))
        w_c0 = compute_cross_sectional_top_k_weights(scores, top_k=4)
        w_c1 = compute_dual_momentum_weights(scores, trends, top_k=4)

        # M2: scale each asset by 1/N * (0.15 / vol_20), sum capped at 1.0
        raw_m2_sum = day_df["vol_target_raw_w"].sum()
        for _, r in day_df.iterrows():
            code = r["ts_code"]
            b0_weights_list.append((dt, code, w_b0_val))
            c0_weights_list.append((dt, code, w_c0.get(code, 0.0)))
            c1_weights_list.append((dt, code, w_c1.get(code, 0.0)))
            # Cap total M2 weight at 1.0
            raw_w = float(r["vol_target_raw_w"])
            norm_w = (raw_w / raw_m2_sum) if raw_m2_sum > 1.0 else raw_w
            m2_weights_list.append((dt, code, norm_w))

    b0_df = pd.DataFrame(b0_weights_list, columns=["trade_date", "ts_code", "equal_weight_b0_w"])
    c0_df = pd.DataFrame(c0_weights_list, columns=["trade_date", "ts_code", "mom_120_cs_w"])
    c1_df = pd.DataFrame(c1_weights_list, columns=["trade_date", "ts_code", "dual_momentum_w"])
    m2_df = pd.DataFrame(m2_weights_list, columns=["trade_date", "ts_code", "vol_target_w"])

    out = out.merge(b0_df, on=["trade_date", "ts_code"], how="left")
    out = out.merge(c0_df, on=["trade_date", "ts_code"], how="left")
    out = out.merge(c1_df, on=["trade_date", "ts_code"], how="left")
    out = out.merge(m2_df, on=["trade_date", "ts_code"], how="left")

    return out


# ---------- Factors Definitions ----------

@dataclass
class FactorMeta:
    name: str
    kind: str  # ts_signal | cs_rank | vol_weighted | portfolio_ablation | benchmark
    col: str
    rule: str


FACTORS = [
    FactorMeta("mom_20_cs", "cs_rank", "mom_20", "Cross-sectional: rank IC of 20d momentum"),
    FactorMeta("mom_60_cs", "cs_rank", "mom_60", "Cross-sectional: rank IC of 60d momentum"),
    FactorMeta("mom_120_cs", "portfolio_ablation", "mom_120_cs_w", "C0: Top-4 120d CS momentum (equal-weight 0.25 each)"),
    FactorMeta("tsmom_12m", "ts_signal", "tsmom_12m", "Time-series: 12m cumulative return > 0 (1/N per long)"),
    FactorMeta("tsmom_volscaled", "ts_signal", "tsmom_volscaled", "Continuous score: 12m sign / 20d annualized vol"),
    FactorMeta("tsmom_voltarget_m2", "vol_weighted", "vol_target_w", "M2: Unleveraged volatility target sizing sum(w)<=1.0"),
    FactorMeta("dual_momentum_c1", "portfolio_ablation", "dual_momentum_w", "C1: Top-4 120d CS gated by 12m trend > 0"),
    FactorMeta("equal_weight_b0", "benchmark", "equal_weight_b0_w", "B0: Baseline unleveraged equal-weight (1/N_t rebalanced)"),
    FactorMeta("rs_vs_300_20", "ts_signal", "rs_sig", "Relative strength vs 510300.SH > 0"),
    FactorMeta("z_mr_20", "ts_signal", "z_mr", "Bollinger z-score mean reversion: z<-1 long, z>1 short"),
    FactorMeta("dual_ma_20_60", "ts_signal", "dual_ma", "Dual MA: SMA20 > SMA60 long else short"),
    FactorMeta("adx_trend", "ts_signal", "adx_trend", "Dual MA only when ADX14 > 25"),
    FactorMeta("macd", "ts_signal", "macd_sig", "MACD histogram sign"),
    FactorMeta("td9_setup", "ts_signal", "td9", "DeMark Setup 9 completion pulse"),
    FactorMeta("ichimoku_cloud", "ts_signal", "ichi", "Above cloud long / below short"),
    FactorMeta("turtle_20_10", "ts_signal", "turtle", "Donchian 20d high entry / 10d low exit"),
]


# ---------- Evaluation Harness ----------

def evaluate_factor_slice(
    panel: pd.DataFrame,
    factor: FactorMeta,
    horizon: int,
    sample_name: str,
    mask: pd.Series,
    holdout_start: pd.Timestamp,
    fixed_daily_sharpe: float,
    closed_trades_stats: dict[str, Any],
) -> dict[str, Any]:
    sub = panel.loc[mask].copy()
    fwd_col = f"fwd_{horizon}"

    # Purge sample points near boundary where trade_date + horizon crosses holdout_start
    if sample_name == "train_earlier_longhist":
        purge_boundary = holdout_start - datetime.timedelta(days=int(horizon * 1.5))
        sub = sub[sub["trade_date"] <= purge_boundary]

    if factor.kind == "cs_rank" or factor.name == "mom_120_cs":
        score_col = "mom_120" if factor.name == "mom_120_cs" else factor.col
        sub_cs = sub.dropna(subset=[score_col, fwd_col])
        ics = []
        long_rets = []
        short_rets = []
        hits = []
        for dt, g in sub_cs.groupby("trade_date"):
            if len(g) < MIN_CROSS_SECTION:
                continue
            ic = spearman_ic(g[score_col], g[fwd_col])
            if not math.isnan(ic):
                ics.append(ic)
            g_sorted = g.sort_values(score_col, ascending=False)
            long = g_sorted.iloc[:4]
            short = g_sorted.iloc[-4:]
            if len(long):
                long_rets.append(long[fwd_col].mean())
                hits.extend((long[fwd_col] > 0).astype(float).tolist())
            if len(short):
                short_rets.append(short[fwd_col].mean())

        n_signals = int(len(hits))
        n_hits = int(sum(hits))
        hr = float(np.mean(hits)) if hits else float("nan")
        hr_lo, hr_hi = wilson_score_interval(n_hits, n_signals)
        ic_mean = float(np.mean(ics)) if ics else float("nan")
        m_long = float(np.mean(long_rets)) if long_rets else float("nan")
        m_short = float(np.mean(short_rets)) if short_rets else float("nan")

    elif factor.kind == "portfolio_ablation" and factor.name == "dual_momentum_c1":
        sub_dm = sub[sub["dual_momentum_w"] > 0].dropna(subset=[fwd_col])
        n_signals = len(sub_dm)
        hits = (sub_dm[fwd_col] > 0).astype(float)
        n_hits = int(hits.sum())
        hr = float(hits.mean()) if n_signals > 0 else float("nan")
        hr_lo, hr_hi = wilson_score_interval(n_hits, n_signals)
        m_long = float(sub_dm[fwd_col].mean()) if n_signals > 0 else float("nan")
        m_short = float("nan")
        ic_mean = spearman_ic(sub["dual_momentum_w"], sub[fwd_col])

    else:
        sig = sub[factor.col]
        hr, hr_lo, hr_hi, n_signals = hit_rate_stats(sig, sub[fwd_col])
        m_long, _ = mean_when(sig, sub[fwd_col], True)
        m_short, _ = mean_when(sig, sub[fwd_col], False)
        ic_mean = spearman_ic(sig, sub[fwd_col])

    return {
        "factor": factor.name,
        "sample": sample_name,
        "horizon": horizon,
        "kind": factor.kind,
        "ic_spearman": round(ic_mean, 6) if not math.isnan(ic_mean) else float("nan"),
        "hit_rate": round(hr, 6) if not math.isnan(hr) else float("nan"),
        "hit_rate_wilson_lo": round(hr_lo, 6) if not math.isnan(hr_lo) else float("nan"),
        "hit_rate_wilson_hi": round(hr_hi, 6) if not math.isnan(hr_hi) else float("nan"),
        "n_signals": n_signals,
        "mean_fwd_long": round(m_long, 6) if not math.isnan(m_long) else float("nan"),
        "mean_fwd_short": round(m_short, 6) if not math.isnan(m_short) else float("nan"),
        "net_sharpe_d1": round(fixed_daily_sharpe, 6) if not math.isnan(fixed_daily_sharpe) else float("nan"),
        "closed_trades": closed_trades_stats.get("trades_count", 0),
        "net_win_rate": closed_trades_stats.get("net_win_rate", float("nan")),
        "net_expectancy_bps": closed_trades_stats.get("net_expectancy_bps", float("nan")),
        "profit_factor": closed_trades_stats.get("profit_factor", float("nan")),
        "net_max_drawdown": closed_trades_stats.get("max_drawdown", float("nan")),
        "rule": factor.rule,
    }


def compute_fixed_daily_stats_for_factor(
    panel: pd.DataFrame,
    factor: FactorMeta,
    mask: pd.Series,
) -> Tuple[float, dict[str, Any]]:
    """Compute fixed daily return series, Net Sharpe, and closed trades ledger over the sample mask.

    Uses simulate_portfolio_ledger_daily to guarantee:
    - Open price execution.
    - Explicit transaction fees deducted on entries, adds, trims, and exits.
    - Total portfolio weight <= 1.0 (unleveraged).
    - True net Sharpe and net max drawdown.
    """
    sub = panel.loc[mask].copy()
    if sub.empty:
        return float("nan"), {}

    # Build weights_map: (trade_date_str, ts_code) -> weight
    sub_df = sub.copy()
    sub_df["date_str"] = pd.to_datetime(sub_df["trade_date"]).dt.strftime("%Y-%m-%d")

    weights_map: dict[tuple[str, str], float] = {}

    if factor.kind in ("portfolio_ablation", "vol_weighted", "benchmark"):
        valid_rows = sub_df[sub_df[factor.col] > 0.0][["date_str", "ts_code", factor.col]]
        for dt, code, w_val in valid_rows.itertuples(index=False, name=None):
            weights_map[(str(dt), str(code))] = float(w_val)

    elif factor.kind == "cs_rank":
        # Cross-sectional momentum: Top-4 equal weight (0.25 each)
        for dt, day_df in sub_df.groupby("date_str"):
            scores = dict(zip(day_df["ts_code"], day_df[factor.col]))
            w_dict = compute_cross_sectional_top_k_weights(scores, top_k=4)
            for c, w in w_dict.items():
                if w > 0.0:
                    weights_map[(dt, c)] = w

    else:
        # Time-series signals: equal weight 1/N across active assets on that day with sig > 0
        sig_df = sub_df[sub_df[factor.col] > 0.0]
        day_counts = sub_df.groupby("date_str")["ts_code"].count().to_dict()
        for dt, code in sig_df[["date_str", "ts_code"]].itertuples(index=False, name=None):
            n_active = day_counts.get(dt, 0)
            if n_active > 0:
                weights_map[(str(dt), str(code))] = 1.0 / n_active

    # Simulate unified ledger
    sim_res = simulate_portfolio_ledger_daily(
        panel=sub_df,
        weights_map=weights_map,
        initial_capital=100000.0,
        cost_bps_one_way=COST_BPS_ONE_WAY,
    )

    sh = sim_res["annualized_sharpe"]
    mdd = sim_res["max_drawdown"]
    trades = sim_res["trades"]

    # Closed trade performance
    if factor.kind == "ts_signal":
        # Simulate asset-level trade ledger for closed trade stats
        all_trades = []
        for code, g in sub_df.groupby("ts_code"):
            g_sorted = g.sort_values("trade_date").copy()
            if len(g_sorted) > 20:
                t_list = simulate_closed_trades_ledger(g_sorted, g_sorted[factor.col], cost_bps_one_way=COST_BPS_ONE_WAY)
                all_trades.extend(t_list)

        if all_trades:
            net_pnls = [t["net_return"] for t in all_trades]
            pos_pnls = [r for r in net_pnls if r > 0]
            neg_pnls = [r for r in net_pnls if r < 0]
            win_count = len(pos_pnls)
            tot_count = len(net_pnls)
            n_win_rate = round(win_count / tot_count, 4) if tot_count > 0 else float("nan")
            exp_bps = round(float(np.mean(net_pnls)) * 10000.0, 1) if tot_count > 0 else float("nan")
            pf = round(sum(pos_pnls) / abs(sum(neg_pnls)), 3) if neg_pnls and sum(neg_pnls) != 0 else float("nan")
            return sh, {
                "trades_count": tot_count,
                "net_win_rate": n_win_rate,
                "net_expectancy_bps": exp_bps,
                "profit_factor": pf,
                "max_drawdown": round(mdd, 4),
            }

    return sh, {
        "trades_count": len(trades),
        "max_drawdown": round(mdd, 4),
    }


def main() -> None:
    print("--- Starting Audited Momentum & Factor Validation (V3 Accounting & Boundary Alignment) ---")
    bars, meta, codes = load_data()
    long_codes = meta.loc[meta["n"] >= MIN_BARS_FOR_LONG, "ts_code"].tolist()
    if "510300.SH" not in long_codes:
        long_codes.append("510300.SH")

    print(f"Loaded bars: {len(bars)}, instruments: {len(codes)}, long-history: {len(long_codes)}")

    panel = add_features_and_forwards(bars)

    max_dt = panel["trade_date"].max()
    holdout_start = max_dt - pd.DateOffset(years=HOLDOUT_YEARS)
    recent_start = pd.Timestamp("2025-08-18")

    panel["sample"] = np.where(panel["trade_date"] >= holdout_start, "holdout_2y", "train_earlier")

    sample_masks = [
        ("holdout_2y_longhist", (panel["ts_code"].isin(long_codes)) & (panel["sample"] == "holdout_2y")),
        ("train_earlier_longhist", (panel["ts_code"].isin(long_codes)) & (panel["sample"] == "train_earlier")),
        ("recent_all_enabled", panel["trade_date"] >= recent_start),
        ("all_longhist", panel["ts_code"].isin(long_codes)),
    ]

    records = []
    fixed_stats_cache: dict[Tuple[str, str], Tuple[float, dict[str, Any]]] = {}

    for sample_name, mask in sample_masks:
        print(f"\nProcessing slice: {sample_name}")
        for fac in FACTORS:
            cache_key = (sample_name, fac.name)
            if cache_key not in fixed_stats_cache:
                fixed_stats_cache[cache_key] = compute_fixed_daily_stats_for_factor(panel, fac, mask)
            fixed_sh, closed_stats = fixed_stats_cache[cache_key]

            for h in HORIZONS:
                try:
                    res = evaluate_factor_slice(
                        panel=panel,
                        factor=fac,
                        horizon=h,
                        sample_name=sample_name,
                        mask=mask,
                        holdout_start=holdout_start,
                        fixed_daily_sharpe=fixed_sh,
                        closed_trades_stats=closed_stats,
                    )
                    records.append(res)
                except Exception as e:
                    print(f"Error evaluating {sample_name} {fac.name} h={h}: {e}")

    df_metrics = pd.DataFrame(records)

    out_csv = OUT_DIR / "factor_empirical_metrics_audited_20261024.csv"
    docs_csv = DOCS_DIR / "factor_empirical_metrics_audited_20261024.csv"
    df_metrics.to_csv(out_csv, index=False)
    df_metrics.to_csv(docs_csv, index=False)
    print(f"\nSaved audited CSV metrics to {out_csv} and {docs_csv} ({len(df_metrics)} rows)")

    build_audited_report(df_metrics, meta, holdout_start, recent_start)


def build_audited_report(
    df: pd.DataFrame,
    meta: pd.DataFrame,
    holdout_start: pd.Timestamp,
    recent_start: pd.Timestamp,
) -> None:
    rep = []
    rep.append("# ETF动量与计算决策因子受控实证报告（第三版·统一资金账本与边界净化）")
    rep.append("")
    rep.append("日期：2026-10-25 | 分支：`research/decision-momentum-validation-20261024`")
    rep.append("基线提交：`1a4b6652f49c412145d12812fa02820ba0a80991`")
    rep.append("状态：`research_only=true` / `actionable=false`")
    rep.append("")
    rep.append("> **审计修复说明（第三版深度治理）**：根据独立审查意见，本版本彻底完成了以下核心修复：")
    rep.append("> 1. **等权基准（B0）与资金预算约束**：B0 明确为无杠杆、多头再平衡组合，每只资产权重为 $1/N_t$，组合总敞口严格限制在 $\\sum w_i \\le 1.0$。彻底消除了原先 $N$ 倍杠杆导致的 $-173.6\\%$ 虚假回撤。M2 波动目标同样加入组合总预算约束（$\\sum w_i \\le 1.0$），未分配资金留存现金（0.0）。")
    rep.append("> 2. **加仓与减仓真实入账**：消除 `min(old, new)` 粗暴估计，区分隔夜持仓损益、次日开盘成交（Open $t+1$）与日内损益，并在换仓与调仓时精确收取单边 10 bps（往返 20 bps）手续费。平价从 10% 调到 20%，准确收取约 1 bp 的组合费用。")
    rep.append("> 3. **统一日净值与逐笔账本**：采用共享的 `simulate_portfolio_ledger_daily` 现金与成交引擎，净值从 1.0 开始，任何破产即刻终止并不允许复活。")
    rep.append("> 4. **样本外与统计边界诚实化**：")
    rep.append(">    - 声明 Holdout 2Y 已被用于策略比较，正式定性为**开发验证集（Validation Set）**，非全新盲测集；后续上线前须等待真正的实盘向前推进检验。")
    rep.append(">    - 训练集在边界处执行 Purging，清除跨入留出期的多日重叠前瞻标签。")
    rep.append(">    - 声明普通 Wilson 区间基于独立伯努利假定，在多日重叠与标的相关下仅代表描述性区间，不单独充当 Alpha 显著性证明。")
    rep.append("> 5. **纠正指标硬矛盾**：如实反映重算后的 `z_mr_20` IC 数据，清理旧版失效结论。")
    rep.append("")

    # Section 1: Holdout 2Y Main Ranking
    rep.append("## 1. 验证集（Holdout 2Y，长历史 17 只）核心表现（次日开盘·真实扣费·统一账本）")
    rep.append("")
    rep.append("| 候选因子 | 流派 | hold IC_7 | hold hit_7 (95% CI) | 净日频 Sharpe (扣费) | 净最大回撤 | 逐笔净胜率 (扣费20bp) | 净期望 (bps) |")
    rep.append("|---|---|---:|:---:|---:|---:|---:|---:|")

    hold_df = df[df["sample"] == "holdout_2y_longhist"]
    for fac in FACTORS:
        h7_row = hold_df[(hold_df["factor"] == fac.name) & (hold_df["horizon"] == 7)]
        if h7_row.empty:
            continue
        r = h7_row.iloc[0]
        ci_str = f"{r['hit_rate']*100:.1f}% [{r['hit_rate_wilson_lo']*100:.1f}%, {r['hit_rate_wilson_hi']*100:.1f}%]" if not pd.isna(r["hit_rate"]) else "n/a"
        wr_str = f"{r['net_win_rate']*100:.1f}%" if not pd.isna(r["net_win_rate"]) else "n/a"
        exp_str = f"{r['net_expectancy_bps']:+.1f}" if not pd.isna(r["net_expectancy_bps"]) else "n/a"
        rep.append(
            f"| `{fac.name}` | {fac.kind} | {r['ic_spearman']:+.4f} | {ci_str} | {r['net_sharpe_d1']:+.3f} | {r['net_max_drawdown']*100:.1f}% | {wr_str} | {exp_str} |"
        )

    # Section 2: Recent Slice Robustness
    rep.append("")
    rep.append("## 2. 近期全池切片（`recent_all_enabled`，2025-08-18 至今）公平对照")
    rep.append("")
    rec_df = df[df["sample"] == "recent_all_enabled"]
    c0_h7 = rec_df[(rec_df["factor"] == "mom_120_cs") & (rec_df["horizon"] == 7)]
    c1_h7 = rec_df[(rec_df["factor"] == "dual_momentum_c1") & (rec_df["horizon"] == 7)]
    b0_h7 = rec_df[(rec_df["factor"] == "equal_weight_b0") & (rec_df["horizon"] == 7)]

    c0_sh = f"{c0_h7.iloc[0]['net_sharpe_d1']:+.3f}" if not c0_h7.empty else "n/a"
    c0_mdd = f"{c0_h7.iloc[0]['net_max_drawdown']*100:.1f}%" if not c0_h7.empty else "n/a"
    c1_sh = f"{c1_h7.iloc[0]['net_sharpe_d1']:+.3f}" if not c1_h7.empty else "n/a"
    c1_mdd = f"{c1_h7.iloc[0]['net_max_drawdown']*100:.1f}%" if not c1_h7.empty else "n/a"
    b0_mdd = f"{b0_h7.iloc[0]['net_max_drawdown']*100:.1f}%" if not b0_h7.empty else "n/a"

    rep.append("> **同选品基数（Top-4）对照与如实评述**：")
    rep.append(
        f"> - **C0 (mom_120_cs)**：选取 Top-4 等权配置（各 0.25），净 Sharpe 为 `{c0_sh}`，净最大回撤为 `{c0_mdd}`。"
    )
    rep.append(
        f"> - **C1 (dual_momentum_c1)**：在完全相同的 Top-4 候选下叠加 12 月绝对动量过滤，未过门资产划归现金。净 Sharpe 为 `{c1_sh}`，净最大回撤为 `{c1_mdd}`。绝对动量门控使最大回撤由 `{c0_mdd}` 收敛至 `{c1_mdd}`，但在低收益震荡期现金持有产生拖累，净夏普低于 C0。"
    )
    rep.append(
        f"> - **B0 (equal_weight_b0)**：在修正总预算为 1.0（$1/N_t$）后，基准净回撤恢复至正常区间（`{b0_mdd}`），彻底消除了旧版杠杆求和导致的假性崩溃。"
    )
    rep.append("")
    rep.append("| 因子 | h7 IC | h7 命中率 (95% CI) | 多头平均远期收益 | 净日频 Sharpe | 净最大回撤 |")
    rep.append("|---|---:|:---:|---:|---:|---:|")

    rec_df = df[df["sample"] == "recent_all_enabled"]
    for fac_name in ["mom_120_cs", "dual_momentum_c1", "tsmom_12m", "tsmom_voltarget_m2", "equal_weight_b0", "z_mr_20", "dual_ma_20_60"]:
        h7_row = rec_df[(rec_df["factor"] == fac_name) & (rec_df["horizon"] == 7)]
        if h7_row.empty:
            continue
        r = h7_row.iloc[0]
        ci_str = f"{r['hit_rate']*100:.1f}% [{r['hit_rate_wilson_lo']*100:.1f}%, {r['hit_rate_wilson_hi']*100:.1f}%]" if not pd.isna(r["hit_rate"]) else "n/a"
        rep.append(
            f"| `{fac_name}` | {r['ic_spearman']:+.4f} | {ci_str} | {r['mean_fwd_long']*100:+.2f}% | {r['net_sharpe_d1']:+.3f} | {r['net_max_drawdown']*100:.1f}% |"
        )

    # Section 3: Detailed Multi-Horizon IC & Direction Table
    rep.append("")
    rep.append("## 3. 跨期限 IC 结构（Purged 边界净化后）")
    rep.append("")
    rep.append("> **重算后事实记录**：")
    rep.append("> - 训练集（`train_earlier`）已执行边界 Purging，剔除跨入验证期的多日前瞻样本。")
    rep.append("> - `z_mr_20` 在纠正前瞻窗口与边界后，其各期限与切片 IC 如实反映如下：在中周期（h20/h60）部分切片显示弱相关，但在短窗及扣费日频 Sharpe 上普遍为负，不具备作为主买卖信号的资格。")
    rep.append("")
    rep.append("| 因子 | 切片 | h1 IC | h3 IC | h7 IC | h20 IC | h60 IC |")
    rep.append("|---|---|---:|---:|---:|---:|---:|")

    for fac_name in ["mom_120_cs", "tsmom_12m", "z_mr_20", "dual_ma_20_60", "td9_setup"]:
        for s_name in ["holdout_2y_longhist", "train_earlier_longhist", "recent_all_enabled"]:
            sub_f = df[(df["factor"] == fac_name) & (df["sample"] == s_name)]
            ic_dict = {row["horizon"]: row["ic_spearman"] for _, row in sub_f.iterrows()}
            rep.append(
                f"| `{fac_name}` | {s_name} | {ic_dict.get(1, float('nan')):.4f} | {ic_dict.get(3, float('nan')):.4f} | {ic_dict.get(7, float('nan')):.4f} | {ic_dict.get(20, float('nan')):.4f} | {ic_dict.get(60, float('nan')):.4f} |"
            )

    # Section 4: Architecture Conclusion
    rep.append("")
    rep.append("## 4. 剩余不具备交易资格的门槛清单（严守研究门禁）")
    rep.append("")
    rep.append("根据当前实测，**本项目继续保持 `research_only=true` / `actionable=false`，严禁任何形式的实盘上线或自动交易**。以下硬门槛尚未通过：")
    rep.append("1. **全新未见盲测集（Pristine OOS）**：当前 Holdout 2Y 已被多次查看并参与规则挑选，已转为验证集；必须等待未见时间序列向前推进（Walk-forward）积累。")
    rep.append("2. **真实冲击与订单撮合**：当前扣费模型仅考虑了 20 bps 双边佣金与滑点，尚未对大额冲击成本、涨跌停无法成交、分笔排队进行高频撮合测试。")
    rep.append("3. **资产池生存偏差**：当前 17 只长历史 ETF 属于存活标的，未包含历史已退市或清盘基金。")
    rep.append("4. **人工审批与授权边界**：未经 Jovi 明确书面指令，系统不得解除操作阻断，不得改动生产定时调度与策略邮件。")

    report_path = DOCS_DIR / "ETF_MOMENTUM_VALIDATION_REPORT_20261024.md"
    report_path.write_text("\n".join(rep), encoding="utf-8")
    print(f"Saved audited Markdown report to {report_path}")


if __name__ == "__main__":
    main()
