"""Confirmed-pivot Dow proxy (lag_n, no lookahead)."""

from __future__ import annotations

from typing import Any

DEFAULT_LAG_N = 2
DEFAULT_SWING_K = 2


def _swings(values: list[float], *, is_high: bool, k: int) -> list[int]:
    out: list[int] = []
    n = len(values)
    for i in range(k, n - k):
        w = values[i - k : i + k + 1]
        v = values[i]
        if is_high and v == max(w) and w.count(v) == 1:
            out.append(i)
        if (not is_high) and v == min(w) and w.count(v) == 1:
            out.append(i)
    return out


def confirmed_pivots(
    highs: list[float],
    lows: list[float],
    *,
    as_of_index: int,
    lag_n: int = DEFAULT_LAG_N,
    swing_k: int = DEFAULT_SWING_K,
) -> list[dict[str, Any]]:
    highs = highs[: as_of_index + 1]
    lows = lows[: as_of_index + 1]
    last_usable = len(highs) - 1 - lag_n
    pivots: list[dict[str, Any]] = []
    for series, side, is_high in ((highs, "high", True), (lows, "low", False)):
        for i in _swings(series, is_high=is_high, k=swing_k):
            confirmed_at = i + swing_k
            if confirmed_at <= last_usable:
                pivots.append({"side": side, "index": i, "price": series[i], "confirmed_index": confirmed_at})
    pivots.sort(key=lambda p: (p["confirmed_index"], p["side"]))
    return pivots


def dow_phase_from_pivots(
    pivots: list[dict[str, Any]],
) -> tuple[str, float, float, list[dict[str, Any]]]:
    highs_p = [p for p in pivots if p["side"] == "high"]
    lows_p = [p for p in pivots if p["side"] == "low"]
    evidence: list[dict[str, Any]] = []
    if len(highs_p) >= 2:
        evidence.append({"kind": "dow_pivot", "text": f"swing highs {highs_p[-2]['price']:.4f}->{highs_p[-1]['price']:.4f}", "bar_index": highs_p[-1]["index"]})
    if len(lows_p) >= 2:
        evidence.append({"kind": "dow_pivot", "text": f"swing lows {lows_p[-2]['price']:.4f}->{lows_p[-1]['price']:.4f}", "bar_index": lows_p[-1]["index"]})
    if len(highs_p) < 2 or len(lows_p) < 2:
        evidence.append({"kind": "note", "text": "insufficient confirmed pivots", "bar_index": None})
        return "unknown", 0.0, 0.2, evidence

    h1, h2 = highs_p[-2], highs_p[-1]
    l1, l2 = lows_p[-2], lows_p[-1]
    hh, hl = h2["price"] > h1["price"], l2["price"] > l1["price"]
    lh, ll = h2["price"] < h1["price"], l2["price"] < l1["price"]

    if hh and hl:
        return "uptrend", 0.7, 0.65, evidence
    if lh and ll:
        return "downtrend", -0.7, 0.65, evidence
    if hh and ll:
        return "sideways", 0.1, 0.45, evidence
    if lh and hl:
        # Contracting swings. Comparing the last swing high with the last
        # swing low cannot separate the two cases (a swing high sits above
        # the swing low in any sane series), so use the drift of the
        # swing-range midpoint: a contracting range whose centre rises is a
        # correction inside an uptrend; a falling centre is a rally inside
        # a downtrend; no drift is sideways.
        mid_prev = (h1["price"] + l1["price"]) / 2
        mid_last = (h2["price"] + l2["price"]) / 2
        if mid_last > mid_prev:
            return "correction_in_uptrend", 0.25, 0.5, evidence
        if mid_last < mid_prev:
            return "rally_in_downtrend", -0.25, 0.5, evidence
        return "sideways", 0.0, 0.4, evidence
    return "sideways", 0.0, 0.4, evidence
