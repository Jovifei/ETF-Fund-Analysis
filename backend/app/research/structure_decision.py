"""structure_decision_v1 — owner-directed participation of the structure
factors (Wyckoff / Dow / ATR) in the live five-grade decision.

History: Phase B1 kept the frozen soft_c score as a display-only shadow
because the B2 holdout gate had not passed. On 2026-11-07 the owner
explicitly instructed that the three factors join the decision, with the
proportion (weight) to be fixed later. This module implements that
participation as a bounded adjustment of the base grade from assign_grade:

- blend: adjusted = base_rank + weight * shadow_score * 2 (rounded);
- at most max_shift (1) notch of movement;
- structure can neither create 可加仓 (top grade) nor 减仓 (bottom grade);
- hard-rule grades 减仓 / 数据异常 are never overridden;
- missing structure/shadow, disabled config, or weight 0 -> no change.

research_only / actionable=false / not_calibrated are unchanged. The
frozen soft_c weights themselves are NOT retuned here; the only knob is
the participation weight in config/strategy.json
(signal_grade.structure_decision.weight). The weight is a living
parameter, re-fit as daily outcomes accumulate; it was set to 0.4167 on
2026-11-07 (grade shifts only when |score| >= 0.60 — see strategy.json
note and CONSOLIDATION_20261107.md section 14 for the derivation).
"""

from __future__ import annotations

import math
from typing import Any

DECISION_VERSION = "structure-decision-v1"

GRADE_RANK = {"减仓": 0, "观望": 1, "可试探": 2, "可入场": 3, "可加仓": 4}
RANK_GRADE = {rank: grade for grade, rank in GRADE_RANK.items()}
_HARD_GRADES = {"减仓", "数据异常"}
_TOP = 4
_BOTTOM = 0


def apply_structure_decision(
    base_grade: str | None,
    shadow: dict[str, Any] | None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the structure-adjusted grade detail for one row.

    ``shadow`` is the compute_structure_shadow result (frozen soft_c
    score). The returned dict always carries base/final grades so callers
    can display the adjustment transparently.
    """
    cfg = cfg or {}
    enabled = bool(cfg.get("enabled", False))
    raw_weight = cfg.get("weight", 0.0)
    if isinstance(raw_weight, bool) or raw_weight is None:
        weight = 0.0
    else:
        try:
            f = float(raw_weight)
            weight = f if math.isfinite(f) else 0.0
        except (TypeError, ValueError, OverflowError):
            weight = 0.0
    weight = min(1.0, max(0.0, weight))

    raw_shift = cfg.get("max_shift", 1)
    if isinstance(raw_shift, bool):
        max_shift = 1
    else:
        try:
            max_shift = int(raw_shift)
        except (TypeError, ValueError):
            max_shift = 1
    max_shift = max(0, max_shift)

    detail: dict[str, Any] = {
        "version": DECISION_VERSION,
        "enabled": enabled,
        "weight": weight,
        "applied": False,
        "base_grade": base_grade,
        "final_grade": base_grade,
        "score": None,
        "signal": None,
        "reason": "",
    }
    if not enabled:
        detail["reason"] = "disabled"
        return detail
    if base_grade in _HARD_GRADES or base_grade not in GRADE_RANK:
        detail["reason"] = "hard_grade_not_adjusted"
        return detail
    if not isinstance(shadow, dict):
        detail["reason"] = "no_structure"
        return detail
    raw_score = shadow.get("score")
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        detail["reason"] = "no_structure"
        return detail
    try:
        f_score = float(raw_score)
        if not math.isfinite(f_score):
            detail["reason"] = "no_structure"
            return detail
    except (TypeError, ValueError, OverflowError):
        detail["reason"] = "no_structure"
        return detail

    score = f_score
    detail["score"] = shadow["score"]
    detail["signal"] = shadow.get("signal")
    if weight <= 0:
        detail["reason"] = "zero_weight"
        return detail
    base_rank = GRADE_RANK[base_grade]
    target = math.floor(base_rank + weight * score * 2.0 + 0.5)
    shift = max(-max_shift, min(max_shift, target - base_rank))
    candidate_rank = base_rank + shift
    final_rank = max(_BOTTOM, min(_TOP, candidate_rank))
    if final_rank >= _TOP and base_rank < _TOP:
        final_rank = _TOP - 1
    if final_rank <= _BOTTOM and base_rank > _BOTTOM:
        final_rank = _BOTTOM + 1
    final_grade = RANK_GRADE[final_rank]
    detail["final_grade"] = final_grade
    detail["applied"] = final_grade != base_grade
    detail["reason"] = "adjusted" if detail["applied"] else "within_band"
    return detail
