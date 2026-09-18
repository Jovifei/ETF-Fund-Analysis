"""Display-only entry/exit and theme-relative views.

These helpers never change five-grade assignment, indicator formulas, or
forecast snapshots.  They project already-computed support/resistance zones and
confirmed 5-day returns so a human can compare one ETF against its theme peers.

Borrowed design (native reimplementation, no vendor import):
- zhangsensen/etf-rotation-strategy: rank inside a sleeve, do not invent a
  second action from the rank.
- BatuhanUsluel / SUPPORT_RESISTANCE_SEMANTICS: use clustered price zones, never
  convert MACD/KDJ/RSI into a price.
"""
from __future__ import annotations

from math import isfinite
from typing import Any


def _finite(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _zone_from_level(level: object) -> dict[str, float] | None:
    if not isinstance(level, dict):
        price = _finite(level)
        if price is None or price <= 0:
            return None
        return {"low": price, "high": price, "mid": price}
    low = _finite(level.get("zone_low"))
    high = _finite(level.get("zone_high"))
    mid = _finite(level.get("price"))
    if mid is None or mid <= 0:
        return None
    if low is None or low <= 0:
        low = mid
    if high is None or high <= 0:
        high = mid
    if high < low:
        return None
    return {"low": round(low, 6), "high": round(high, 6), "mid": round(mid, 6)}


def entry_exit_reference(support_resistance: object, current_price: object = None) -> dict[str, Any]:
    """Nearest clustered support/resistance as a research band, not a trade ticket."""

    payload = support_resistance if isinstance(support_resistance, dict) else {}
    support = _zone_from_level(payload.get("nearest_support"))
    resistance = _zone_from_level(payload.get("nearest_resistance"))
    price = _finite(current_price if current_price is not None else payload.get("current_price"))
    if price is not None and price <= 0:
        price = None
    position = "unknown"
    if price is not None and support is not None and price < support["low"]:
        position = "below_support"
    elif price is not None and resistance is not None and price > resistance["high"]:
        position = "above_resistance"
    elif price is not None and (support is not None or resistance is not None):
        position = "inside_band"
    return {
        "support_zone": support,
        "resistance_zone": resistance,
        "current_price": price,
        "position": position,
        "basis": "clustered_price_zones_not_oscillator_conversion",
        "research_only": True,
        "actionable": False,
    }


def theme_relative_ranks(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Rank enabled rows inside theme_l1 by confirmed 5-day return.

    Missing or non-finite returns stay unranked.  The rank never overrides grade.
    """

    buckets: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        code = str(row.get("ts_code") or "")
        theme = str(row.get("theme_l1") or "").strip()
        ret = _finite(row.get("return_5d"))
        if not code or not theme or ret is None:
            continue
        buckets.setdefault(theme, []).append((code, ret))
    ranked: dict[str, dict[str, Any]] = {}
    for theme, members in buckets.items():
        ordered = sorted(members, key=lambda item: (-item[1], item[0]))
        count = len(ordered)
        for index, (code, ret) in enumerate(ordered, start=1):
            ranked[code] = {
                "theme_l1": theme,
                "peer_count": count,
                "rank": index,
                "return_5d": ret,
                "label": f"{theme} {index}/{count}",
                "basis": "confirmed_5d_return_inside_theme_not_a_second_grade",
                "research_only": True,
                "actionable": False,
            }
    return ranked
