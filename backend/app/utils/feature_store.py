from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from app.utils.indicators_v05 import calculate_indicators

FEATURE_SCHEMA_VERSION = "feature-store-v0.7.0"

LEGACY_FEATURES = (
    "return_1d",
    "return_5d",
    "return_20d",
    "ma_gap_5_20",
    "ma_gap_20_60",
    "macd_norm",
    "kdj_j",
    "rsi14",
    "atr_pct",
    "volume_ratio",
    "volatility_20d",
    "drawdown_60d",
)

HORIZON_FEATURES: dict[int, tuple[str, ...]] = {
    1: LEGACY_FEATURES
    + (
        "amount_ratio",
        "volume_zscore20",
        "obv_slope_5",
        "mfi14",
        "cmf20",
        "adx14",
        "plus_di14",
        "minus_di14",
        "cci20",
        "wr14",
        "roc12",
        "rsrs_zscore",
        "rps20",
        "volume_breakout",
        "false_breakout_risk",
    ),
    5: LEGACY_FEATURES
    + (
        "return_60d",
        "amount_ratio",
        "obv_slope_5",
        "mfi14",
        "cmf20",
        "adx14",
        "cci20",
        "roc12",
        "rsrs_zscore",
        "box_position_20",
        "box_range_20",
        "box_position_55",
        "turtle_entry_20",
        "turtle_entry_55",
        "pullback_ready",
        "second_launch",
        "rps20",
        "rps60",
        "vp_peak_distance",
        "cost50_distance",
    ),
    20: LEGACY_FEATURES
    + (
        "return_60d",
        "return_120d",
        "mfi14",
        "cmf20",
        "adx14",
        "rsrs_zscore",
        "rsrs_right_skew",
        "box_position_55",
        "box_range_55",
        "box_position_120",
        "box_range_120",
        "pullback_ready",
        "second_launch",
        "rps20",
        "rps60",
        "rps120",
        "vp_peak_distance",
        "cost50_distance",
        "profit_ratio_est",
        "chip_concentration",
    ),
}

BOOLEAN_FEATURES = (
    "turtle_entry_20",
    "turtle_entry_55",
    "turtle_exit_10",
    "turtle_exit_20",
    "volume_breakout",
    "false_breakout_risk",
    "pullback_ready",
    "second_launch",
    "pullback_support_broken",
)


@dataclass(slots=True)
class FeatureFrame:
    frame: pd.DataFrame
    values: dict[str, Any]
    feature_schema_version: str = FEATURE_SCHEMA_VERSION


def _weighted_quantiles(values: np.ndarray, weights: np.ndarray, quantiles: Iterable[float]) -> np.ndarray:
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cumulative = np.cumsum(weights)
    if cumulative[-1] <= 0:
        return np.quantile(values, list(quantiles))
    cumulative = (cumulative - 0.5 * weights) / cumulative[-1]
    return np.interp(np.asarray(list(quantiles), dtype=float), cumulative, values)


def _rolling_volume_profile(frame: pd.DataFrame, window: int = 120, bins: int = 32) -> pd.DataFrame:
    typical = (frame["high"].astype(float) + frame["low"].astype(float) + frame["close"].astype(float)) / 3.0
    volume = frame["volume"].astype(float).fillna(0.0).clip(lower=0.0)
    close = frame["close"].astype(float)
    outputs = {
        "vp_peak_distance": np.full(len(frame), np.nan),
        "cost50_distance": np.full(len(frame), np.nan),
        "profit_ratio_est": np.full(len(frame), np.nan),
        "chip_concentration": np.full(len(frame), np.nan),
    }
    for end in range(window - 1, len(frame)):
        start = end - window + 1
        prices = typical.iloc[start : end + 1].to_numpy(dtype=float)
        weights = volume.iloc[start : end + 1].to_numpy(dtype=float)
        valid = np.isfinite(prices) & np.isfinite(weights) & (weights > 0)
        if valid.sum() < max(20, window // 3):
            continue
        prices = prices[valid]
        weights = weights[valid]
        low, high = float(prices.min()), float(prices.max())
        if high <= low:
            continue
        edges = np.linspace(low, high, bins + 1)
        histogram, _ = np.histogram(prices, bins=edges, weights=weights)
        centers = (edges[:-1] + edges[1:]) / 2.0
        peak = float(centers[int(np.argmax(histogram))])
        q15, q50, q85 = _weighted_quantiles(prices, weights, (0.15, 0.50, 0.85))
        current = float(close.iloc[end])
        total = float(weights.sum())
        outputs["vp_peak_distance"][end] = current / peak - 1.0 if peak > 0 else np.nan
        outputs["cost50_distance"][end] = current / float(q50) - 1.0 if q50 > 0 else np.nan
        outputs["profit_ratio_est"][end] = float(weights[prices <= current].sum() / total) if total > 0 else np.nan
        outputs["chip_concentration"][end] = float((q85 - q15) / q50) if q50 > 0 else np.nan
    return pd.DataFrame(outputs, index=frame.index)


def build_feature_frame(raw_frame: pd.DataFrame, indicator_config: dict[str, Any]) -> FeatureFrame:
    result = calculate_indicators(raw_frame, indicator_config)
    frame = result.frame.copy()
    frame["ma_gap_5_20"] = frame["ma5"] / frame["ma20"].replace(0, np.nan) - 1.0
    frame["ma_gap_20_60"] = frame["ma20"] / frame["ma60"].replace(0, np.nan) - 1.0
    frame["macd_norm"] = frame["macd_hist"] / frame["close"].replace(0, np.nan)
    for name in BOOLEAN_FEATURES:
        if name in frame:
            frame[name] = frame[name].astype(float)
    profile = _rolling_volume_profile(
        frame,
        window=int(indicator_config.get("chip", {}).get("window", 120)),
        bins=int(indicator_config.get("chip", {}).get("bins", 32)),
    )
    for name in profile:
        frame[name] = profile[name]
    return FeatureFrame(frame=frame, values=result.values)


def add_cross_sectional_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Add date-local RPS values without using future observations."""
    if panel.empty:
        return panel.copy()
    result = panel.copy()
    for horizon in (20, 60, 120):
        source = f"return_{horizon}d"
        target = f"rps{horizon}"
        if source not in result:
            result[target] = np.nan
            continue
        result[target] = result.groupby("trade_date", observed=True)[source].rank(
            method="average", pct=True
        ) * 100.0
    return result


def feature_columns_for_horizon(horizon: int, available: Iterable[str] | None = None) -> tuple[str, ...]:
    requested = HORIZON_FEATURES.get(int(horizon), LEGACY_FEATURES)
    if available is None:
        return requested
    available_set = set(available)
    selected = tuple(name for name in requested if name in available_set)
    if len(selected) >= 6:
        return selected
    return tuple(name for name in LEGACY_FEATURES if name in available_set)
