"""Project a persisted R4C Chan read onto chart geometry.

The chart does not call CZSC. It only draws the latest verified observation
when that observation's price basis matches the research series. A missing
snapshot may fall back to ``chan-structure-simplified-v1``. A failed
verification does not.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

_UP = {"up", "向上", "direction.up", "direction.向上"}
_DOWN = {"down", "向下", "direction.down", "direction.向下"}
_FALLBACK_REASONS = {"snapshot_missing", "unsupported_interval"}
_MISSING = "尚无已保存缠论观测。勾选后显示简化结构 chan-structure-simplified-v1，不是完整 CZSC。"
_BLOCKED = "已保存缠论读模型未通过校验，不改用简化结构代替。"
_BASIS = "已保存缠论观测的价格口径与当前研究序列不一致，未绘制该观测。图上若出现笔段，只是简化结构 chan-structure-simplified-v1。"
_DRAWN = "已保存缠论观测（CZSC 笔与中枢）。不是线段，不含背驰和买卖点。"


def annotate_chart_chan(chart: dict[str, Any], evidence: dict[str, Any] | None) -> dict[str, Any]:
    chart["chan_observation"] = project_persisted_chan(evidence, chart.get("research_price_basis_id"))
    return chart


def project_persisted_chan(evidence: dict[str, Any] | None, research_price_basis_id: str | None) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "available": False,
        "drawable": False,
        "fallback_allowed": True,
        "qualified": False,
        "actionable": False,
        "source": None,
        "reason_code": "snapshot_missing",
        "price_basis_id": None,
        "engine_id": None,
        "engine_version": None,
        "dialect_id": None,
        "counts": {"fx": 0, "bi": 0, "zs": 0},
        "bi": [],
        "segments": [],
        "zhongshu": [],
        "undrawable_bi": 0,
        "disclaimer": _MISSING,
    }
    if not isinstance(evidence, dict):
        return projected
    if not evidence.get("available"):
        reason = str(evidence.get("reason_code") or "snapshot_missing")
        fallback = reason in _FALLBACK_REASONS
        projected.update(
            reason_code=reason,
            fallback_allowed=fallback,
            disclaimer=_MISSING if fallback else _BLOCKED,
        )
        return projected

    counts = evidence.get("counts") if isinstance(evidence.get("counts"), dict) else {}
    basis = evidence.get("price_basis_id")
    projected.update(
        available=True,
        source=evidence.get("source") or "persisted_r4c_observed_revision",
        reason_code=None,
        price_basis_id=basis,
        engine_id=evidence.get("engine_id"),
        engine_version=evidence.get("engine_version"),
        dialect_id=evidence.get("dialect_id"),
        observation_id=evidence.get("observation_id"),
        settlement_status=evidence.get("settlement_status"),
        view_semantics=evidence.get("view_semantics"),
        counts={
            "fx": int(counts.get("fx") or 0),
            "bi": int(counts.get("bi") or 0),
            "zs": int(counts.get("zs") or 0),
        },
        fallback_allowed=False,
    )
    if not isinstance(research_price_basis_id, str) or not research_price_basis_id or basis != research_price_basis_id:
        projected.update(
            drawable=False,
            reason_code="price_basis_mismatch" if basis != research_price_basis_id else "price_basis_unknown",
            fallback_allowed=True,
            disclaimer=_BASIS,
        )
        return projected

    strokes: list[dict[str, Any]] = []
    zones: list[dict[str, Any]] = []
    undrawable = 0
    structures = evidence.get("structures")
    if isinstance(structures, list):
        for item in structures:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            geometry = item.get("geometry") if isinstance(item.get("geometry"), dict) else {}
            start = item.get("source_start")
            end = item.get("source_end")
            if kind == "bi":
                prices = _stroke_prices(item.get("direction"), geometry.get("high"), geometry.get("low"))
                if prices is None or not isinstance(start, str) or not isinstance(end, str):
                    undrawable += 1
                    continue
                strokes.append({
                    "start_date": start,
                    "end_date": end,
                    "start_price": prices[0],
                    "end_price": prices[1],
                    "direction": item.get("direction"),
                    "source": "persisted",
                })
            elif kind == "zs":
                lower, upper = _finite(geometry.get("zd")), _finite(geometry.get("zg"))
                if lower is None or upper is None or lower >= upper or not isinstance(start, str) or not isinstance(end, str):
                    continue
                zones.append({
                    "start_date": start,
                    "end_date": end,
                    "zd": lower,
                    "zg": upper,
                    "source": "persisted",
                })
    projected.update(drawable=True, bi=strokes, zhongshu=zones, undrawable_bi=undrawable, disclaimer=_DRAWN)
    if isinstance(evidence.get("transitions"), list):
        projected["revision_evidence"] = _revision_evidence(evidence)
    return projected


def _revision_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Allowlist saved metadata only; never infer revisions from chart geometry."""
    sequence = evidence.get("sequence_number")
    result: dict[str, Any] = {
        "sequence_number": sequence if type(sequence) is int and sequence > 0 else None,
        **{key: _optional_text(evidence.get(key)) for key in ("cutoff_at", "input_revision_id", "input_hash")},
        "transitions": [],
    }
    statuses = {"OBSERVED_NEW", "OBSERVED_CHANGED", "OBSERVED_UNCHANGED", "OBSERVED_ABSENT"}
    for value in evidence["transitions"]:
        item = value if isinstance(value, dict) else {}
        status = _optional_text(item.get("status"))
        result["transitions"].append({
            **{key: _optional_text(item.get(key)) for key in ("structure_key", "revision_id", "prior_revision_id")},
            "status": status if status in statuses else None,
            "reappearance": item.get("reappearance") if type(item.get("reappearance")) is bool else None,
        })
    return result


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _stroke_prices(direction: Any, high: Any, low: Any) -> tuple[float, float] | None:
    top, bottom = _finite(high), _finite(low)
    if top is None or bottom is None or bottom > top:
        return None
    token = str(direction or "").strip().lower().replace(" ", "")
    if token in _UP:
        return bottom, top
    if token in _DOWN:
        return top, bottom
    return None
