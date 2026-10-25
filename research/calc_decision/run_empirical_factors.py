#!/usr/bin/env python3
"""Offline empirical factor evaluation on local China ETF daily_bars.

Read-only against research.sqlite3. Writes metrics CSV + markdown under
research/calc_decision/out/ and docs/.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(r"E:\worktrees\etf-calc-decision-20261024")
DB = Path(r"F:\ETF_Data\ETF-Fund-Analysis\db\research.sqlite3")
WATCHLIST = ROOT / "config" / "watchlist.json"
OUT = ROOT / "research" / "calc_decision" / "out"
OUT.mkdir(parents=True, exist_ok=True)

HORIZONS = [1, 3, 7, 20, 60]
COST_BPS = 10  # one-way approx for ETF round-trip commentary (buy+sell ~20bps)
HOLDOUT_YEARS = 2
MIN_BARS_FOR_LONG = 400  # prefer longer history for primary panel
MIN_CROSS_SECTION = 8

# ---------- helpers ----------

def spearman_ic(x: pd.Series, y: pd.Series) -> float:
    df = pd.concat([x, y], axis=1).dropna()
    if len(df) < 5:
        return float("nan")
    return float(df.iloc[:, 0].rank().corr(df.iloc[:, 1].rank()))


def hit_rate(signal: pd.Series, fwd: pd.Series) -> Tuple[float, int]:
    s = pd.concat([signal, fwd], axis=1).dropna()
    s.columns = ["sig", "fwd"]
    s = s[s["sig"] != 0]
    if len(s) == 0:
        return float("nan"), 0
    hits = ((s["sig"] > 0) & (s["fwd"] > 0)) | ((s["sig"] < 0) & (s["fwd"] < 0))
    return float(hits.mean()), int(len(s))


def mean_when(signal: pd.Series, fwd: pd.Series, positive: bool) -> Tuple[float, int]:
    s = pd.concat([signal, fwd], axis=1).dropna()
    s.columns = ["sig", "fwd"]
    mask = s["sig"] > 0 if positive else s["sig"] < 0
    sub = s.loc[mask, "fwd"]
    if len(sub) == 0:
        return float("nan"), 0
    return float(sub.mean()), int(len(sub))


def ann_sharpe(daily_rets: pd.Series) -> float:
    r = daily_rets.dropna()
    if len(r) < 20 or r.std() == 0:
        return float("nan")
    return float(np.sqrt(252) * r.mean() / r.std())


# ---------- indicators ----------

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    up = h.diff()
    down = -l.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([(h - l), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr_n = pd.Series(tr, index=df.index).rolling(n, min_periods=n).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(n, min_periods=n).mean() / atr_n
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(n, min_periods=n).mean() / atr_n
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan)
    return dx.rolling(n, min_periods=n).mean()


def macd_hist(close: pd.Series) -> pd.Series:
    return ema(close, 12) - ema(close, 26) - ema(ema(close, 12) - ema(close, 26), 9)


def boll_z(close: pd.Series, n: int = 20) -> pd.Series:
    m = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std()
    return (close - m) / sd.replace(0, np.nan)


def donchian_signal(df: pd.DataFrame, entry: int = 20, exit_: int = 10) -> pd.Series:
    """+1 on breakout above N-day high (excl today), -1 below exit low; else carry/0."""
    hh = df["high"].shift(1).rolling(entry, min_periods=entry).max()
    ll_exit = df["low"].shift(1).rolling(exit_, min_periods=exit_).min()
    sig = pd.Series(0.0, index=df.index)
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


def td_setup_signal(close: pd.Series) -> pd.Series:
    """Simplified DeMark Setup: buy exhaustion after 9 downs, sell after 9 ups.
    Signal at completion bar: +1 after TD buy setup 9, -1 after TD sell setup 9.
    """
    cmp = close > close.shift(4)
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
                s = 1.0  # buy setup complete -> expect bounce
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


def ichimoku_signal(df: pd.DataFrame) -> pd.Series:
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


# ---------- load ----------

def load_watchlist() -> List[str]:
    data = json.loads(WATCHLIST.read_text(encoding="utf-8"))
    return [x["ts_code"] for x in data["instruments"] if x.get("enabled")]


def load_panel(codes: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    inst = pd.read_sql_query(
        "SELECT id, ts_code, symbol, name, enabled FROM instruments", con
    )
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
    # Prefer exchange pct_change when present; else close/pre_close-1
    bars["ret_1"] = bars["pct_change"] / 100.0
    missing = bars["ret_1"].isna()
    bars.loc[missing, "ret_1"] = bars.loc[missing, "close"] / bars.loc[missing, "pre_close"] - 1.0
    # still NaN -> close pct
    still = bars["ret_1"].isna()
    bars.loc[still, "ret_1"] = bars.groupby("ts_code")["close"].pct_change()
    meta = (
        bars.groupby("ts_code")
        .agg(n=("trade_date", "count"), start=("trade_date", "min"), end=("trade_date", "max"), name=("name", "first"))
        .reset_index()
    )
    return bars, meta


def add_forwards(g: pd.DataFrame) -> pd.DataFrame:
    g = g.sort_values("trade_date").copy()
    for h in HORIZONS:
        # compound forward return using ret_1
        r = g["ret_1"].fillna(0.0)
        # sum log approx for speed/stability
        log1p = np.log1p(r.clip(lower=-0.99))
        fwd = log1p[::-1].rolling(h, min_periods=h).sum()[::-1].shift(-h)
        g[f"fwd_{h}"] = np.expm1(fwd)
    return g


def compute_per_asset_factors(g: pd.DataFrame, bench_close: Optional[pd.Series]) -> pd.DataFrame:
    g = g.sort_values("trade_date").copy()
    c = g["close"]
    g["mom_20"] = c / c.shift(20) - 1
    g["mom_60"] = c / c.shift(60) - 1
    g["mom_120"] = c / c.shift(120) - 1
    # TSMOM 12m ~ 252d sign, vol scale 20d
    ret = g["ret_1"]
    g["vol_20"] = ret.rolling(20, min_periods=20).std() * np.sqrt(252)
    g["tsmom_12m"] = np.sign(c / c.shift(252) - 1.0)
    g["tsmom_volscaled"] = g["tsmom_12m"] / g["vol_20"].replace(0, np.nan)
    # relative strength vs 510300
    if bench_close is not None:
        b = bench_close.reindex(g["trade_date"].values)
        # align by date via merge later — here store date-indexed bench ret ratio
        pass
    g["z_20"] = boll_z(c, 20)
    g["adx_14"] = adx(g, 14)
    g["atr_14"] = atr(g, 14)
    g["atr_pct"] = g["atr_14"] / c
    g["dual_ma"] = np.where(sma(c, 20) > sma(c, 60), 1.0, -1.0)
    g["macd_hist"] = macd_hist(c)
    g["macd_sig"] = np.sign(g["macd_hist"])
    g["td9"] = td_setup_signal(c)
    g["ichi"] = ichimoku_signal(g)
    g["turtle"] = donchian_signal(g, 20, 10)
    # ATR risk filter: allow long only if atr_pct below rolling median*1.5 (not extreme)
    med = g["atr_pct"].rolling(60, min_periods=20).median()
    g["atr_ok"] = (g["atr_pct"] <= 1.5 * med).astype(float)
    # ADX gate trend follow: dual_ma only when ADX>25 else 0
    g["adx_trend"] = np.where(g["adx_14"] > 25, g["dual_ma"], 0.0)
    # mean reversion: long when z<-1, short when z>1
    g["z_mr"] = np.where(g["z_20"] < -1.0, 1.0, np.where(g["z_20"] > 1.0, -1.0, 0.0))
    # TSMOM sign as trade signal
    g["tsmom_sig"] = g["tsmom_12m"].fillna(0.0)
    return g


def attach_rs(panel: pd.DataFrame, bench_code: str = "510300.SH") -> pd.DataFrame:
    bench = panel.loc[panel["ts_code"] == bench_code, ["trade_date", "close"]].rename(columns={"close": "bench_close"})
    out = panel.merge(bench, on="trade_date", how="left")
    # RS = asset 20d mom minus bench 20d mom
    out = out.sort_values(["ts_code", "trade_date"])
    out["bench_mom_20"] = out.groupby("ts_code")["bench_close"].transform(lambda s: s / s.shift(20) - 1)
    # actually bench_close is same series repeated — ok
    out["rs_vs_300_20"] = out["mom_20"] - out["bench_mom_20"]
    out["rs_sig"] = np.sign(out["rs_vs_300_20"])
    return out


@dataclass
class FactorSpec:
    name: str
    kind: str  # ts_signal | cs_rank | continuous
    col: str
    rule: str


FACTORS = [
    FactorSpec("mom_20_cs", "cs_rank", "mom_20", "Cross-sectional: long top tercile mom_20, short bottom"),
    FactorSpec("mom_60_cs", "cs_rank", "mom_60", "Cross-sectional: long top tercile mom_60, short bottom"),
    FactorSpec("mom_120_cs", "cs_rank", "mom_120", "Cross-sectional: long top tercile mom_120, short bottom"),
    FactorSpec("tsmom_12m", "ts_signal", "tsmom_sig", "Long if 12m return >0 else flat/short"),
    FactorSpec("tsmom_volscaled", "continuous", "tsmom_volscaled", "12m sign / 20d ann vol as continuous score"),
    FactorSpec("rs_vs_300_20", "ts_signal", "rs_sig", "Long if 20d RS vs 510300 >0"),
    FactorSpec("z_mr_20", "ts_signal", "z_mr", "Long z<-1, short z>1"),
    FactorSpec("adx_trend", "ts_signal", "adx_trend", "Dual MA only when ADX>25"),
    FactorSpec("dual_ma_20_60", "ts_signal", "dual_ma", "SMA20>SMA60 long else short"),
    FactorSpec("macd", "ts_signal", "macd_sig", "MACD hist sign"),
    FactorSpec("td9_setup", "ts_signal", "td9", "TD Setup 9 completion (pulse)"),
    FactorSpec("ichimoku_cloud", "ts_signal", "ichi", "Above cloud long / below short"),
    FactorSpec("turtle_20_10", "ts_signal", "turtle", "Donchian 20 entry / 10 exit long-flat"),
    FactorSpec("atr_gate_dual_ma", "ts_signal", "dual_ma", "Dual MA filtered by atr_ok (evaluated separately)"),
]


def evaluate_ts(panel: pd.DataFrame, factor: FactorSpec, horizon: int, mask: pd.Series) -> dict:
    sig_col = factor.col
    fwd = f"fwd_{horizon}"
    sub = panel.loc[mask].copy()
    if factor.name == "atr_gate_dual_ma":
        sig = sub["dual_ma"].where(sub["atr_ok"] > 0, 0.0)
    else:
        sig = sub[sig_col]
    # pool all asset-days
    hr, n = hit_rate(sig, sub[fwd])
    mlong, nlong = mean_when(sig, sub[fwd], True)
    mshort, nshort = mean_when(sig, sub[fwd], False)
    # long-flat daily portfolio: equal-weight across assets with sig>0 that day
    tmp = sub[["trade_date", "ts_code"]].copy()
    tmp["sig"] = sig.values
    tmp["fwd"] = sub[fwd].values
    # approximate holding return as fwd/horizon per day contribution is messy;
    # instead build daily long-flat using next-day ret when signal>0
    daily = sub[["trade_date", "ts_code", "ret_1"]].copy()
    daily["sig"] = sig.values
    # signal at t, earn ret at t+1
    daily["pos"] = daily.groupby("ts_code")["sig"].shift(1)
    daily["pnl"] = np.where(daily["pos"] > 0, daily["ret_1"], 0.0)
    port = daily.groupby("trade_date")["pnl"].mean()
    sh = ann_sharpe(port)
    # IC for continuous / raw col vs fwd (time-series pooled Spearman is weak; still report)
    ic = spearman_ic(sub[sig_col] if factor.name != "atr_gate_dual_ma" else sig, sub[fwd])
    return {
        "factor": factor.name,
        "horizon": horizon,
        "kind": factor.kind,
        "hit_rate": hr,
        "n_signals": n,
        "mean_fwd_long": mlong,
        "n_long": nlong,
        "mean_fwd_short": mshort,
        "n_short": nshort,
        "ic_spearman": ic,
        "sharpe_longflat_d1": sh,
        "rule": factor.rule,
    }


def evaluate_cs(panel: pd.DataFrame, factor: FactorSpec, horizon: int, mask: pd.Series) -> dict:
    fwd = f"fwd_{horizon}"
    sub = panel.loc[mask, ["trade_date", "ts_code", factor.col, fwd, "ret_1"]].dropna(subset=[factor.col, fwd])
    # daily cross-section IC
    ics = []
    long_rets = []
    short_rets = []
    hits = []
    n_days = 0
    port_daily = []
    for dt, g in sub.groupby("trade_date"):
        if len(g) < MIN_CROSS_SECTION:
            continue
        n_days += 1
        ic = spearman_ic(g[factor.col], g[fwd])
        if not math.isnan(ic):
            ics.append(ic)
        q_hi = g[factor.col].quantile(2 / 3)
        q_lo = g[factor.col].quantile(1 / 3)
        long = g[g[factor.col] >= q_hi]
        short = g[g[factor.col] <= q_lo]
        if len(long):
            long_rets.append(long[fwd].mean())
            # hit: forward positive
            hits.extend((long[fwd] > 0).astype(float).tolist())
        if len(short):
            short_rets.append(short[fwd].mean())
        # next-day long-flat portfolio from today's ranking — use ret_1 shifted externally hard;
        # approximate: earn equal-weight long basket next day ret via merge on date+1 later
        port_daily.append((dt, long["ts_code"].tolist()))

    # build sharpe of daily long-flat using next day's ret_1
    # map date -> long names
    date_longs = {d: set(codes) for d, codes in port_daily}
    dates = sorted(date_longs)
    # index ret
    piv = panel.pivot_table(index="trade_date", columns="ts_code", values="ret_1")
    pnls = []
    for i in range(len(dates) - 1):
        d0, d1 = dates[i], dates[i + 1]
        codes = date_longs[d0]
        # if calendar gap, still use next available date in piv
        if d1 not in piv.index:
            continue
        vals = [piv.loc[d1, c] for c in codes if c in piv.columns and pd.notna(piv.loc[d1, c])]
        if vals:
            pnls.append(np.mean(vals))
    sh = ann_sharpe(pd.Series(pnls))

    return {
        "factor": factor.name,
        "horizon": horizon,
        "kind": factor.kind,
        "hit_rate": float(np.mean(hits)) if hits else float("nan"),
        "n_signals": int(len(hits)),
        "mean_fwd_long": float(np.mean(long_rets)) if long_rets else float("nan"),
        "n_long": int(len(long_rets)),
        "mean_fwd_short": float(np.mean(short_rets)) if short_rets else float("nan"),
        "n_short": int(len(short_rets)),
        "ic_spearman": float(np.mean(ics)) if ics else float("nan"),
        "ic_days": n_days,
        "sharpe_longflat_d1": sh,
        "rule": factor.rule,
    }


def main():
    codes = load_watchlist()
    print("watchlist enabled", len(codes))
    bars, meta = load_panel(codes)
    meta.to_csv(OUT / "data_coverage_by_etf.csv", index=False)
    print(meta.sort_values("n", ascending=False).to_string(index=False))

    # Primary panel: ETFs with enough history OR all enabled for short-sample note
    long_codes = meta.loc[meta["n"] >= MIN_BARS_FOR_LONG, "ts_code"].tolist()
    if "510300.SH" not in long_codes:
        long_codes.append("510300.SH")
    print("long-history panel", len(long_codes))

    panel = bars[bars["ts_code"].isin(set(codes))].copy()
    parts = []
    for code, g in panel.groupby("ts_code", sort=False):
        g2 = add_forwards(g)
        g2 = compute_per_asset_factors(g2, None)
        parts.append(g2)
    panel = pd.concat(parts, ignore_index=True)
    panel = attach_rs(panel)

    # sample splits
    max_dt = panel["trade_date"].max()
    holdout_start = max_dt - pd.DateOffset(years=HOLDOUT_YEARS)
    panel["sample"] = np.where(panel["trade_date"] >= holdout_start, "holdout_2y", "train_earlier")

    # also short-history recent panel (all enabled overlapping from 2025-08)
    recent_start = pd.Timestamp("2025-08-18")

    rows = []
    for sample_name, mask in [
        ("all_longhist", (panel["ts_code"].isin(long_codes))),
        ("train_earlier_longhist", (panel["ts_code"].isin(long_codes)) & (panel["sample"] == "train_earlier")),
        ("holdout_2y_longhist", (panel["ts_code"].isin(long_codes)) & (panel["sample"] == "holdout_2y")),
        ("recent_all_enabled", panel["trade_date"] >= recent_start),
    ]:
        for fac in FACTORS:
            for h in HORIZONS:
                try:
                    if fac.kind == "cs_rank":
                        res = evaluate_cs(panel, fac, h, mask)
                    else:
                        res = evaluate_ts(panel, fac, h, mask)
                    res["sample"] = sample_name
                    rows.append(res)
                    print(sample_name, fac.name, h, "hit", res.get("hit_rate"), "ic", res.get("ic_spearman"), "sh", res.get("sharpe_longflat_d1"))
                except Exception as e:
                    print("ERR", sample_name, fac.name, h, e)

    metrics = pd.DataFrame(rows)
    metrics_path = OUT / "factor_empirical_metrics_20261024.csv"
    metrics.to_csv(metrics_path, index=False)

    # also copy paths expected by parent
    docs_csv = ROOT / "docs" / "factor_empirical_metrics_20261024.csv"
    metrics.to_csv(docs_csv, index=False)

    # coverage summary json
    cov = {
        "db_path": str(DB),
        "db_mtime": str(DB.stat().st_mtime),
        "watchlist_n": len(codes),
        "bars_n": int(len(bars)),
        "date_min": str(bars["trade_date"].min().date()),
        "date_max": str(bars["trade_date"].max().date()),
        "sources": bars["source"].value_counts().to_dict(),
        "adjust": bars["adjust"].value_counts().to_dict(),
        "long_history_codes": long_codes,
        "long_history_n": len(long_codes),
        "share_scales_rows": 0,
        "premium_iopv_historical": False,
        "us_native_etf_bars": False,
        "us_proxy_in_watchlist": ["513100.SH", "513500.SH"],
        "holdout_start": str(holdout_start.date()),
        "cost_assumption_bps_one_way": COST_BPS,
    }
    (OUT / "data_inventory_20261024.json").write_text(json.dumps(cov, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", metrics_path, "rows", len(metrics))


if __name__ == "__main__":
    main()
