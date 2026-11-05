"""Confirmed-pivot Dow trend proxy (no lookahead).

Algorithm sketch
----------------
1. Detect swing highs/lows with symmetric window `k` on bars[0 : t+1] only.
2. A swing at index i is **confirmed** only when i <= t - lag_n (default lag_n=2).
   Bars in (t - lag_n, t] may form tentative swings but must not label the phase yet.
3. Phase from the last two confirmed swings of each type (HH/HL vs LH/LL):
   - HH + HL → uptrend
   - LH + LL → downtrend
   - HL then LH inside prior uptrend → correction_in_uptrend
   - LH then HL inside prior downtrend → rally_in_downtrend
   - otherwise sideways / unknown
4. Score in [-1, 1] from signed pivot sequence strength; confidence from
   pivot spacing consistency and sample count.

This module is a stub: functions return structured placeholders until wired to bars.
"""

from __future__ import annotations

from typing import Any

DEFAULT_LAG_N = 2
DEFAULT_SWING_K = 2


def confirmed_pivots(
    highs: list[float],
    lows: list[float],
    *,
    as_of_index: int,
    lag_n: int = DEFAULT_LAG_N,
    swing_k: int = DEFAULT_SWING_K,
) -> list[dict[str, Any]]:
    """Return confirmed pivots with index <= as_of_index - lag_n. Stub → []."""
    _ = (highs, lows, as_of_index, lag_n, swing_k)
    return []


def dow_phase_from_pivots(
    pivots: list[dict[str, Any]],
) -> tuple[str, float, float, list[dict[str, Any]]]:
    """Return (dow_phase, dow_score, dow_confidence, evidence). Stub → unknown."""
    _ = pivots
    return "unknown", 0.0, 0.0, [{"kind": "note", "text": "dow_proxy stub — not computed", "bar_index": None}]
