from __future__ import annotations

import numpy as np
import pandas as pd


def wilder(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    return pd.concat([(high-low).abs(), (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)


def rsi(series: pd.Series, window: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = wilder(gain, window)
    avg_loss = wilder(loss, window)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    return out.mask(avg_loss == 0, 100.0).mask(avg_gain == 0, 0.0).mask(both_zero, 50.0).fillna(50.0)


def adx_dmi(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index, dtype=float)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index, dtype=float)
    atr = wilder(true_range(high, low, close), window).replace(0, np.nan)
    plus_di = 100 * wilder(plus_dm, window) / atr
    minus_di = 100 * wilder(minus_dm, window) / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = wilder(dx.fillna(0.0), window)
    return adx.fillna(0.0), plus_di.fillna(0.0), minus_di.fillna(0.0)


def cci(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 20) -> pd.Series:
    typical = (high + low + close) / 3
    mean = typical.rolling(window, min_periods=window).mean()
    mad = typical.rolling(window, min_periods=window).apply(
        lambda x: float(np.mean(np.abs(x - np.mean(x)))), raw=True
    )
    return ((typical - mean) / (0.015 * mad.replace(0, np.nan))).fillna(0.0)


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    hh = high.rolling(window, min_periods=window).max()
    ll = low.rolling(window, min_periods=window).min()
    return (-100 * (hh - close) / (hh - ll).replace(0, np.nan)).fillna(-50.0)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0.0))
    return pd.Series((direction * volume).cumsum(), index=close.index, dtype=float)


def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int = 14) -> pd.Series:
    typical = (high + low + close) / 3
    money = typical * volume
    delta = typical.diff()
    positive = money.where(delta > 0, 0.0).rolling(window, min_periods=window).sum()
    negative = money.where(delta < 0, 0.0).abs().rolling(window, min_periods=window).sum()
    ratio = positive / negative.replace(0, np.nan)
    out = 100 - 100 / (1 + ratio)
    out = out.mask((negative == 0) & (positive > 0), 100.0)
    out = out.mask((positive == 0) & (negative > 0), 0.0)
    return out.fillna(50.0)


def cmf(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int = 20) -> pd.Series:
    span = (high - low).replace(0, np.nan)
    multiplier = (((close-low) - (high-close)) / span).fillna(0.0)
    mfv = multiplier * volume
    denominator = volume.rolling(window, min_periods=window).sum().replace(0, np.nan)
    return (mfv.rolling(window, min_periods=window).sum() / denominator).fillna(0.0)


def rsrs(
    high: pd.Series,
    low: pd.Series,
    regression_window: int = 18,
    zscore_window: int = 60,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """RSRS: OLS(high ~ low), raw=beta*R², then rolling z-score."""
    beta = np.full(len(high), np.nan)
    r2 = np.full(len(high), np.nan)
    raw = np.full(len(high), np.nan)
    hv, lv = high.to_numpy(float), low.to_numpy(float)
    for i in range(regression_window - 1, len(high)):
        x = lv[i+1-regression_window:i+1]
        y = hv[i+1-regression_window:i+1]
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            continue
        mx, my = float(x.mean()), float(y.mean())
        cx = x - mx
        sxx = float(np.dot(cx, cx))
        if sxx <= 0:
            continue
        b = float(np.dot(cx, y-my) / sxx)
        pred = (my - b*mx) + b*x
        sst = float(np.dot(y-my, y-my))
        if sst <= 0:
            continue
        rr = max(0.0, min(1.0, 1 - float(np.dot(y-pred, y-pred))/sst))
        beta[i], r2[i], raw[i] = b, rr, b*rr
    beta_s = pd.Series(beta, index=high.index)
    r2_s = pd.Series(r2, index=high.index)
    raw_s = pd.Series(raw, index=high.index)
    minp = max(20, min(zscore_window, zscore_window // 2))
    mean = raw_s.rolling(zscore_window, min_periods=minp).mean()
    std = raw_s.rolling(zscore_window, min_periods=minp).std(ddof=0).replace(0, np.nan)
    z = ((raw_s - mean) / std).fillna(0.0)
    return beta_s, r2_s, raw_s, z
