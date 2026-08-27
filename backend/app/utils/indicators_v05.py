from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from app.utils.advanced_indicators import adx_dmi, cci, cmf, mfi, obv, rsi, rsrs, williams_r
from app.utils.indicators import IndicatorResult, calculate_indicators as calculate_base
from app.utils.numbers import clamp
from app.utils.structure_indicators import add_structure_features, volume_profile


def _num(value: Any, digits: int = 4) -> float | None:
    if value is None or pd.isna(value):
        return None
    value = float(value)
    if not math.isfinite(value):
        return None
    return round(value, digits)


def calculate_indicators(frame: pd.DataFrame, config: dict[str, Any]) -> IndicatorResult:
    base = calculate_base(frame, config)
    df = base.frame.copy()
    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    df["rsi14"] = rsi(close, 14)
    df["return_120d"] = close.pct_change(120)
    trend_cfg = config.get("trend_strength", {})
    window = int(trend_cfg.get("adx_window", 14))
    df["adx14"], df["plus_di14"], df["minus_di14"] = adx_dmi(high, low, close, window)
    df["cci20"] = cci(high, low, close, int(trend_cfg.get("cci_window", 20)))
    df["wr14"] = williams_r(high, low, close, int(trend_cfg.get("wr_window", 14)))
    df["wr28"] = williams_r(high, low, close, int(trend_cfg.get("wr_long_window", 28)))
    df["roc12"] = close.pct_change(int(trend_cfg.get("roc_window", 12))) * 100
    df["obv"] = obv(close, volume)
    df["obv_slope_5"] = df["obv"].pct_change(5).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    flow_cfg = config.get("money_flow", {})
    df["mfi14"] = mfi(high, low, close, volume, int(flow_cfg.get("mfi_window", 14)))
    df["cmf20"] = cmf(high, low, close, volume, int(flow_cfg.get("cmf_window", 20)))
    df = add_structure_features(df, config)
    rsrs_cfg = config.get("rsrs", {})
    df["rsrs_beta"], df["rsrs_r2"], df["rsrs_raw"], df["rsrs_zscore"] = rsrs(
        high, low,
        int(rsrs_cfg.get("regression_window", 18)),
        int(rsrs_cfg.get("zscore_window", 60)),
    )
    df["rsrs_right_skew"] = df["rsrs_zscore"] * df["rsrs_beta"] * df["rsrs_r2"]
    chip = volume_profile(df, config.get("chip", {}))
    latest = df.iloc[-1]
    values = dict(base.values)
    keys = [
        "amount_ratio","volume_zscore20","vwap20","obv","obv_slope_5","mfi14","cmf20",
        "adx14","plus_di14","minus_di14","cci20","wr14","wr28","roc12","return_120d",
        "rsrs_beta","rsrs_r2","rsrs_raw","rsrs_zscore","rsrs_right_skew",
        "box_range_20","box_position_20","box_range_55","box_position_55","box_range_120","box_position_120",
        "pullback_volume_ratio","pullback_support",
    ]
    for key in keys:
        values[key] = _num(latest.get(key), 4)
    for key in ["turtle_entry_20","turtle_entry_55","turtle_exit_10","turtle_exit_20","volume_breakout","false_breakout_risk","pullback_ready","second_launch","pullback_support_broken"]:
        values[key] = bool(latest.get(key))
    values.update(chip)
    reasons = list(values.get("technical_reasons") or [])
    score, risk = float(base.technical_score), float(base.risk_score)
    adx = float(latest.get("adx14") or 0); pdi = float(latest.get("plus_di14") or 0); mdi = float(latest.get("minus_di14") or 0)
    cmf20 = float(latest.get("cmf20") or 0); mfi14 = float(latest.get("mfi14") or 50); rz = float(latest.get("rsrs_zscore") or 0)
    if adx >= 20 and pdi > mdi: score += 5; reasons.append("ADX/DMI 趋势确认")
    elif adx >= 25 and mdi > pdi: score -= 6; reasons.append("ADX/DMI 空头趋势")
    if cmf20 >= 0.05 and mfi14 >= 55: score += 4; reasons.append("CMF/MFI 资金流确认")
    if bool(latest.get("pullback_ready")): score += 4; reasons.append("放量突破后缩量承接")
    if bool(latest.get("turtle_entry_55")): score += 4; reasons.append("海龟55日突破")
    if rz >= 0.7: score += 3; reasons.append("RSRS 偏多")
    elif rz <= -0.7: score -= 4; risk += 6; reasons.append("RSRS 偏空")
    if bool(latest.get("false_breakout_risk")): risk += 8
    values["technical_reasons"] = list(dict.fromkeys(reasons))[:16]
    quality_fields = ["adx14","mfi14","cmf20","rsrs_zscore","box_position_20"]
    quality = sum(pd.notna(latest.get(k)) for k in quality_fields) / len(quality_fields) * 100
    data_quality = round(0.7 * base.data_quality + 0.3 * quality, 2)
    final_score = round(clamp(score, 0, 100), 2)
    if final_score >= 72: label = "强势"
    elif final_score >= 58: label = "偏强"
    elif final_score >= 43: label = "震荡"
    elif final_score >= 30: label = "偏弱"
    else: label = "弱势"
    return IndicatorResult(df, values, final_score, round(clamp(risk, 0, 100), 2), label, data_quality)


__all__ = ["IndicatorResult", "calculate_indicators"]
