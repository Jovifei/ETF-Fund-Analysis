"""Wilder ATR(14) + atr_pct + atr_risk_bucket. atr_pct = atr14/close (or slim price)."""

from __future__ import annotations

from typing import Any

# atr_risk_bucket_rule_version
RISK_BUCKET_RULE_VERSION = "atr_pct_fixed_v1"
# atr_pct = atr14 / price
# low: < 1.0%; mid: [1.0%, 2.0%); high: [2.0%, 3.5%); extreme: >= 3.5%; unknown: missing
BANDS = [
    ("low", 0.0, 0.010),
    ("mid", 0.010, 0.020),
    ("high", 0.020, 0.035),
    ("extreme", 0.035, float("inf")),
]


def wilder_atr14(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    n = len(closes)
    if n < period + 1 or not (len(highs) == len(lows) == n):
        return None
    trs: list[float] = []
    for i in range(1, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return float(atr)


def bucket_from_pct(atr_pct: float | None) -> str:
    if atr_pct is None:
        return "unknown"
    for name, lo, hi in BANDS:
        if lo <= atr_pct < hi:
            return name
    return "unknown"


def atr_features(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    *,
    as_of_index: int,
    atr14_override: float | None = None,
    price_override: float | None = None,
) -> tuple[float | None, float | None, str, list[dict[str, Any]]]:
    _ = as_of_index
    atr = atr14_override if atr14_override is not None else wilder_atr14(highs, lows, closes)
    price = price_override if price_override is not None else (closes[-1] if closes else None)
    atr_pct = (atr / price) if (atr is not None and price) else None
    bucket = bucket_from_pct(atr_pct)
    ev = [{
        "kind": "atr",
        "text": f"atr14={atr} atr_pct={atr_pct} bucket={bucket} rule={RISK_BUCKET_RULE_VERSION}",
        "bar_index": as_of_index if closes else None,
    }]
    return atr, atr_pct, bucket, ev
