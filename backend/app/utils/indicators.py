from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.utils.numbers import clamp


@dataclass(slots=True)
class IndicatorResult:
    frame: pd.DataFrame
    values: dict[str, Any]
    technical_score: float
    risk_score: float
    trend_label: str
    data_quality: float


def _rsi(series: pd.Series, window: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    return result.fillna(50.0)


def _kdj(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 9, initial: float = 50.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    lowest = low.rolling(period, min_periods=1).min()
    highest = high.rolling(period, min_periods=1).max()
    denominator = (highest - lowest).replace(0, np.nan)
    rsv = ((close - lowest) / denominator * 100).fillna(initial).clip(0, 100)
    k_values: list[float] = []
    d_values: list[float] = []
    k = initial
    d = initial
    for value in rsv.tolist():
        k = (2.0 / 3.0) * k + (1.0 / 3.0) * float(value)
        d = (2.0 / 3.0) * d + (1.0 / 3.0) * k
        k_values.append(k)
        d_values.append(d)
    k_series = pd.Series(k_values, index=close.index)
    d_series = pd.Series(d_values, index=close.index)
    j_series = 3 * k_series - 2 * d_series
    return k_series, d_series, j_series


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    previous_close = close.shift(1)
    true_range = pd.concat(
        [(high - low).abs(), (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def _td_setup(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    buy_counts: list[int] = []
    sell_counts: list[int] = []
    buy = 0
    sell = 0
    values = close.tolist()
    for idx, current in enumerate(values):
        if idx < 4 or not math.isfinite(float(current)):
            buy = sell = 0
        else:
            reference = float(values[idx - 4])
            if float(current) < reference:
                buy += 1
                sell = 0
            elif float(current) > reference:
                sell += 1
                buy = 0
            else:
                buy = sell = 0
        buy_counts.append(buy)
        sell_counts.append(sell)
    return pd.Series(buy_counts, index=close.index), pd.Series(sell_counts, index=close.index)


def _to_number(value: Any, digits: int = 4) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return round(number, digits)


def calculate_indicators(frame: pd.DataFrame, config: dict[str, Any]) -> IndicatorResult:
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"指标输入缺少字段: {sorted(missing)}")
    if frame.empty:
        raise ValueError("指标输入为空")

    df = frame.copy().sort_values("trade_date").reset_index(drop=True)
    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)

    for window in config.get("ma_windows", [5, 10, 20, 30, 60]):
        df[f"ma{window}"] = close.rolling(window, min_periods=window).mean()

    macd_cfg = config.get("macd", {})
    fast = int(macd_cfg.get("fast", 12))
    slow = int(macd_cfg.get("slow", 26))
    signal = int(macd_cfg.get("signal", 9))
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    df["macd_dif"] = ema_fast - ema_slow
    df["macd_dea"] = df["macd_dif"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"] = 2 * (df["macd_dif"] - df["macd_dea"])

    kdj_cfg = config.get("kdj", {})
    df["kdj_k"], df["kdj_d"], df["kdj_j"] = _kdj(
        high,
        low,
        close,
        period=int(kdj_cfg.get("period", 9)),
        initial=float(kdj_cfg.get("initial", 50)),
    )

    for window in config.get("rsi_windows", [6, 12, 14]):
        df[f"rsi{window}"] = _rsi(close, int(window))

    atr_window = int(config.get("atr_window", 14))
    df["atr"] = _atr(high, low, close, atr_window)
    df["atr_pct"] = df["atr"] / close.replace(0, np.nan) * 100

    boll_window = int(config.get("boll_window", 20))
    boll_std = float(config.get("boll_std", 2))
    df["boll_mid"] = close.rolling(boll_window, min_periods=boll_window).mean()
    rolling_std = close.rolling(boll_window, min_periods=boll_window).std(ddof=0)
    df["boll_upper"] = df["boll_mid"] + boll_std * rolling_std
    df["boll_lower"] = df["boll_mid"] - boll_std * rolling_std

    df["volume_ma5"] = volume.rolling(5, min_periods=1).mean()
    df["volume_ma20"] = volume.rolling(20, min_periods=1).mean()
    df["volume_ratio"] = volume / df["volume_ma20"].replace(0, np.nan)

    df["return_1d"] = close.pct_change()
    df["return_5d"] = close.pct_change(5)
    df["return_20d"] = close.pct_change(20)
    df["return_60d"] = close.pct_change(60)
    df["volatility_20d"] = df["return_1d"].rolling(20, min_periods=10).std() * math.sqrt(252)
    rolling_max = close.rolling(60, min_periods=20).max()
    df["drawdown_60d"] = close / rolling_max - 1
    df["td_buy_setup"], df["td_sell_setup"] = _td_setup(close)

    latest = df.iloc[-1]
    available = sum(int(not pd.isna(latest.get(key))) for key in ["ma20", "ma60", "atr_pct", "volatility_20d"])
    history_quality = min(100.0, len(df) / 240 * 100)
    field_quality = available / 4 * 100
    data_quality = round(0.65 * history_quality + 0.35 * field_quality, 2)

    score = 50.0
    reasons: list[str] = []
    last_close = float(latest["close"])
    ma5 = latest.get("ma5")
    ma10 = latest.get("ma10")
    ma20 = latest.get("ma20")
    ma30 = latest.get("ma30")
    ma60 = latest.get("ma60")
    ma_values = [ma5, ma10, ma20, ma30, ma60]
    if all(not pd.isna(value) for value in ma_values):
        if ma5 > ma10 > ma20 > ma30 > ma60:
            score += 18
            reasons.append("均线多头排列")
        elif ma5 < ma10 < ma20 < ma30 < ma60:
            score -= 18
            reasons.append("均线空头排列")
        elif last_close > ma20 and ma20 > ma60:
            score += 9
            reasons.append("价格站上中期均线")
        elif last_close < ma20 and ma20 < ma60:
            score -= 9
            reasons.append("价格位于中期均线下方")

    dif = float(latest["macd_dif"])
    dea = float(latest["macd_dea"])
    hist = float(latest["macd_hist"])
    previous_hist = float(df.iloc[-2]["macd_hist"]) if len(df) > 1 else hist
    if dif > dea and hist > 0:
        score += 10
        reasons.append("MACD 多头")
        if hist > previous_hist:
            score += 3
            reasons.append("MACD 红柱增强")
    elif dif < dea and hist < 0:
        score -= 10
        reasons.append("MACD 空头")
        if hist < previous_hist:
            score -= 3
            reasons.append("MACD 绿柱扩大")

    j_value = float(latest["kdj_j"])
    k_value = float(latest["kdj_k"])
    d_value = float(latest["kdj_d"])
    if k_value > d_value and j_value < 90:
        score += 6
        reasons.append("KDJ 金叉或多头")
    elif k_value < d_value:
        score -= 5
        reasons.append("KDJ 偏弱")
    if j_value < 10:
        score += 4
        reasons.append("KDJ 低位")
    if j_value > 100:
        score -= 5
        reasons.append("KDJ 过热")

    rsi14 = float(latest.get("rsi14", 50))
    if 50 <= rsi14 <= 68:
        score += 5
    elif rsi14 >= 75:
        score -= 8
        reasons.append("RSI 超买")
    elif rsi14 < 35:
        score -= 3
        reasons.append("RSI 弱势")

    volume_ratio = float(latest.get("volume_ratio") or 0)
    return_5d = float(latest.get("return_5d") or 0)
    if volume_ratio > 1.25 and return_5d > 0:
        score += 7
        reasons.append("上涨放量")
    elif volume_ratio > 1.4 and return_5d < 0:
        score -= 7
        reasons.append("下跌放量")

    risk = 50.0
    atr_pct = float(latest.get("atr_pct") or 0)
    volatility = float(latest.get("volatility_20d") or 0)
    drawdown = float(latest.get("drawdown_60d") or 0)
    if atr_pct > 3.5:
        risk += 12
    elif atr_pct < 1.5:
        risk -= 6
    if volatility > 0.35:
        risk += 12
    elif volatility < 0.18:
        risk -= 5
    if drawdown < -0.15:
        risk += 10
    if int(latest.get("td_sell_setup") or 0) >= int(config.get("td_setup_length", 9)):
        risk += 10
        reasons.append("TD 卖出设置达到风险计数")
    if int(latest.get("td_buy_setup") or 0) >= int(config.get("td_setup_length", 9)):
        risk -= 4
        reasons.append("TD 买入设置达到低位计数")

    technical_score = round(clamp(score, 0, 100), 2)
    risk_score = round(clamp(risk, 0, 100), 2)
    if technical_score >= 72:
        trend_label = "强势"
    elif technical_score >= 58:
        trend_label = "偏强"
    elif technical_score >= 43:
        trend_label = "震荡"
    elif technical_score >= 30:
        trend_label = "偏弱"
    else:
        trend_label = "弱势"

    values = {
        "close": _to_number(latest["close"]),
        "ma5": _to_number(ma5),
        "ma10": _to_number(ma10),
        "ma20": _to_number(ma20),
        "ma30": _to_number(ma30),
        "ma60": _to_number(ma60),
        "macd_dif": _to_number(dif, 6),
        "macd_dea": _to_number(dea, 6),
        "macd_hist": _to_number(hist, 6),
        "kdj_k": _to_number(k_value, 2),
        "kdj_d": _to_number(d_value, 2),
        "kdj_j": _to_number(j_value, 2),
        "rsi6": _to_number(latest.get("rsi6"), 2),
        "rsi12": _to_number(latest.get("rsi12"), 2),
        "rsi14": _to_number(rsi14, 2),
        "atr": _to_number(latest.get("atr"), 4),
        "atr_pct": _to_number(atr_pct, 2),
        "boll_mid": _to_number(latest.get("boll_mid"), 4),
        "boll_upper": _to_number(latest.get("boll_upper"), 4),
        "boll_lower": _to_number(latest.get("boll_lower"), 4),
        "volume_ratio": _to_number(volume_ratio, 2),
        "return_1d": _to_number(latest.get("return_1d"), 6),
        "return_5d": _to_number(return_5d, 6),
        "return_20d": _to_number(latest.get("return_20d"), 6),
        "return_60d": _to_number(latest.get("return_60d"), 6),
        "volatility_20d": _to_number(volatility, 4),
        "drawdown_60d": _to_number(drawdown, 4),
        "td_buy_setup": int(latest.get("td_buy_setup") or 0),
        "td_sell_setup": int(latest.get("td_sell_setup") or 0),
        "technical_reasons": reasons,
    }
    return IndicatorResult(
        frame=df,
        values=values,
        technical_score=technical_score,
        risk_score=risk_score,
        trend_label=trend_label,
        data_quality=data_quality,
    )
