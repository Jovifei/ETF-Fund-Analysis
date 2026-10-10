"""Afternoon sector add/reduce observation helpers (research-only).

Aggregates decision-board rows by theme_l1 into an explicit observation layer for
14:30 / 14:45 human review.  Optionally attaches AKShare SectorSnapshot market
breadth/pct_change as corroboration via taxonomy theme_l1 mapping — never invents
missing market rows, never overrides five-grade assignment, never flips
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
    "optional_sectorsnapshot_corroboration_via_taxonomy;"
    "does_not_override_five_grade_or_forecast_calibration"
)

# Bot / afternoon-routine field path (stable contract for digests).
DIGEST_FIELD_PATH = "sector_timing.digest"
SUMMARY_FIELD_PATH = "sector_timing.summary"
API_READ_PATH = "GET /api/decision-board → payload.sector_timing"


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
    bias = {OBSERVATION_ADD: 1.0, OBSERVATION_REDUCE: -1.0, OBSERVATION_NEUTRAL: 0.0}[observation]
    return round(100.0 * (0.55 * bias + 0.30 * density + 0.15 * (ret / 0.2)), 2)


def map_sector_name_to_theme_l1(
    sector_name: str,
    taxonomy: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Map an AKShare/industry sector name onto theme_l1 via config taxonomy.

    Uses exact keys first, then keyword_rules.  Returns None when no honest match
    exists — callers must not invent a theme.
    """

    name = str(sector_name or "").strip()
    if not name or not isinstance(taxonomy, dict):
        return None

    for exact, value in (taxonomy.get("exact") or {}).items():
        if not isinstance(value, dict):
            continue
        exact_text = str(exact or "").strip()
        if not exact_text:
            continue
        if exact_text == name or exact_text in name or name in exact_text:
            theme = str(value.get("theme_l1") or "").strip()
            if theme:
                return {
                    "theme_l1": theme,
                    "match_kind": "exact",
                    "matched_token": exact_text,
                    "confidence": "high",
                }

    lowered = name.lower()
    for rule in taxonomy.get("keyword_rules") or []:
        if not isinstance(rule, dict):
            continue
        keywords = rule.get("keywords") or []
        token = next(
            (
                str(item).strip()
                for item in keywords
                if str(item).strip() and str(item).strip().lower() in lowered
            ),
            None,
        )
        if not token:
            continue
        theme = str(rule.get("theme_l1") or "").strip()
        if theme:
            return {
                "theme_l1": theme,
                "match_kind": "keyword",
                "matched_token": token,
                "confidence": "medium",
            }
    return None


def _empty_corroboration() -> dict[str, Any]:
    return {
        "available": False,
        "matched_sectors": [],
        "mean_pct_change": None,
        "breadth_up": None,
        "breadth_down": None,
        "trade_date": None,
        "alignment": "unavailable",
        "research_only": True,
        "actionable": False,
        "note": "no_SectorSnapshot_match_for_theme; not invented",
    }


def _alignment(observation: str, mean_pct_change: float | None) -> str:
    if mean_pct_change is None:
        return "unavailable"
    if mean_pct_change > 0 and observation == OBSERVATION_ADD:
        return "supports_add"
    if mean_pct_change < 0 and observation == OBSERVATION_REDUCE:
        return "supports_reduce"
    if mean_pct_change > 0 and observation == OBSERVATION_REDUCE:
        return "mixed"
    if mean_pct_change < 0 and observation == OBSERVATION_ADD:
        return "mixed"
    if mean_pct_change == 0:
        return "mixed"
    return "mixed"


