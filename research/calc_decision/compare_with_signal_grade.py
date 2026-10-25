#!/usr/bin/env python3
"""Offline shadow comparison between Dual Momentum (C1) and existing SignalGradeService (A3.3 gate).

Evaluates historical concordance, false-alarm reduction, and forward return distributions
across the five action grades ('可加仓', '可入场', '可试探', '观望', '减仓') vs C1 Dual Momentum.
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

from app.services.signal_grade_service import SignalGradeService, classify_row
from app.services.strategy_evaluation.momentum_engine import (
    calc_cross_sectional_ranks,
    calc_forward_returns,
    calc_momentum,
    calc_volatility_annualized,
    compute_cross_sectional_top_k_weights,
)
from app.utils.indicators import calculate_indicators

DB_PATH = Path(r"F:\ETF_Data\ETF-Fund-Analysis\db\research.sqlite3")
OUT_DIR = WORKTREE_ROOT / "research" / "calc_decision" / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)


WATCHLIST_PATH = WORKTREE_ROOT / "config" / "watchlist.json"


def load_long_history_panel() -> pd.DataFrame:
    if WATCHLIST_PATH.exists():
        watchlist_data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
        codes = [x["ts_code"] for x in watchlist_data["instruments"] if x.get("enabled")]
    else:
        codes = []

    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        where_clause = f"WHERE i.ts_code IN ({','.join('?' * len(codes))})" if codes else ""
        df = pd.read_sql_query(
            f"""
            SELECT i.ts_code, i.name, d.trade_date, d.open, d.high, d.low, d.close, d.volume
            FROM daily_bars d
            JOIN instruments i ON i.id = d.instrument_id
            {where_clause}
            ORDER BY i.ts_code, d.trade_date ASC
            """,
            conn,
            params=codes if codes else None,
        )
    finally:
        conn.close()

    df["trade_date"] = pd.to_datetime(df["trade_date"])
    # Filter to long-history 17 assets (>=400 bars)
    counts = df.groupby("ts_code")["trade_date"].count()
    long_codes = set(counts[counts >= 400].index)
    if "510300.SH" not in long_codes:
        long_codes.add("510300.SH")

    sub = df[df["ts_code"].isin(long_codes)].copy()
    return sub.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def compute_panel_with_signals_and_grades(panel: pd.DataFrame) -> pd.DataFrame:
    """Compute indicators, SignalGrade five-level actions, and C0/C1 momentum weights."""
    grade_service = SignalGradeService()
    cfg = grade_service.config
    ind_cfg = {
        "ma_windows": [5, 10, 20, 30, 60],
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "kdj": {"n": 9, "m1": 3, "m2": 3},
        "rsi": {"window": 14},
        "volume": {"volume_expand": 1.35, "volume_contract": 0.85},
    }

    asset_dfs = []
    for code, g in panel.groupby("ts_code"):
        g_sorted = g.sort_values("trade_date").reset_index(drop=True)
        # Compute forward returns
        g_fwd = calc_forward_returns(g_sorted, horizons=[1, 3, 7, 20, 60])
        # Compute momentum features
        g_fwd["mom_120"] = calc_momentum(g_fwd["close"], 120)
        g_fwd["mom_252"] = calc_momentum(g_fwd["close"], 252)
        g_fwd["tsmom_state"] = np.where(g_fwd["mom_252"] > 0, 1.0, 0.0)

        # Compute technical indicators for SignalGradeService
        try:
            ind_res = calculate_indicators(g_fwd, ind_cfg)
            ind_frame = ind_res.frame
        except Exception:
            ind_frame = g_fwd.copy()

        grades = []
        n_rows = len(ind_frame)
        for i in range(n_rows):
            if i < 30:
                grades.append("数据不足")
                continue
            row_dict = ind_frame.iloc[i].to_dict()
            prev_dict = ind_frame.iloc[i - 1].to_dict() if i > 0 else None
            c_curr = float(ind_frame["close"].iloc[i])
            c_prev = float(ind_frame["close"].iloc[i - 1]) if i > 0 else c_curr
            pct_chg = (c_curr / c_prev - 1.0) if c_prev > 0 else 0.0

            res = classify_row(row_dict, pct_change=pct_chg, previous=prev_dict, cfg=cfg)
            grades.append(res.get("grade", "观望"))

        g_fwd["signal_grade"] = grades
        asset_dfs.append(g_fwd)

    full = pd.concat(asset_dfs, ignore_index=True)
    full["date_str"] = full["trade_date"].dt.strftime("%Y-%m-%d")

    # Cross-sectional momentum Top-4 (C0) and Dual Momentum (C1)
    full["c0_weight"] = 0.0
    full["c1_weight"] = 0.0

    for dt, day_df in full.groupby("date_str"):
        scores = dict(zip(day_df["ts_code"], day_df["mom_120"]))
        top4_weights = compute_cross_sectional_top_k_weights(scores, top_k=4)
        for idx, row in day_df.iterrows():
            code = row["ts_code"]
            w0 = top4_weights.get(code, 0.0)
            full.at[idx, "c0_weight"] = w0
            # C1 adds 12-month trend filter: tsmom_state > 0
            if w0 > 0.0 and row["tsmom_state"] > 0.0:
                full.at[idx, "c1_weight"] = w0

    return full


def analyze_shadow_comparison(df: pd.DataFrame) -> dict[str, Any]:
    valid_df = df[df["signal_grade"].isin(["可加仓", "可入场", "可试探", "观望", "减仓"])].copy()

    total_samples = len(valid_df)

    # 1. Overall Grade Distribution
    grade_counts = valid_df["signal_grade"].value_counts().to_dict()
    grade_pcts = {k: round(v / total_samples * 100, 2) for k, v in grade_counts.items()}

    # 2. Concordance Matrix: C1 vs SignalGrade
    # C1 Long: c1_weight > 0; C1 Cash: c1_weight == 0
    c1_long = valid_df[valid_df["c1_weight"] > 0]
    c1_cash = valid_df[valid_df["c1_weight"] == 0]

    c1_long_grades = c1_long["signal_grade"].value_counts().to_dict()
    c1_long_pcts = {k: round(v / len(c1_long) * 100, 2) for k, v in c1_long_grades.items()} if len(c1_long) else {}

    c1_cash_grades = c1_cash["signal_grade"].value_counts().to_dict()
    c1_cash_pcts = {k: round(v / len(c1_cash) * 100, 2) for k, v in c1_cash_grades.items()} if len(c1_cash) else {}

    # 3. Performance by SignalGrade (Forward 7-day and 20-day returns)
    perf_by_grade = {}
    for g, group in valid_df.groupby("signal_grade"):
        fwd_7 = group["fwd_7"].dropna()
        fwd_20 = group["fwd_20"].dropna()
        perf_by_grade[g] = {
            "count": len(group),
            "mean_fwd_7": round(float(fwd_7.mean()) * 100, 3) if len(fwd_7) else None,
            "win_rate_7": round(float((fwd_7 > 0).mean()) * 100, 2) if len(fwd_7) else None,
            "mean_fwd_20": round(float(fwd_20.mean()) * 100, 3) if len(fwd_20) else None,
            "win_rate_20": round(float((fwd_20 > 0).mean()) * 100, 2) if len(fwd_20) else None,
        }

    # 4. Performance by C1 State
    perf_c1_long_7 = c1_long["fwd_7"].dropna()
    perf_c1_cash_7 = c1_cash["fwd_7"].dropna()

    c1_stats = {
        "c1_long": {
            "count": len(c1_long),
            "mean_fwd_7": round(float(perf_c1_long_7.mean()) * 100, 3) if len(perf_c1_long_7) else None,
            "win_rate_7": round(float((perf_c1_long_7 > 0).mean()) * 100, 2) if len(perf_c1_long_7) else None,
        },
        "c1_cash": {
            "count": len(c1_cash),
            "mean_fwd_7": round(float(perf_c1_cash_7.mean()) * 100, 3) if len(perf_c1_cash_7) else None,
            "win_rate_7": round(float((perf_c1_cash_7 > 0).mean()) * 100, 2) if len(perf_c1_cash_7) else None,
        },
    }

    # 5. False-Alarm Reduction & Divergence Analysis
    # Case A: SignalGrade says Enter/Add (可加仓/可入场/可试探), but C1 Absolute Momentum Filter rejects it (tsmom_state == 0)
    bullish_grades = ["可加仓", "可入场", "可试探"]
    bearish_grades = ["观望", "减仓"]

    sg_bull = valid_df[valid_df["signal_grade"].isin(bullish_grades)]
    # Dual filter agreement
    sg_bull_c1_approved = sg_bull[sg_bull["c1_weight"] > 0]
    sg_bull_c1_rejected = sg_bull[sg_bull["c1_weight"] == 0]

    fwd_app_7 = sg_bull_c1_approved["fwd_7"].dropna()
    fwd_rej_7 = sg_bull_c1_rejected["fwd_7"].dropna()

    divergence_analysis = {
        "sg_bullish_c1_approved": {
            "count": len(sg_bull_c1_approved),
            "mean_fwd_7": round(float(fwd_app_7.mean()) * 100, 3) if len(fwd_app_7) else None,
            "win_rate_7": round(float((fwd_app_7 > 0).mean()) * 100, 2) if len(fwd_app_7) else None,
        },
        "sg_bullish_c1_filtered_out": {
            "count": len(sg_bull_c1_rejected),
            "mean_fwd_7": round(float(fwd_rej_7.mean()) * 100, 3) if len(fwd_rej_7) else None,
            "win_rate_7": round(float((fwd_rej_7 > 0).mean()) * 100, 2) if len(fwd_rej_7) else None,
            "filtering_alpha": round(float(fwd_app_7.mean() - fwd_rej_7.mean()) * 100, 3)
            if (len(fwd_app_7) and len(fwd_rej_7))
            else None,
        },
    }

    return {
        "contract": "A3.3-shadow-signal-grade-comparison-v1",
        "total_evaluated_bars": total_samples,
        "grade_counts": grade_counts,
        "grade_percentages": grade_pcts,
        "c1_long_grade_breakdown_pct": c1_long_pcts,
        "c1_cash_grade_breakdown_pct": c1_cash_pcts,
        "performance_by_signal_grade": perf_by_grade,
        "performance_by_c1_state": c1_stats,
        "divergence_and_false_alarm_analysis": divergence_analysis,
    }


def main() -> None:
    print("--- Starting A3.3 Shadow Decision Comparison (SignalGrade vs Dual Momentum C1) ---")
    panel = load_long_history_panel()
    print(f"Loaded bars: {len(panel)}, distinct assets: {panel['ts_code'].nunique()}")

    enriched = compute_panel_with_signals_and_grades(panel)
    print("Calculated indicators, SignalGrade classifications, and C0/C1 weights.")

    results = analyze_shadow_comparison(enriched)

    out_file = OUT_DIR / "shadow_comparison_signal_grade.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Saved comparison results to {out_file}")
    print("\n=== A3.3 离线影子对比核心结论 ===")
    div = results["divergence_and_false_alarm_analysis"]
    print(
        f"1. 现行五档给出偏多建议且获双动量批准 (C1>0) 的 7日平均远期收益: {div['sg_bullish_c1_approved']['mean_fwd_7']}% (命中率 {div['sg_bullish_c1_approved']['win_rate_7']}%)"
    )
    print(
        f"2. 现行五档给出偏多建议但被双动量过滤 (C1=0) 的 7日平均远期收益: {div['sg_bullish_c1_filtered_out']['mean_fwd_7']}% (命中率 {div['sg_bullish_c1_filtered_out']['win_rate_7']}%)"
    )
    print(f"3. 绝对动量门控提供的超额过滤增益 (Filtering Alpha): {div['sg_bullish_c1_filtered_out']['filtering_alpha']}%")


if __name__ == "__main__":
    main()
