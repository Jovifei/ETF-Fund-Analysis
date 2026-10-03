"""Structured detail availability v1 contract helpers.

This module only transforms already computed read-model evidence. It does not
calculate decisions, upgrade qualification, infer missing measurements, or make
anything actionable.
"""

from __future__ import annotations

from copy import deepcopy


DETAIL_AVAILABILITY_VERSION = "detail-availability-v1"

MODULE_ORDER = (
    "instrument",
    "price",
    "history",
    "price_basis",
    "indicators",
    "volume",
    "forecasts",
    "decision",
    "support_resistance",
)


def _module(status: str, reason_code: str | None) -> dict:
    return {"status": status, "reason_code": reason_code}


def build_detail_availability(existing: dict, *, support_resistance: dict | None = None, chart: dict | None = None) -> dict:
    """Build detail-availability-v1 from existing read-model evidence.

    The first eight modules are passed through without reinterpretation.
    Forecast horizon diagnostics remain owned by their source rows. Structural
    evidence is fail-closed: an SR snapshot is only available when the chart
    evidence explicitly confirms that overlay is allowed.
    """
    result = {name: deepcopy(existing.get(name, _module("unknown", "not_reported"))) for name in MODULE_ORDER[:-1]}

    chart = chart or {}
    if chart.get("history_issue"):
        result["support_resistance"] = _module("blocked", chart["history_issue"])
    elif chart.get("raw_overlay_allowed") is False:
        result["support_resistance"] = _module("blocked", chart.get("raw_overlay_reason") or "price_basis_mismatch")
    elif support_resistance is None:
        result["support_resistance"] = _module("unavailable", "support_resistance_not_generated")
    elif chart.get("sr_overlay_allowed") is True:
        result["support_resistance"] = _module("degraded", "price_only_research") if support_resistance.get("qualification") == "price_only_research" else _module("available", None)
    else:
        result["support_resistance"] = _module(
            "blocked",
            chart.get("raw_overlay_reason") or "support_resistance_overlay_blocked",
        )

    return {
        "contract_version": DETAIL_AVAILABILITY_VERSION,
        "modules": result,
        "actionable": False,
    }


def forecast_availability(snapshot, reasons, *, history_issue=None):
    """Expose only controlled diagnostic causes after snapshot/time guards."""
    if history_issue or reasons:
        return _module("blocked", history_issue or reasons[0])
    if snapshot is None:
        return _module("unavailable", "forecast_not_generated")
    diagnostics = snapshot.diagnostics_json or {}
    reason = diagnostics.get("reason") if isinstance(diagnostics, dict) else None
    if reason in {"feature_shortage", "feature_or_sample_shortage", "history_too_short"}:
        return _module("unavailable", reason)
    if not any(getattr(snapshot, name, None) is not None for name in ("p_up", "expected_return", "q10", "q50", "q90")):
        return _module("unavailable", "forecast_values_unavailable")
    return _module("available", None)
