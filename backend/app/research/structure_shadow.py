"""structure_shadow_v1 — Phase B1 parallel (bypass) structure signal.

Applies the frozen B0 soft_c_strict overlay (verdict WEAK_PASS_KEEP_FROZEN in
docs/handoffs/HANDOFF_STRUCTURE_V1.md) to a row's structure_v1 block and
reports a ternary shadow signal next to the live five-档 grade.

Hard boundaries:
- Pure function of the structure_v1 block; never calls assign_grade and its
  result is never fed back into the live grade, CONFIG_HASH, or strategy.json.
- Weights are the frozen research proposal, NOT a live promotion: B2 (live
  promote) still requires the Phase A parallel gate, holdout standing, and a
  separate explicit user approval.
- Missing/invalid structure → None (UI shows —), matching Phase A soft-fail.
"""

from __future__ import annotations

from typing import Any

SHADOW_VERSION = "structure_shadow_v1"
SHADOW_WEIGHTS_ID = "soft_c_strict_frozen_v1"

# Frozen soft_c_strict (B0 walk-forward selection; kept frozen, do not retune).
W_WYCKOFF = 0.40
W_DOW = 0.60
CONF_FLOOR = 0.45
BUY_THRESH = 0.30
FLAT_BAND = 0.12
ATR_SCALE = {"low": 1.0, "mid": 0.9, "high": 0.4, "extreme": 0.0, "unknown": 0.4}

_POSITIVE_LIVE = {"可加仓", "可入场", "可试探"}
_NEGATIVE_LIVE = {"减仓"}
_NEUTRAL_LIVE = {"观望"}

_SIGNAL_BY_POSITION = {
    1.0: "偏多",
    0.5: "弱偏多",
    0.0: "中性",
    -0.5: "弱偏空",
    -1.0: "偏空",
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _position_for(score: float) -> float:
    if score >= BUY_THRESH:
        return 1.0
    if score <= -BUY_THRESH:
        return -1.0
    if abs(score) < FLAT_BAND:
        return 0.0
    return 0.5 if score > 0 else -0.5


def _agrees(position: float, live_grade: str | None) -> bool | None:
    if live_grade in _POSITIVE_LIVE:
        return position > 0
    if live_grade in _NEGATIVE_LIVE:
        return position < 0
    if live_grade in _NEUTRAL_LIVE:
        return position == 0
    return None


def compute_structure_shadow(
    structure_v1: Any, *, live_grade: str | None = None
) -> dict[str, Any] | None:
    """Frozen soft_c overlay on one structure_v1 block. Soft-fail → None."""
    if not isinstance(structure_v1, dict):
        return None
    wy_score = _finite(structure_v1.get("wyckoff_score"))
    wy_conf = _finite(structure_v1.get("wyckoff_confidence"))
    dow_score = _finite(structure_v1.get("dow_score"))
    dow_conf = _finite(structure_v1.get("dow_confidence"))
    if None in (wy_score, wy_conf, dow_score, dow_conf):
        return None
    assert wy_score is not None and wy_conf is not None
    assert dow_score is not None and dow_conf is not None

    raw = (W_WYCKOFF * wy_score * wy_conf + W_DOW * dow_score * dow_conf) / (
        W_WYCKOFF + W_DOW
    )
    if (wy_conf + dow_conf) / 2.0 < CONF_FLOOR:
        raw = 0.0
    bucket = str(structure_v1.get("atr_risk_bucket") or "unknown")
    scale = ATR_SCALE.get(bucket, ATR_SCALE["unknown"])
    score = max(-1.0, min(1.0, raw * scale))
    position = _position_for(score)
    return {
        "version": SHADOW_VERSION,
        "weights_id": SHADOW_WEIGHTS_ID,
        "score": round(score, 4),
        "position": position,
        "signal": _SIGNAL_BY_POSITION[position],
        "atr_scale": scale,
        "live_grade": live_grade,
        "agrees_with_live": _agrees(position, live_grade),
        "changes_live_grade": False,
        "research_only": True,
    }
