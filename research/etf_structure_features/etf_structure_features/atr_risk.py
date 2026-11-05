"""Wilder ATR(14) + percent + risk bucket. Align with price_structure wilder_14_from_ohlc."""

from __future__ import annotations

from typing import Any

# Fixed starter bands on atr_pct; Phase A may switch to cross-sectional quantiles later.
ATR_PCT_BANDS = {
    "low": (0.0, 0.008),
    "mid": (0.008, 0.015),
    "high": (0.015, 0.025),
    "extreme": (0.025, float("inf")),
}


def wilder_atr14(highs: list[float], lows: list[float], closes: list[float]) -> float | None:
    """Stub: return None until ported from price_structure._atr_series."""
    _ = (highs, lows, closes)
    return None


def atr_features(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    *,
    as_of_index: int,
) -> tuple[float | None, float | None, str, list[dict[str, Any]]]:
    """Return (atr14, atr_pct, atr_risk_bucket, evidence)."""
    _ = as_of_index
    atr = wilder_atr14(highs, lows, closes)
    if atr is None or not closes:
        return None, None, "unknown", [{"kind": "atr", "text": "atr stub — not computed", "bar_index": None}]
    close = closes[-1]
    atr_pct = (atr / close) if close else None
    bucket = "unknown"
    if atr_pct is not None:
        for name, (lo, hi) in ATR_PCT_BANDS.items():
            if lo <= atr_pct < hi:
                bucket = name
                break
    return atr, atr_pct, bucket, [{"kind": "atr", "text": f"atr14={atr} atr_pct={atr_pct} → {bucket}", "bar_index": as_of_index}]
