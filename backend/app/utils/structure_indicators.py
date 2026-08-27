from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def volume_profile(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    """ETF/LOF volume-at-price approximation, never true shareholder chips."""
    window = max(20, int(config.get("window", 120)))
    bins = max(20, int(config.get("bins", 80)))
    half_life = max(5.0, float(config.get("half_life", 60)))
    sample = frame.tail(window).copy()
    out: dict[str, Any] = {
        "chip_method": "volume_profile_approx",
        "chip_is_estimated": True,
        "chip_sample_count": len(sample),
    }
    if len(sample) < 20:
        return out
    low = pd.to_numeric(sample["low"], errors="coerce").to_numpy(float)
    high = pd.to_numeric(sample["high"], errors="coerce").to_numpy(float)
    close = pd.to_numeric(sample["close"], errors="coerce").to_numpy(float)
    volume = pd.to_numeric(sample["volume"], errors="coerce").fillna(0).to_numpy(float)
    finite = np.isfinite(low) & np.isfinite(high) & np.isfinite(close)
    if finite.sum() < 20:
        return out
    pmin, pmax = float(np.nanmin(low[finite])), float(np.nanmax(high[finite]))
    if pmax <= pmin:
        return out
    centers = np.linspace(pmin, pmax, bins)
    weights = np.zeros_like(centers)
    ages = np.arange(len(sample)-1, -1, -1, dtype=float)
    recency = np.power(0.5, ages / half_life)
    for lo, hi, cl, vol, decay in zip(low, high, close, volume, recency):
        if not np.isfinite(lo+hi+cl) or hi < lo or vol <= 0:
            continue
        typical = (lo + hi + cl) / 3
        width = max(hi-lo, (pmax-pmin)/bins)
        shape = np.maximum(0.0, 1.0 - np.abs(centers-typical)/(width*0.75))
        if shape.sum() <= 0:
            shape[np.argmin(np.abs(centers-typical))] = 1.0
        weights += shape / shape.sum() * vol * decay
    total = float(weights.sum())
    if total <= 0:
        return out
    shares = weights / total
    cumulative = shares.cumsum()
    latest = float(close[-1])
    def cost(q: float) -> float:
        return float(centers[min(int(np.searchsorted(cumulative, q, side="left")), len(centers)-1)])
    peak_idx = int(np.argmax(shares))
    peak = float(centers[peak_idx])
    winner = float(shares[centers <= latest].sum())
    c15, c50, c85 = cost(0.15), cost(0.50), cost(0.85)
    out.update({
        "chip_peak_price": round(peak, 4),
        "chip_peak_share": round(float(shares[peak_idx]), 4),
        "chip_winner_ratio": round(winner, 4),
        "chip_cost15": round(c15, 4),
        "chip_cost50": round(c50, 4),
        "chip_cost85": round(c85, 4),
        "chip_concentration_70": round((c85-c15)/max(c50, 1e-9), 4),
        "chip_distance_to_peak_pct": round((latest/peak-1)*100, 2) if peak else None,
    })
    return out


def add_structure_features(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    df = frame
    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    amount = pd.to_numeric(df.get("amount", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0)
    vol_cfg = config.get("volume", {})
    vol_window = int(vol_cfg.get("window", 20))
    df["volume_ma20"] = volume.rolling(vol_window, min_periods=1).mean()
    df["volume_ratio"] = volume / df["volume_ma20"].replace(0, np.nan)
    df["amount_ma20"] = amount.rolling(vol_window, min_periods=1).mean()
    df["amount_ratio"] = amount / df["amount_ma20"].replace(0, np.nan)
    vol_std = volume.rolling(vol_window, min_periods=10).std(ddof=0).replace(0, np.nan)
    df["volume_zscore20"] = ((volume - df["volume_ma20"]) / vol_std).fillna(0.0)
    df["vwap20"] = amount.rolling(20, min_periods=5).sum() / volume.rolling(20, min_periods=5).sum().replace(0, np.nan)

    box_windows = [int(x) for x in config.get("box_windows", [20, 55, 120])]
    for window in sorted(set(box_windows + [10])):
        ph = high.shift(1).rolling(window, min_periods=window).max()
        pl = low.shift(1).rolling(window, min_periods=window).min()
        df[f"prior_high_{window}"] = ph
        df[f"prior_low_{window}"] = pl
        if window in box_windows:
            spread = (ph-pl).replace(0, np.nan)
            df[f"box_range_{window}"] = spread / pl.replace(0, np.nan)
            df[f"box_position_{window}"] = (close-pl) / spread
            df[f"box_breakout_{window}"] = close / ph.replace(0, np.nan) - 1
    df["turtle_entry_20"] = close.ge(df["prior_high_20"]).fillna(False)
    df["turtle_entry_55"] = close.ge(df.get("prior_high_55", np.nan)).fillna(False)
    df["turtle_exit_10"] = close.le(df["prior_low_10"]).fillna(False)
    df["turtle_exit_20"] = close.le(df["prior_low_20"]).fillna(False)
    breakout_ratio = float(vol_cfg.get("breakout_ratio", 1.35))
    df["volume_breakout"] = (close.ge(df["prior_high_20"]*0.98) & df["volume_ratio"].ge(breakout_ratio)).fillna(False)
    df["false_breakout_risk"] = (
        high.ge(df["prior_high_20"]*0.995) & close.lt(df["prior_high_20"]*0.985) & df["volume_ratio"].lt(1.0)
    ).fillna(False)

    pull_cfg = config.get("pullback", {})
    ignition_ratio = float(pull_cfg.get("ignition_volume_ratio", 1.5))
    contraction_max = float(pull_cfg.get("contraction_max", 0.90))
    support_ratio = float(pull_cfg.get("support_ratio", 0.97))
    ignition = (df["volume_ratio"] >= ignition_ratio) & (close >= df["prior_high_20"]*0.98)
    last_idx: int | None = None
    bars_since, ign_low, ign_high, ign_vol, ign_platform = [], [], [], [], []
    for i in range(len(df)):
        if bool(ignition.iloc[i]):
            last_idx = i
        if last_idx is None:
            bars_since.append(np.nan); ign_low.append(np.nan); ign_high.append(np.nan); ign_vol.append(np.nan); ign_platform.append(np.nan)
        else:
            bars_since.append(i-last_idx)
            ign_low.append(float(low.iloc[last_idx])); ign_high.append(float(high.iloc[last_idx])); ign_vol.append(float(volume.iloc[last_idx]))
            ign_platform.append(float(df["prior_high_20"].iloc[last_idx]) if pd.notna(df["prior_high_20"].iloc[last_idx]) else float(low.iloc[last_idx]))
    df["bars_since_ignition"] = bars_since
    df["last_ignition_low"] = ign_low
    df["last_ignition_high"] = ign_high
    df["last_ignition_volume"] = ign_vol
    df["last_ignition_platform"] = ign_platform
    df["pullback_volume_ratio"] = volume / pd.Series(ign_vol, index=df.index).replace(0, np.nan)
    recent = pd.Series(bars_since, index=df.index).between(1, int(pull_cfg.get("max_age", 12)))
    support = pd.concat([
        df["last_ignition_low"]*support_ratio,
        df["last_ignition_platform"]*float(pull_cfg.get("platform_ratio", 0.96)),
    ], axis=1).max(axis=1)
    df["pullback_support"] = support
    df["pullback_ready"] = (recent & close.ge(support) & df["pullback_volume_ratio"].le(contraction_max) & close.ge(df.get("ma20", close)*0.98)).fillna(False)
    df["second_launch"] = (recent & close.ge(support) & close.gt(high.shift(1)) & close.gt(close.shift(1)) & df["volume_ratio"].ge(0.85)).fillna(False)
    df["pullback_support_broken"] = (recent & close.lt(support)).fillna(False)
    return df
