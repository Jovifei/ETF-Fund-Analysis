"""Afternoon sector add/reduce observation helpers (research-only).

Aggregates decision-board rows by theme_l1 into an explicit observation layer for
14:30 / 14:45 human review.  Never overrides five-grade assignment, never flips
actionable=true, and never claims calibrated forecasts.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

ADD_GRADES = frozenset({"可加仓", "可入场", "可试错"})
REDUCE_GRADES = frozenset({"减仓"})
NEUTRAL_GRADES = frozenset({"观望", "数据异常"})

OBSERVATION_ADD = "偏强观察"
OBSERVATION_REDUCE = "偏弱观察"
OBSERVATION_NEUTRAL = "中性"

_BASIS = (
    "theme_grade_density_plus_confirmed_5d_return_observation_only;"
    "does_not_override_five_grade_or_forecast_calibration"
)


def _finite(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _observation(add_count: int, reduce_count: int, mean_return_5d: float | None) -> str:
    """Map grade density + optional return into a research observation label."""

    if add_count == 0 and reduce_count == 0:
        return OBSERVATION_NEUTRAL
    if add_count > reduce_count and (mean_return_5d is None or mean_return_5d >= 0):
        return OBSERVATION_ADD
    if reduce_count > add_count and (mean_return_5d is None or mean_return_5d <= 0):
        return OBSERVATION_REDUCE
    if add_count > reduce_count:
        return OBSERVATION_ADD
    if reduce_count > add_count:
        return OBSERVATION_REDUCE
    if mean_return_5d is not None and mean_return_5d > 0:
        return OBSERVATION_ADD
    if mean_return_5d is not None and mean_return_5d < 0:
        return OBSERVATION_REDUCE
    return OBSERVATION_NEUTRAL


def _strength_score(
    observation: str,
    add_count: int,
    reduce_count: int,
    member_count: int,
    mean_return_5d: float | None,
) -> float:
    """Display ranking only; higher means stronger add-side observation."""

    density = (add_count - reduce_count) / member_count if member_count else 0.0
    ret = 0.0 if mean_return_5d is None else max(-0.2, min(0.2, mean_return_5d))
    bias = {"偏强观察": 1.0, "偏弱观察": -1.0, "中性": 0.0}[observation]
    return round(100.0 * (0.55 * bias + 0.30 * density + 0.15 * (ret / 0.2)), 2)


def build_sector_timing_observation(
    rows: list[dict[str, Any]] | None,
    *,
    slot_hint: str | None = None,
) -> dict[str, Any]:
    """Build a research-only sector timing block from decision-board rows.

    Parameters
    ----------
    rows:
        Decision-board instrument rows.  Expected keys: theme_l1, grade,
        return_5d, ts_code (optional for member lists).
    slot_hint:
        Optional afternoon slot label such as \"14:30\" or \"14:45\".
    """

    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        theme = str(row.get("theme_l1") or "").strip()
        if not theme:
            continue
        buckets.setdefault(theme, []).append(row)

    themes: list[dict[str, Any]] = []
    for theme, members in buckets.items():
        grades = [str(member.get("grade") or "") for member in members]
        add_count = sum(1 for grade in grades if grade in ADD_GRADES)
        reduce_count = sum(1 for grade in grades if grade in REDUCE_GRADES)
        watch_count = sum(1 for grade in grades if grade in NEUTRAL_GRADES)
        returns = [_finite(member.get("return_5d")) for member in members]
        finite_returns = [value for value in returns if value is not None]
        mean_return_5d = _mean(finite_returns)
        observation = _observation(add_count, reduce_count, mean_return_5d)
        member_count = len(members)
        themes.append(
            {
                "theme_l1": theme,
                "observation": observation,
                "member_count": member_count,
                "add_grade_count": add_count,
                "reduce_grade_count": reduce_count,
                "watch_grade_count": watch_count,
                "mean_return_5d": mean_return_5d,
                "strength_score": _strength_score(
                    observation, add_count, reduce_count, member_count, mean_return_5d
                ),
                "sample_codes": sorted(
                    {
                        str(member.get("ts_code") or "").strip().upper()
                        for member in members
                        if str(member.get("ts_code") or "").strip()
                    }
                )[:8],
                "research_only": True,
                "actionable": False,
            }
        )

    themes.sort(key=lambda item: (-item["strength_score"], item["theme_l1"]))
    for rank, item in enumerate(themes, start=1):
        item["rank"] = rank

    add_themes = [item["theme_l1"] for item in themes if item["observation"] == OBSERVATION_ADD]
    reduce_themes = [item["theme_l1"] for item in themes if item["observation"] == OBSERVATION_REDUCE]

    return {
        "version": "sector-timing-observation-v1",
        "slot_hint": slot_hint,
        "intended_slots": ["14:30", "14:45"],
        "research_only": True,
        "actionable": False,
        "calibration_status": "not_calibrated",
        "basis": _BASIS,
        "summary": {
            "theme_count": len(themes),
            "add_observation_themes": add_themes,
            "reduce_observation_themes": reduce_themes,
            "neutral_observation_themes": [
                item["theme_l1"] for item in themes if item["observation"] == OBSERVATION_NEUTRAL
            ],
        },
        "themes": themes,
    }


def empty_sector_timing_observation(*, slot_hint: str | None = None) -> dict[str, Any]:
    """Empty but schema-stable sector timing block for missing snapshots."""

    payload = build_sector_timing_observation([], slot_hint=slot_hint)
    return payload
