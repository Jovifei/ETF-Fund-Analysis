"""Range/volume Wyckoff proxy from OHLCV (not true flow)."""

from __future__ import annotations

from statistics import median
from typing import Any


def wyckoff_from_ohlcv(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    *,
    as_of_index: int,
    lag_n: int = 2,
    range_lookback: int = 20,
) -> tuple[str, float, float, list[dict[str, Any]]]:
    _ = (opens, lag_n)
    n = as_of_index + 1
    highs, lows, closes, volumes = highs[:n], lows[:n], closes[:n], volumes[:n]
    if n < max(range_lookback, 6) or not volumes:
        return "unknown", 0.0, 0.0, [{"kind": "note", "text": "insufficient bars for wyckoff proxy", "bar_index": None}]

    w = slice(-range_lookback, None)
    hi, lo = max(highs[w]), min(lows[w])
    rng = hi - lo
    close = closes[-1]
    pos = 0.5 if rng <= 0 else (close - lo) / rng
    vol_med = median(volumes[w]) or 1.0
    vol_ratio = volumes[-1] / vol_med
    ret5 = (closes[-1] / closes[-6] - 1.0) if n >= 6 and closes[-6] else 0.0
    evidence = [
        {"kind": "wyckoff_range", "text": f"20d pos={pos:.2f} range={rng:.4f}", "bar_index": as_of_index},
        {"kind": "wyckoff_volume", "text": f"vol_ratio={vol_ratio:.2f} ret5={ret5:.3%}", "bar_index": as_of_index},
    ]

    if pos <= 0.35 and vol_ratio < 0.95 and ret5 <= 0.01:
        return "accumulation", 0.45, min(0.75, 0.4 + (0.35 - pos)), evidence
    if pos >= 0.65 and vol_ratio < 0.95 and ret5 >= -0.01:
        return "distribution", -0.45, min(0.75, 0.4 + (pos - 0.65)), evidence
    if ret5 > 0.025 and vol_ratio >= 1.15 and pos >= 0.55:
        return "markup", 0.7, min(0.8, 0.5 + ret5), evidence
    if ret5 < -0.025 and vol_ratio >= 1.15 and pos <= 0.45:
        return "markdown", -0.7, min(0.8, 0.5 - ret5), evidence
    if 0.35 < pos < 0.65 and abs(ret5) < 0.02:
        return "range", 0.0, 0.4, evidence
    if ret5 > 0.01 and pos > 0.5:
        return "markup", 0.35, 0.35, evidence
    if ret5 < -0.01 and pos < 0.5:
        return "markdown", -0.35, 0.35, evidence
    if pos < 0.4:
        return "accumulation", 0.25, 0.3, evidence
    if pos > 0.6:
        return "distribution", -0.25, 0.3, evidence
    return "range", 0.0, 0.3, evidence
