"""Deterministic price-level research utilities for the ETF 14:30 workbench.

The module never turns oscillator values into prices.  MACD/KDJ/RSI are used
only to confirm historical *price* pivots.  ``chan_zone_approx`` is explicitly a
price-overlap approximation, not a full Chan-theory implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(slots=True)
class _Candidate:
    price: float
    method: str
    weight: float


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _pivot_indexes(values: pd.Series, *, window: int, kind: str) -> list[int]:
    array = values.astype(float).to_numpy()
    indexes: list[int] = []
    if len(array) < window * 2 + 1:
        return indexes
    for index in range(window, len(array) - window):
        center = array[index]
        segment = array[index - window : index + window + 1]
        if not np.isfinite(center) or not np.isfinite(segment).all():
            continue
        if kind == "high" and center == segment.max() and np.count_nonzero(segment == center) == 1:
            indexes.append(index)
        elif kind == "low" and center == segment.min() and np.count_nonzero(segment == center) == 1:
            indexes.append(index)
    return indexes


def _indicator_confirmations(frame: pd.DataFrame, index: int, kind: str) -> list[str]:
    methods: list[str] = []
    row = frame.iloc[index]
    prior = frame.iloc[index - 1] if index > 0 else row
    after = frame.iloc[index + 1] if index + 1 < len(frame) else row

    hist = _number(row.get("macd_hist"))
    prior_hist = _number(prior.get("macd_hist"))
    after_hist = _number(after.get("macd_hist"))
    dif = _number(row.get("macd_dif"))
    dea = _number(row.get("macd_dea"))
    if None not in (hist, prior_hist, after_hist, dif, dea):
        if kind == "high" and hist > 0 and after_hist < hist and dif >= dea:
            methods.append("MACD确认拐点")
        elif kind == "low" and hist < 0 and after_hist > hist and dif <= dea:
            methods.append("MACD确认拐点")

    j = _number(row.get("kdj_j"))
    if j is not None:
        if kind == "high" and j >= 80:
            methods.append("KDJ确认拐点")
        elif kind == "low" and j <= 20:
            methods.append("KDJ确认拐点")

    rsi = _number(row.get("rsi14"))
    if rsi is not None:
        if kind == "high" and rsi >= 65:
            methods.append("RSI确认拐点")
        elif kind == "low" and rsi <= 35:
            methods.append("RSI确认拐点")
    return methods


def _volume_profile(frame: pd.DataFrame, window: int, bins: int) -> dict[str, float] | None:
    sample = frame.tail(max(20, window)).copy()
    typical = (sample["high"].astype(float) + sample["low"].astype(float) + sample["close"].astype(float)) / 3
    volume = sample["volume"].astype(float).fillna(0).clip(lower=0)
    valid = np.isfinite(typical) & np.isfinite(volume) & (volume > 0)
    if int(valid.sum()) < 20:
        return None
    prices = typical[valid].to_numpy(dtype=float)
    weights = volume[valid].to_numpy(dtype=float)
    low, high = float(prices.min()), float(prices.max())
    if high <= low:
        return None
    edges = np.linspace(low, high, max(8, bins) + 1)
    histogram, _ = np.histogram(prices, bins=edges, weights=weights)
    centers = (edges[:-1] + edges[1:]) / 2
    peak = float(centers[int(np.argmax(histogram))])
    order = np.argsort(prices)
    sorted_prices = prices[order]
    sorted_weights = weights[order]
    cumulative = np.cumsum(sorted_weights)
    cumulative = (cumulative - 0.5 * sorted_weights) / cumulative[-1]
    q15, q50, q85 = np.interp([0.15, 0.50, 0.85], cumulative, sorted_prices)
    return {"peak": peak, "cost15": float(q15), "cost50": float(q50), "cost85": float(q85)}


def _chan_zone_approx(frame: pd.DataFrame, segments: int = 3, segment_bars: int = 18) -> dict[str, Any] | None:
    """Approximate a central overlap zone from recent non-overlapping ranges.

    This intentionally avoids claiming full Chan-theory semantics.  A complete
    implementation requires validated fractals, strokes, segments and centres.
    """

    needed = segments * segment_bars
    if len(frame) < needed:
        return None
    sample = frame.tail(needed)
    ranges: list[tuple[float, float]] = []
    for offset in range(segments):
        part = sample.iloc[offset * segment_bars : (offset + 1) * segment_bars]
        ranges.append((float(part["low"].min()), float(part["high"].max())))
    lower = max(item[0] for item in ranges)
    upper = min(item[1] for item in ranges)
    if not isfinite(lower) or not isfinite(upper) or lower >= upper:
        return None
    return {
        "method": "chan_zone_approx",
        "qualified": False,
        "lower": round(lower, 6),
        "middle": round((lower + upper) / 2, 6),
        "upper": round(upper, 6),
        "ranges": [[round(low, 6), round(high, 6)] for low, high in ranges],
        "disclaimer": "价格重叠区近似，不等同于完整缠论笔、线段与中枢。",
    }


def _trend_line(frame: pd.DataFrame, indexes: list[int], column: str, label: str) -> dict[str, Any] | None:
    if len(indexes) < 2:
        return None
    first, second = indexes[-2], indexes[-1]
    if second <= first:
        return None
    first_price = float(frame.iloc[first][column])
    second_price = float(frame.iloc[second][column])
    slope = (second_price - first_price) / (second - first)
    projected = second_price + slope * (len(frame) - 1 - second)
    if not isfinite(projected) or projected <= 0:
        return None
    return {
        "label": label,
        "method": "confirmed_pivot_trendline",
        "start_index": first,
        "end_index": second,
        "start_price": round(first_price, 6),
        "end_price": round(second_price, 6),
        "projected_price": round(projected, 6),
        "slope_per_bar": round(slope, 8),
    }


def _cluster(candidates: Iterable[_Candidate], *, current: float, tolerance: float) -> list[dict[str, Any]]:
    ordered = sorted((item for item in candidates if item.price > 0 and isfinite(item.price)), key=lambda item: item.price)
    groups: list[list[_Candidate]] = []
    for item in ordered:
        if not groups:
            groups.append([item])
            continue
        previous_price = sum(row.price * row.weight for row in groups[-1]) / sum(row.weight for row in groups[-1])
        if abs(item.price - previous_price) <= tolerance:
            groups[-1].append(item)
        else:
            groups.append([item])

    levels: list[dict[str, Any]] = []
    for group in groups:
        total_weight = sum(item.weight for item in group)
        price = sum(item.price * item.weight for item in group) / max(total_weight, 1e-9)
        methods = sorted({item.method for item in group})
        distance = price / current - 1 if current > 0 else 0
        strength = min(100.0, 14.0 * total_weight + 5.0 * len(methods))
        levels.append(
            {
                "price": round(price, 6),
                "kind": "support" if price <= current else "resistance",
                "strength": round(strength, 1),
                "methods": methods,
                "confirmations": len(group),
                "distance_pct": round(distance * 100, 3),
            }
        )
    return levels


def build_support_resistance(
    frame: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return auditable support/resistance zones from a rich daily feature frame."""

    config = config or {}
    if frame.empty or len(frame) < 30:
        return {
            "qualified": False,
            "reason": "history_too_short",
            "levels": [],
            "nearest_support": None,
            "nearest_resistance": None,
            "trend_lines": [],
            "chan_zone_approx": None,
        }
    current = float(frame.iloc[-1]["close"])
    atr = _number(frame.iloc[-1].get("atr14")) or current * 0.02
    tolerance = max(current * float(config.get("cluster_tolerance_pct", 0.006)), atr * 0.30)
    pivot_window = int(config.get("pivot_window", 2))
    high_indexes = _pivot_indexes(frame["high"], window=pivot_window, kind="high")
    low_indexes = _pivot_indexes(frame["low"], window=pivot_window, kind="low")
    candidates: list[_Candidate] = []

    lookback_pivots = int(config.get("pivot_lookback", 120))
    minimum_index = max(0, len(frame) - lookback_pivots)
    for kind, indexes, column in (("high", high_indexes, "high"), ("low", low_indexes, "low")):
        for index in indexes:
            if index < minimum_index:
                continue
            price = float(frame.iloc[index][column])
            candidates.append(_Candidate(price, "确认分形高点" if kind == "high" else "确认分形低点", 1.0))
            for method in _indicator_confirmations(frame, index, kind):
                candidates.append(_Candidate(price, method, 1.25))

    current_row = frame.iloc[-1]
    for window in (5, 10, 20, 30, 60):
        value = _number(current_row.get(f"ma{window}"))
        if value:
            candidates.append(_Candidate(value, f"MA{window}", 0.75 if window < 20 else 1.0))
    for column, method in (("boll_lower", "布林下轨"), ("boll_upper", "布林上轨")):
        value = _number(current_row.get(column))
        if value:
            candidates.append(_Candidate(value, method, 0.9))
    for multiple in (1.0, 2.0):
        candidates.append(_Candidate(current - atr * multiple, f"ATR-{multiple:g}", 0.7))
        candidates.append(_Candidate(current + atr * multiple, f"ATR+{multiple:g}", 0.7))

    for window in (20, 55, 120):
        sample = frame.tail(min(window, len(frame)))
        candidates.append(_Candidate(float(sample["low"].min()), f"{window}日区间下沿", 1.0))
        candidates.append(_Candidate(float(sample["high"].max()), f"{window}日区间上沿", 1.0))

    sample = frame.tail(min(120, len(frame)))
    swing_low = float(sample["low"].min())
    swing_high = float(sample["high"].max())
    width = swing_high - swing_low
    if width > 0:
        for ratio in (0.236, 0.382, 0.5, 0.618, 0.786):
            candidates.append(_Candidate(swing_high - width * ratio, f"Fibonacci {ratio:.3f}", 0.65))

    profile = _volume_profile(
        frame,
        int(config.get("volume_profile_window", 120)),
        int(config.get("volume_profile_bins", 32)),
    )
    if profile:
        candidates.extend(
            [
                _Candidate(profile["peak"], "成交密集峰估算", 1.25),
                _Candidate(profile["cost15"], "COST15估算", 0.65),
                _Candidate(profile["cost50"], "COST50估算", 1.0),
                _Candidate(profile["cost85"], "COST85估算", 0.65),
            ]
        )

    zone = _chan_zone_approx(
        frame,
        int(config.get("chan_segments", 3)),
        int(config.get("chan_segment_bars", 18)),
    )
    if zone:
        candidates.extend(
            [
                _Candidate(zone["lower"], "缠论重叠区下沿近似", 1.0),
                _Candidate(zone["middle"], "缠论重叠区中值近似", 0.75),
                _Candidate(zone["upper"], "缠论重叠区上沿近似", 1.0),
            ]
        )

    trend_lines = [
        item
        for item in (
            _trend_line(frame, low_indexes, "low", "支撑趋势线"),
            _trend_line(frame, high_indexes, "high", "压力趋势线"),
        )
        if item is not None
    ]
    for line in trend_lines:
        candidates.append(_Candidate(float(line["projected_price"]), line["label"], 1.0))

    levels = _cluster(candidates, current=current, tolerance=tolerance)
    supports = sorted((item for item in levels if item["price"] <= current), key=lambda item: item["price"], reverse=True)
    resistances = sorted((item for item in levels if item["price"] > current), key=lambda item: item["price"])
    return {
        "qualified": True,
        "current_price": round(current, 6),
        "atr14": round(float(atr), 6),
        "cluster_tolerance": round(tolerance, 6),
        "levels": levels,
        "nearest_support": supports[0] if supports else None,
        "nearest_resistance": resistances[0] if resistances else None,
        "support_levels": supports[:6],
        "resistance_levels": resistances[:6],
        "trend_lines": trend_lines,
        "volume_profile_approx": profile,
        "chan_zone_approx": zone,
        "semantics": {
            "oscillator_levels": "MACD/KDJ/RSI only confirm historical price pivots; oscillator values are never converted directly to prices.",
            "chan": "chan_zone_approx is a range-overlap approximation, not a complete Chan-theory implementation.",
            "volume_profile": "ETF volume profile is a traded-cost approximation, not shareholder chip ownership.",
        },
    }
