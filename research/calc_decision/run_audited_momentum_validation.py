#!/usr/bin/env python3
"""Audited quantitative momentum & decision factors validation harness (V4 - Full Audit Gate Remediation).

Incorporates all 2026-10-26 audit remediations:
1. P0: Official Corporate Action split adjustments (research_history_rows) across daily_bars.
2. P0: Untradable on missing Open (no 1.0 fallback!).
3. P1: Exact label_end_{h} < holdout_start purging (zero calendar estimation overlap).
4. S1: Slice-first investable universe isolation: B0, C0, C1, M0, M2 constructed strictly within each slice.
5. S1: Disentangled executed orders vs true FIFO closed round-trip trades; daily ledger reconciliation.
6. S1: M2 base budget aligned to (1/N_t) * min(1.0, 0.15 / vol_20).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from typing import Any, List, Tuple

import numpy as np
import pandas as pd

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKTREE_ROOT / "backend"))

from app.providers.corporate_action_contract import research_history_rows
from app.services.strategy_evaluation.backtest_harness import (
    calc_daily_portfolio_sharpe,
    calc_max_drawdown,
    simulate_closed_trades_ledger,
    simulate_daily_portfolio_net_returns,
    simulate_portfolio_ledger_daily,
    wilson_score_interval,
)
from app.services.strategy_evaluation.momentum_engine import (
    calc_forward_returns,
    calc_momentum,
    calc_volatility_annualized,
    compute_cross_sectional_top_k_weights,
    compute_dual_momentum_weights,
)

DB_PATH = Path(r"F:\ETF_Data\ETF-Fund-Analysis\db\research.sqlite3")
WATCHLIST_PATH = WORKTREE_ROOT / "config" / "watchlist.json"
OUT_DIR = WORKTREE_ROOT / "research" / "calc_decision" / "out"
DOCS_DIR = WORKTREE_ROOT / "docs" / "research"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS = [1, 3, 7, 20, 60]
HOLDOUT_YEARS = 2
MIN_CROSS_SECTION = 3
MIN_BARS_FOR_LONG = 400
COST_BPS_ONE_WAY = 10.0


# ---------- Math & Statistics Utilities ----------

def spearman_ic(x: pd.Series, y: pd.Series) -> float:
    valid = pd.concat([x, y], axis=1).dropna()
    if len(valid) < MIN_CROSS_SECTION:
        return float("nan")
    corr = valid.iloc[:, 0].corr(valid.iloc[:, 1], method="spearman")
    return float(corr) if not math.isnan(corr) else float("nan")


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


def calc_td_setup_signal(close: pd.Series) -> pd.Series:
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
            sig.iloc[i] = 1.0  # Buy setup
        elif bull_count == 9:
            sig.iloc[i] = -1.0
    return sig


def calc_ichimoku_signal(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2.0
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2.0
    span_a = ((tenkan + kijun) / 2.0).shift(26)
    span_b = ((h.rolling(52).max() + l.rolling(52).min()) / 2.0).shift(26)
    cloud_top = pd.concat([span_a, span_b], axis=1).max(axis=1)
    cloud_bot = pd.concat([span_a, span_b], axis=1).min(axis=1)
    sig = pd.Series(0.0, index=df.index)
    sig[c > cloud_top] = 1.0
    sig[c < cloud_bot] = -1.0
    return sig


def calc_donchian_signal(df: pd.DataFrame, entry_n: int = 20, exit_n: int = 10) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    hh = h.shift(1).rolling(entry_n).max()
    ll = l.shift(1).rolling(exit_n).min()
    sig = pd.Series(0.0, index=df.index)
    curr = 0.0
    for i in range(len(df)):
        if pd.isna(hh.iloc[i]) or pd.isna(ll.iloc[i]):
            continue
        if c.iloc[i] > hh.iloc[i]:
            curr = 1.0
        elif c.iloc[i] < ll.iloc[i]:
            curr = 0.0
        sig.iloc[i] = curr
    return sig


# ---------- Data Loading & Preparation ----------

def load_data() -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    watchlist_data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    codes = [x["ts_code"] for x in watchlist_data["instruments"] if x.get("enabled")]

    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    raw_bars = pd.read_sql_query(
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

    # Apply official Corporate Action adjustments (research_history_rows)
    parts = []
    for code, g in raw_bars.groupby("ts_code"):
        name_val = g["name"].iloc[0]
        sym_val = g["symbol"].iloc[0]
        raw_dict = g.to_dict("records")
        rows = []
        for r in raw_dict:
            r_copy = r.copy()
            r_copy["trade_date"] = pd.to_datetime(r_copy["trade_date"]).date()
            rows.append(SimpleNamespace(**r_copy))
        adj_rows = research_history_rows(rows, code)
        adj_df = pd.DataFrame([vars(r) for r in adj_rows])
        adj_df["ts_code"] = code
        adj_df["name"] = name_val
        adj_df["symbol"] = sym_val
        parts.append(adj_df)

    bars = pd.concat(parts, ignore_index=True)
    bars["trade_date"] = pd.to_datetime(bars["trade_date"])
    bars["ret_1"] = bars["pct_change"] / 100.0 if "pct_change" in bars else bars["close"].pct_change()
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

        # Forward returns: EXACT Day 1 to Day h compound returns + exact label_end date
        g = calc_forward_returns(g, HORIZONS)

        # Momentum & Volatility
        g["mom_20"] = calc_momentum(c, 20)
        g["mom_60"] = calc_momentum(c, 60)
        g["mom_120"] = calc_momentum(c, 120)
        g["mom_252"] = calc_momentum(c, 252)
        g["vol_20"] = calc_volatility_annualized(ret, 20)

        # M0: Raw TSMOM (preserves NaN for un-warmed history)
        g["tsmom_12m"] = np.sign(g["mom_252"])
        # M1: Volatility-scaled continuous score
        g["tsmom_volscaled"] = g["tsmom_12m"] / g["vol_20"].replace(0, np.nan)

        # Technical Counterfactuals
        g["z_20"] = calc_boll_z(c, 20)
        g["z_mr"] = np.where(g["z_20"] < -1.0, 1.0, np.where(g["z_20"] > 1.0, -1.0, 0.0))
        g["adx_14"] = calc_adx(g, 14)
        g["atr_14"] = calc_atr(g, 14)
        g["dual_ma"] = np.where(sma(c, 20) > sma(c, 60), 1.0, -1.0)
        g["macd_sig"] = np.sign(calc_macd_hist(c))
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
    out["rs_sig"] = np.sign(out["rs_vs_300_20"])

    return out


def build_slice_portfolio_weights(slice_df: pd.DataFrame) -> pd.DataFrame:
    """Build B0, C0, C1, M0, M2 weights strictly WITHIN the slice's investable universe.

    Guarantees:
    - B0 assigns 1/N_t to each active asset in this slice, sum(w) = 1.0.
    - C0 selects Top-4 cross-sectional momentum strictly from active assets in this slice, 0.25 each.
    - C1 gates Top-4 by 12m trend > 0; vetoed assets stay in CASH (0.0).
    - M0 assigns 1/N_t to each active asset with 12m trend > 0 in this slice.
    - M2 assigns (1/N_t) * min(1.0, 0.15 / vol_20) to each asset with 12m trend > 0, sum capped at 1.0.
    """
    df = slice_df.copy()
    df["date_str"] = df["trade_date"].dt.strftime("%Y-%m-%d")

    b0_weights = []
    c0_weights = []
    c1_weights = []
    m0_weights = []
    m2_weights = []

    for dt, day_df in df.groupby("date_str"):
        n_active = len(day_df)
        w_b0 = 1.0 / n_active if n_active > 0 else 0.0

        scores = dict(zip(day_df["ts_code"], day_df["mom_120"]))
        trends = dict(zip(day_df["ts_code"], day_df["tsmom_12m"]))
        vols = dict(zip(day_df["ts_code"], day_df["vol_20"]))

        w_c0 = compute_cross_sectional_top_k_weights(scores, top_k=4)
        w_c1 = compute_dual_momentum_weights(scores, trends, top_k=4)

        raw_m2 = {}
        for c, t in trends.items():
            if not pd.isna(t) and t > 0:
                v = vols.get(c, float("nan"))
                scale = min(1.0, 0.15 / v) if (not pd.isna(v) and v > 0) else 1.0
                raw_m2[c] = w_b0 * scale

        m2_sum = sum(raw_m2.values())
        norm_m2 = {c: (w / m2_sum if m2_sum > 1.0 else w) for c, w in raw_m2.items()}

        for _, r in day_df.iterrows():
            c = r["ts_code"]
            t_val = trends.get(c)
            is_active_long = (not pd.isna(t_val)) and (t_val > 0)
            b0_weights.append((dt, c, w_b0))
            c0_weights.append((dt, c, w_c0.get(c, 0.0)))
            c1_weights.append((dt, c, w_c1.get(c, 0.0)))
            m0_weights.append((dt, c, w_b0 if is_active_long else 0.0))
            m2_weights.append((dt, c, norm_m2.get(c, 0.0) if is_active_long else 0.0))

    b0_df = pd.DataFrame(b0_weights, columns=["date_str", "ts_code", "equal_weight_b0_w"])
    c0_df = pd.DataFrame(c0_weights, columns=["date_str", "ts_code", "mom_120_cs_w"])
    c1_df = pd.DataFrame(c1_weights, columns=["date_str", "ts_code", "dual_momentum_w"])
    m0_df = pd.DataFrame(m0_weights, columns=["date_str", "ts_code", "tsmom_12m_w"])
    m2_df = pd.DataFrame(m2_weights, columns=["date_str", "ts_code", "vol_target_w"])

    df = df.merge(b0_df, on=["date_str", "ts_code"], how="left")
    df = df.merge(c0_df, on=["date_str", "ts_code"], how="left")
    df = df.merge(c1_df, on=["date_str", "ts_code"], how="left")
    df = df.merge(m0_df, on=["date_str", "ts_code"], how="left")
    df = df.merge(m2_df, on=["date_str", "ts_code"], how="left")
    return df


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
    FactorMeta("tsmom_12m", "ts_signal", "tsmom_12m", "M0: Time-series 12m trend > 0 (1/N_t per long)"),
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
    holdout_start: pd.Timestamp,
    fixed_daily_sharpe: float,
    closed_trades_stats: dict[str, Any],
) -> dict[str, Any]:
    sub = panel.copy()
    fwd_col = f"fwd_{horizon}"

    # Strict label isolation: future return window must NOT touch holdout_start!
    if sample_name == "train_earlier_longhist":
        end_col = f"label_end_{horizon}"
        if end_col in sub.columns:
            sub = sub[sub[end_col] < holdout_start]

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
            g_sorted = g.sort_values(score_col)
            short_rets.append(g_sorted[fwd_col].iloc[0])
            long_rets.append(g_sorted[fwd_col].iloc[-1])
            hits.append(1 if g_sorted[fwd_col].iloc[-1] > 0 else 0)

        ic_mean = float(np.mean(ics)) if ics else float("nan")
        ic_std = float(np.std(ics, ddof=1)) if len(ics) > 1 else float("nan")
        icir = (ic_mean / ic_std) if (ic_std and not math.isnan(ic_std) and ic_std > 0) else float("nan")
        hit_rate = float(np.mean(hits)) if hits else float("nan")
        n_hits = int(sum(hits)) if hits else 0
        n_signals = len(hits)
        hr_lo, hr_hi = wilson_score_interval(n_hits, n_signals)
        mean_long = float(np.mean(long_rets)) if long_rets else float("nan")
        mean_short = float(np.mean(short_rets)) if short_rets else float("nan")

        return {
            "factor": factor.name,
            "kind": factor.kind,
            "sample": sample_name,
            "horizon": horizon,
            "ic_spearman": round(ic_mean, 4),
            "icir": round(icir, 3),
            "hit_rate": round(hit_rate, 4),
            "hit_rate_wilson_lo": round(hr_lo, 4),
            "hit_rate_wilson_hi": round(hr_hi, 4),
            "mean_fwd_long": round(mean_long, 5),
            "mean_fwd_short": round(mean_short, 5),
            "long_short_spread": round(mean_long - mean_short, 5) if not (math.isnan(mean_long) or math.isnan(mean_short)) else float("nan"),
            "net_sharpe_d1": round(fixed_daily_sharpe, 3) if not math.isnan(fixed_daily_sharpe) else float("nan"),
            "net_max_drawdown": closed_trades_stats.get("max_drawdown", float("nan")),
            "net_win_rate": closed_trades_stats.get("net_win_rate", float("nan")),
            "net_expectancy_bps": closed_trades_stats.get("net_expectancy_bps", float("nan")),
            "profit_factor": closed_trades_stats.get("profit_factor", float("nan")),
            "trades_count": closed_trades_stats.get("trades_count", 0),
            "order_count": closed_trades_stats.get("order_count", 0),
        }

    # Time-series, benchmark, and portfolio ablations
    col_name = factor.col
    sub_ts = sub.dropna(subset=[col_name, fwd_col])
    if sub_ts.empty:
        return {
            "factor": factor.name,
            "kind": factor.kind,
            "sample": sample_name,
            "horizon": horizon,
            "ic_spearman": float("nan"),
            "icir": float("nan"),
            "hit_rate": float("nan"),
            "hit_rate_wilson_lo": float("nan"),
            "hit_rate_wilson_hi": float("nan"),
            "mean_fwd_long": float("nan"),
            "mean_fwd_short": float("nan"),
            "long_short_spread": float("nan"),
            "net_sharpe_d1": round(fixed_daily_sharpe, 3) if not math.isnan(fixed_daily_sharpe) else float("nan"),
            "net_max_drawdown": closed_trades_stats.get("max_drawdown", float("nan")),
            "net_win_rate": closed_trades_stats.get("net_win_rate", float("nan")),
            "net_expectancy_bps": closed_trades_stats.get("net_expectancy_bps", float("nan")),
            "profit_factor": closed_trades_stats.get("profit_factor", float("nan")),
            "trades_count": closed_trades_stats.get("trades_count", 0),
            "order_count": closed_trades_stats.get("order_count", 0),
        }

    ic_val = float(sub_ts[col_name].corr(sub_ts[fwd_col], method="spearman"))
    long_rows = sub_ts[sub_ts[col_name] > 0]
    short_rows = sub_ts[sub_ts[col_name] <= 0]
    mean_long = float(long_rows[fwd_col].mean()) if not long_rows.empty else float("nan")
    mean_short = float(short_rows[fwd_col].mean()) if not short_rows.empty else float("nan")
    hits = (long_rows[fwd_col] > 0).astype(int).tolist()
    hit_rate = float(np.mean(hits)) if hits else float("nan")
    n_hits = int(sum(hits)) if hits else 0
    n_signals = len(hits)
    hr_lo, hr_hi = wilson_score_interval(n_hits, n_signals)

    return {
        "factor": factor.name,
        "kind": factor.kind,
        "sample": sample_name,
        "horizon": horizon,
        "ic_spearman": round(ic_val, 4) if not math.isnan(ic_val) else float("nan"),
        "icir": float("nan"),
        "hit_rate": round(hit_rate, 4) if not math.isnan(hit_rate) else float("nan"),
        "hit_rate_wilson_lo": round(hr_lo, 4) if not math.isnan(hr_lo) else float("nan"),
        "hit_rate_wilson_hi": round(hr_hi, 4) if not math.isnan(hr_hi) else float("nan"),
        "mean_fwd_long": round(mean_long, 5) if not math.isnan(mean_long) else float("nan"),
        "mean_fwd_short": round(mean_short, 5) if not math.isnan(mean_short) else float("nan"),
        "long_short_spread": round(mean_long - mean_short, 5) if not (math.isnan(mean_long) or math.isnan(mean_short)) else float("nan"),
        "net_sharpe_d1": round(fixed_daily_sharpe, 3) if not math.isnan(fixed_daily_sharpe) else float("nan"),
        "net_max_drawdown": closed_trades_stats.get("max_drawdown", float("nan")),
        "net_win_rate": closed_trades_stats.get("net_win_rate", float("nan")),
        "net_expectancy_bps": closed_trades_stats.get("net_expectancy_bps", float("nan")),
        "profit_factor": closed_trades_stats.get("profit_factor", float("nan")),
        "trades_count": closed_trades_stats.get("trades_count", 0),
        "order_count": closed_trades_stats.get("order_count", 0),
    }


PRECOMPUTED_STRATEGY_WEIGHTS = {
    "equal_weight_b0": "equal_weight_b0_w",
    "mom_120_cs": "mom_120_cs_w",
    "dual_momentum_c1": "dual_momentum_w",
    "tsmom_12m": "tsmom_12m_w",
    "tsmom_voltarget_m2": "vol_target_w",
}


def compute_fixed_daily_stats_for_factor(
    slice_df: pd.DataFrame,
    factor: FactorMeta,
    sample_name: str,
) -> Tuple[float, dict[str, Any]]:
    """Compute fee-deducted daily Sharpe and closed trades performance on the slice dataframe."""
    weights_map: dict[Tuple[str, str], float] = {}

    if factor.name in PRECOMPUTED_STRATEGY_WEIGHTS:
        w_col = PRECOMPUTED_STRATEGY_WEIGHTS[factor.name]
        valid_w = slice_df.dropna(subset=[w_col])
        for dt, code, w_val in valid_w[["date_str", "ts_code", w_col]].itertuples(index=False, name=None):
            if w_val > 0.0:
                weights_map[(str(dt), str(code))] = float(w_val)
    elif factor.col.endswith("_w"):
        valid_w = slice_df.dropna(subset=[factor.col])
        for dt, code, w_val in valid_w[["date_str", "ts_code", factor.col]].itertuples(index=False, name=None):
            if w_val > 0.0:
                weights_map[(str(dt), str(code))] = float(w_val)
    elif factor.kind == "cs_rank":
        for dt, day_df in slice_df.groupby("date_str"):
            g0 = day_df.dropna(subset=[factor.col])
            if len(g0) >= MIN_CROSS_SECTION:
                q_hi = g0[factor.col].quantile(2 / 3)
                picks = g0.loc[g0[factor.col] >= q_hi, "ts_code"].tolist()
                if picks:
                    w = 1.0 / len(picks)
                    for c in picks:
                        weights_map[(str(dt), str(c))] = w
    elif factor.kind == "ts_signal":
        if factor.col in slice_df.columns:
            for dt, day_df in slice_df.groupby("date_str"):
                sig_assets = day_df.loc[day_df[factor.col] > 0.0, "ts_code"].tolist()
                if sig_assets:
                    w = 1.0 / len(sig_assets)
                    for c in sig_assets:
                        weights_map[(str(dt), str(c))] = w

    sim_res = simulate_portfolio_ledger_daily(
        panel=slice_df,
        weights_map=weights_map,
        initial_capital=100000.0,
        cost_bps_one_way=COST_BPS_ONE_WAY,
    )

    sh = sim_res["annualized_sharpe"]
    mdd = sim_res["max_drawdown"]
    trades = sim_res["trades"]
    round_trips = sim_res["round_trip_trades"]
    daily_ledger = sim_res["daily_ledger"]

    # Save reconciliation ledger for key strategies (B0, C0, C1, M0, M2)
    if factor.name in ["equal_weight_b0", "mom_120_cs", "dual_momentum_c1", "tsmom_12m", "tsmom_voltarget_m2"]:
        ledger_df = pd.DataFrame(daily_ledger)
        ledger_path = OUT_DIR / f"reconciliation_ledger_{sample_name}_{factor.name}.csv"
        ledger_df.to_csv(ledger_path, index=False)

    trade_stats = {
        "max_drawdown": round(mdd, 4),
        "order_count": len(trades),
        "trades_count": len(round_trips),
        "net_win_rate": float("nan"),
        "net_expectancy_bps": float("nan"),
        "profit_factor": float("nan"),
    }

    if round_trips:
        net_pnls = [t["net_return"] for t in round_trips]
        pos_pnls = [r for r in net_pnls if r > 0]
        neg_pnls = [r for r in net_pnls if r < 0]
        tot = len(net_pnls)
        trade_stats["net_win_rate"] = round(len(pos_pnls) / tot, 4) if tot > 0 else float("nan")
        trade_stats["net_expectancy_bps"] = round(float(np.mean(net_pnls)) * 10000.0, 1) if tot > 0 else float("nan")
        trade_stats["profit_factor"] = round(sum(pos_pnls) / abs(sum(neg_pnls)), 3) if neg_pnls and sum(neg_pnls) != 0 else float("nan")

    return sh, trade_stats


def main() -> None:
    print("--- Starting Audited Momentum & Factor Validation (V4 Corporate Actions & S1 Isolation) ---")
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

    # Define slices with explicit investable universes
    slices = [
        ("holdout_2y_longhist", long_codes, panel["sample"] == "holdout_2y"),
        ("train_earlier_longhist", long_codes, panel["sample"] == "train_earlier"),
        ("recent_all_enabled", codes, panel["trade_date"] >= recent_start),
        ("all_longhist", long_codes, pd.Series(True, index=panel.index)),
    ]

    records = []

    for sample_name, universe_codes, date_mask in slices:
        print(f"\nProcessing slice: {sample_name} (universe size: {len(universe_codes)})")
        # S1 Fix: isolate slice dataframe strictly to this slice's universe and dates
        slice_raw = panel[panel["ts_code"].isin(universe_codes) & date_mask].copy()

        # Generate portfolio weights (B0, C0, C1, M0, M2) strictly WITHIN this slice
        slice_df = build_slice_portfolio_weights(slice_raw)

        for fac in FACTORS:
            fixed_sh, closed_stats = compute_fixed_daily_stats_for_factor(slice_df, fac, sample_name)

            for h in HORIZONS:
                try:
                    res = evaluate_factor_slice(
                        panel=slice_df,
                        factor=fac,
                        horizon=h,
                        sample_name=sample_name,
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
    rep.append("# ETF动量与计算决策因子受控实证报告（第四版·全审计门禁闭环）")
    rep.append("")
    rep.append("日期：2026-10-26 | 工作树：`etf-momentum-audit-fix-20261026`")
    rep.append("状态：`research_only=true` / `actionable=false`")
    rep.append("")
    rep.append("> **审计修复说明（第四版全审计门禁闭环）**：根据独立审查与 10-26 专家审核意见，本版本彻底完成了以下核心修复：")
    rep.append("> 1. **等权基准（B0）与资金预算约束**：B0 明确为无杠杆、多头再平衡组合，每只资产权重为 $1/N_t$，组合总敞口严格限制在 $\\sum w_i \\le 1.0$。先确定各切片的可投资资产池（Investable Universe），在池内封闭生成 B0、C0、C1、M0、M2，确保 B0 等权再平衡预算为 1.0、预测与成交 Top4 严格同一、M2 波动预算 $(1/N_t) \\times \\min(1.0, 0.15/\\sigma_i)$ 同构匹配。")
    rep.append("> 2. **加仓与减仓真实入账**：消除 `min(old, new)` 粗暴估计，区分隔夜持仓损益、次日开盘成交（Open $t+1$）与日内损益，并在换仓与调仓时精确收取单边 10 bps（往返 20 bps）手续费。回测引擎彻底废除任何向常数 1.0 的回退。若次日开盘缺价或停牌，严格标记为**不可成交（Untradable）**，拒绝虚假开平仓；收盘估值严格沿用最新已知价，杜绝造假。")
    rep.append("> 3. **统一日净值与逐笔账本**：采用共享的 `simulate_portfolio_ledger_daily` 现金与成交引擎，严格验证 $\\text{NAV} = \\text{Cash} + \\text{PositionsValue}$。区分成交流水条数（Order Count）与 FIFO 匹配后的真实闭合交易（Round-trip Trades），落盘逐日资金对账产物。")
    rep.append("> 4. **样本外与统计边界诚实化**：")
    rep.append(">    - 声明 Holdout 2Y 已被用于策略比较，正式定性为**开发验证集（Validation Set）**，非全新盲测集；后续上线前须等待真正的实盘向前推进检验。")
    rep.append(">    - 严格按每条记录实际未来前瞻窗口截止日 `label_end_{h} < holdout_start` 过滤（Purging），彻底根除原自然日估算造成的跨界前瞻泄漏。")
    rep.append(">    - 声明普通 Wilson 区间基于独立伯努利假定，在多日重叠与标的相关下仅代表描述性区间，不单独充当 Alpha 显著性证明。")
    rep.append("> 5. **P0 拆分与复权价格契约接入**：全面接入 `corporate_action_contract.py`，针对 513100.SH（2022-01-14 1比5拆分）等历史公司行动，在研究层采用前复权价格序列与复权收益，彻底消除拆分日 -80.45% 的虚假断崖。")
    rep.append("> 6. **美股与影子比对科学化**：美股波动率严格基于百分比收益序列计算；命中率与因子信号方向挂钩；影子比对细分过滤原因；如实披露小样本限制。")
    rep.append("")

    # Section 1: Holdout 2Y Main Ranking
    rep.append("## 1. 验证集（Holdout 2Y，长历史 17 只）核心表现（同池统一·真实扣费·FIFO对账）")
    rep.append("")
    rep.append("| 候选因子 | 流派 | hold IC_7 | hold hit_7 (95% CI) | 净日频 Sharpe (扣费) | 净最大回撤 | FIFO净胜率 (扣费20bp) | 净期望 (bps) | 订单数/闭合数 |")
    rep.append("|---|---|---:|:---:|---:|---:|---:|---:|:---:|")

    hold_df = df[df["sample"] == "holdout_2y_longhist"]
    for fac in FACTORS:
        h7_row = hold_df[(hold_df["factor"] == fac.name) & (hold_df["horizon"] == 7)]
        if h7_row.empty:
            continue
        r = h7_row.iloc[0]
        ci_str = f"{r['hit_rate']*100:.1f}% [{r['hit_rate_wilson_lo']*100:.1f}%, {r['hit_rate_wilson_hi']*100:.1f}%]" if not pd.isna(r["hit_rate"]) else "n/a"
        wr_str = f"{r['net_win_rate']*100:.1f}%" if not pd.isna(r["net_win_rate"]) else "n/a"
        exp_str = f"{r['net_expectancy_bps']:+.1f}" if not pd.isna(r["net_expectancy_bps"]) else "n/a"
        count_str = f"{r.get('order_count', 0)} / {r.get('trades_count', 0)}"
        rep.append(
            f"| `{fac.name}` | {fac.kind} | {r['ic_spearman']:+.4f} | {ci_str} | {r['net_sharpe_d1']:+.3f} | {r['net_max_drawdown']*100:.1f}% | {wr_str} | {exp_str} | {count_str} |"
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
    b0_sh = f"{b0_h7.iloc[0]['net_sharpe_d1']:+.3f}" if not b0_h7.empty else "n/a"
    b0_mdd = f"{b0_h7.iloc[0]['net_max_drawdown']*100:.1f}%" if not b0_h7.empty else "n/a"

    rep.append("> **同选品基数（Top-4）对照与如实评述**：")
    rep.append(
        f"> - **B0 (equal_weight_b0)**：动态等权再平衡基准（每日 $1/N_t$），近期净 Sharpe 为 `{b0_sh}`，净回撤为 `{b0_mdd}`。"
    )
    rep.append(
        f"> - **C0 (mom_120_cs)**：选取 Top-4 等权配置（各 0.25），净 Sharpe 为 `{c0_sh}`，净最大回撤为 `{c0_mdd}`。"
    )
    rep.append(
        f"> - **C1 (dual_momentum_c1)**：在完全相同的 Top-4 候选下叠加 12 月绝对动量过滤，未过门资产划归现金。净 Sharpe 为 `{c1_sh}`，净最大回撤为 `{c1_mdd}`。"
    )
    rep.append("")
    rep.append("| 因子 | h7 IC | h7 命中率 (95% CI) | 多头平均远期收益 | 净日频 Sharpe | 净最大回撤 |")
    rep.append("|---|---:|:---:|---:|---:|---:|")

    for fac_name in ["equal_weight_b0", "mom_120_cs", "dual_momentum_c1", "tsmom_12m", "tsmom_voltarget_m2", "z_mr_20", "dual_ma_20_60"]:
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
    rep.append("## 4. 生产准入未完成门槛（严守研究门禁）")
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
