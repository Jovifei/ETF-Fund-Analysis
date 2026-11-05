"""Range / volume Wyckoff phase proxy for ETF OHLCV (honest proxy, not true flow).

Algorithm sketch
----------------
1. Define a local range from recent confirmed swing high/low (reuse Dow pivots)
   or falling back to rolling N-day high/low (N≈20), using only bars ≤ as_of.
2. Locate close within range → position in [0, 1].
3. Volume heuristics vs trailing median:
   - dry-up near range low + spring failure → accumulation bias
   - climax / wide-spread up into resistance → distribution bias
   - breakout with expansion → markup / markdown
4. Map to phase enum + score [-1, 1] + confidence.
5. Always attach evidence; never claim “smart money” — ETF share volume only.

Stub only; no live computation yet.
"""

from __future__ import annotations

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
    """Return (wyckoff_phase, score, confidence, evidence). Stub → unknown."""
    _ = (opens, highs, lows, closes, volumes, as_of_index, lag_n, range_lookback)
    return (
        "unknown",
        0.0,
        0.0,
        [{"kind": "note", "text": "wyckoff_proxy stub — OHLCV proxy not computed", "bar_index": None}],
    )