def aggregate_market_evidence_by_theme(
    market_evidence: list[dict[str, Any]] | None,
    taxonomy: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Group optional SectorSnapshot-like rows by mapped theme_l1.

    Each evidence row may include: sector_name, board_type, pct_change,
    up_count, down_count, flat_count, total_count, trade_date, source.
    Unmapped or empty names are skipped (no fake theme assignment).
    """

    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in market_evidence or []:
        if not isinstance(row, dict):
            continue
        sector_name = str(row.get("sector_name") or "").strip()
        if not sector_name:
            continue
        mapped = map_sector_name_to_theme_l1(sector_name, taxonomy)
        if not mapped:
            continue
        theme = mapped["theme_l1"]
        entry = {
            "sector_name": sector_name,
            "board_type": row.get("board_type"),
            "pct_change": _finite(row.get("pct_change")),
            "up_count": row.get("up_count"),
            "down_count": row.get("down_count"),
            "flat_count": row.get("flat_count"),
            "total_count": row.get("total_count"),
            "trade_date": row.get("trade_date"),
            "source": row.get("source"),
            "match_kind": mapped["match_kind"],
            "matched_token": mapped["matched_token"],
            "confidence": mapped["confidence"],
        }
        buckets.setdefault(theme, []).append(entry)

    by_theme: dict[str, dict[str, Any]] = {}
    for theme, members in buckets.items():
        pcts = [item["pct_change"] for item in members if item["pct_change"] is not None]
        ups = [int(item["up_count"]) for item in members if isinstance(item.get("up_count"), (int, float))]
        downs = [int(item["down_count"]) for item in members if isinstance(item.get("down_count"), (int, float))]
        dates = [str(item["trade_date"]) for item in members if item.get("trade_date")]
        by_theme[theme] = {
            "available": True,
            "matched_sectors": members,
            "mean_pct_change": _mean(pcts),
            "breadth_up": sum(ups) if ups else None,
            "breadth_down": sum(downs) if downs else None,
            "trade_date": max(dates) if dates else None,
            "research_only": True,
            "actionable": False,
            "note": "AKShare_SectorSnapshot_optional_corroboration_via_taxonomy",
        }
    return by_theme


def _attach_corroboration(
    observation: str,
    theme: str,
    by_theme: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    payload = dict(by_theme.get(theme) or _empty_corroboration())
    payload["alignment"] = _alignment(observation, payload.get("mean_pct_change"))
    payload["research_only"] = True
    payload["actionable"] = False
    return payload


def _build_digest(
    *,
    slot_hint: str | None,
    add_themes: list[str],
    reduce_themes: list[str],
    neutral_themes: list[str],
    themes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compact block for 14:30/14:45 Bot digests — read from decision-board API."""

    def _theme_line(theme_name: str) -> str:
        match = next((item for item in themes if item["theme_l1"] == theme_name), None)
        if not match:
            return theme_name
        corr = match.get("market_corroboration") or {}
        pct = corr.get("mean_pct_change")
        align = corr.get("alignment")
        if pct is None:
            return theme_name
        return f"{theme_name}(市{pct:+.2f}%/{align})"

    add_part = "、".join(_theme_line(name) for name in add_themes) or "无"
    reduce_part = "、".join(_theme_line(name) for name in reduce_themes) or "无"
    headline = (
        f"偏强观察: {add_part} | 偏弱观察: {reduce_part} | "
        f"研究向不可操作 · calibration=not_calibrated"
    )
    corroboration_available = sum(
        1 for item in themes if (item.get("market_corroboration") or {}).get("available")
    )
    return {
        "field_path": DIGEST_FIELD_PATH,
        "summary_field_path": SUMMARY_FIELD_PATH,
        "api_read_path": API_READ_PATH,
        "slot_hint": slot_hint,
        "intended_slots": ["14:30", "14:45"],
        "add_themes": list(add_themes),
        "reduce_themes": list(reduce_themes),
        "neutral_themes": list(neutral_themes),
        "headline": headline,
        "theme_count": len(themes),
        "market_corroboration_theme_count": corroboration_available,
        "research_only": True,
        "actionable": False,
        "calibration_status": "not_calibrated",
        "usage_note": (
            "Afternoon Bot routines should read sector_timing.digest.headline "
            "or sector_timing.summary.add_observation_themes / "
            "reduce_observation_themes from GET /api/decision-board. "
            "This layer does not authorize orders."
        ),
    }


def build_sector_timing_observation(
    rows: list[dict[str, Any]] | None,
    *,
    slot_hint: str | None = None,
    market_evidence: list[dict[str, Any]] | None = None,
    taxonomy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a research-only sector timing block from decision-board rows.

    Parameters
    ----------
    rows:
        Decision-board instrument rows.  Expected keys: theme_l1, grade,
        return_5d, ts_code (optional for member lists).
    slot_hint:
        Optional afternoon slot label such as \"14:30\" or \"14:45\".
    market_evidence:
        Optional SectorSnapshot-like dicts for industry/concept corroboration.
        Missing or unmapped evidence stays unavailable — never fabricated.
    taxonomy:
        Optional sector_taxonomy.json payload (exact + keyword_rules) used only
        to map evidence sector_name → theme_l1.
    """

    evidence_by_theme = aggregate_market_evidence_by_theme(market_evidence, taxonomy)

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
                "market_corroboration": _attach_corroboration(
                    observation, theme, evidence_by_theme
                ),
                "research_only": True,
                "actionable": False,
            }
        )

    themes.sort(key=lambda item: (-item["strength_score"], item["theme_l1"]))
    for rank, item in enumerate(themes, start=1):
        item["rank"] = rank

    add_themes = [item["theme_l1"] for item in themes if item["observation"] == OBSERVATION_ADD]
    reduce_themes = [
        item["theme_l1"] for item in themes if item["observation"] == OBSERVATION_REDUCE
    ]
    neutral_themes = [
        item["theme_l1"] for item in themes if item["observation"] == OBSERVATION_NEUTRAL
    ]

    digest = _build_digest(
        slot_hint=slot_hint,
        add_themes=add_themes,
        reduce_themes=reduce_themes,
        neutral_themes=neutral_themes,
        themes=themes,
    )

    return {
        "version": "sector-timing-observation-v1",
        "slot_hint": slot_hint,
        "intended_slots": ["14:30", "14:45"],
        "research_only": True,
        "actionable": False,
        "calibration_status": "not_calibrated",
        "basis": _BASIS,
        "field_paths": {
            "api": API_READ_PATH,
            "digest": DIGEST_FIELD_PATH,
            "summary": SUMMARY_FIELD_PATH,
            "themes": "sector_timing.themes",
        },
        "summary": {
            "theme_count": len(themes),
            "add_observation_themes": add_themes,
            "reduce_observation_themes": reduce_themes,
            "neutral_observation_themes": neutral_themes,
            "market_corroboration_theme_count": digest["market_corroboration_theme_count"],
        },
        "digest": digest,
        "themes": themes,
    }


def empty_sector_timing_observation(*, slot_hint: str | None = None) -> dict[str, Any]:
    """Empty but schema-stable sector timing block for missing snapshots."""

    return build_sector_timing_observation([], slot_hint=slot_hint)


def infer_afternoon_slot_hint(generated_at_hour: int, generated_at_minute: int) -> str | None:
    """Map a Shanghai clock to the nearest afternoon digest slot label."""

    if generated_at_hour != 14:
        return None
    if 28 <= generated_at_minute <= 37:
        return "14:30"
    if 40 <= generated_at_minute <= 49:
        return "14:45"
    return None
