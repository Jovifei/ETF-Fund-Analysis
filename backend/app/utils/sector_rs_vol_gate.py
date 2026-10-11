"""Research-only 20d relative strength + simple volatility gate.

Pilot stub for the next sector-timing factor slice.  Does NOT change five-grade
assignment, does NOT set actionable=true, and does NOT claim calibration.
"""
from __future__ import annotations

from math import isfinite, sqrt
from typing import Any


def _finite(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def relative_strength_20d(return_20d: object, peer_returns_20d: list[object] | None) -> dict[str, Any]:
    """Rank one theme/instrument 20d return inside a peer set (research display)."""

    target = _finite(return_20d)
    peers = [value for value in (_finite(item) for item in (peer_returns_20d or [])) if value is not None]
    if target is None or not peers:
        return {
            "return_20d": target,
            "peer_count": len(peers),
            "rank": None,
            "percentile": None,
            "research_only": True,
            "actionable": False,
            "note": "insufficient_20d_peer_sample",
        }
    better = sum(1 for value in peers if value > target)
    rank = better + 1
    percentile = round(100.0 * (1.0 - (rank - 1) / len(peers)), 2)
    return {
        "return_20d": target,
        "peer_count": len(peers),
        "rank": rank,
        "percentile": percentile,
        "research_only": True,
        "actionable": False,
        "note": "20d_relative_strength_observation_only",
    }


def simple_vol_gate(returns: list[object] | None, *, high_vol_percentile: float = 0.8) -> dict[str, Any]:
    """Flag high realized vol from a short return sample (display gate only)."""

    series = [value for value in (_finite(item) for item in (returns or [])) if value is not None]
    if len(series) < 5:
        return {
            "stdev": None,
            "gate": "unavailable",
            "high_vol": False,
            "research_only": True,
            "actionable": False,
            "note": "need_at_least_5_returns",
        }
    mean = sum(series) / len(series)
    var = sum((value - mean) ** 2 for value in series) / (len(series) - 1)
    stdev = sqrt(var)
    elevated = stdev >= 0.03
    return {
        "stdev": round(stdev, 6),
        "gate": "elevated_vol" if elevated else "normal_vol",
        "high_vol": elevated,
        "threshold_hint": 0.03,
        "high_vol_percentile_config": high_vol_percentile,
        "research_only": True,
        "actionable": False,
        "note": "simple_sample_stdev_gate_not_a_grade_override",
    }


def annotate_theme_observation(theme: dict[str, Any], *, peer_returns_20d: list[object] | None = None) -> dict[str, Any]:
    """Attach RS/vol research tags onto a sector_timing theme dict (copy)."""

    out = dict(theme)
    returns = theme.get("member_returns") or theme.get("returns_sample") or []
    out["rs_20d"] = relative_strength_20d(theme.get("mean_return_20d", theme.get("mean_return_5d")), peer_returns_20d)
    out["vol_gate"] = simple_vol_gate(returns if isinstance(returns, list) else [])
    out["research_only"] = True
    out["actionable"] = False
    return out
