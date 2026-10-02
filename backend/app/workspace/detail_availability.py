"""Structured detail availability v1 contract helpers.

This module only transforms already computed read-model evidence. It does not
calculate decisions, upgrade qualification, infer missing measurements, or make
anything actionable.
"""

from __future__ import annotations


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
    result = {name: existing.get(name, _module("unknown", "not_reported")) for name in MODULE_ORDER[:-1]}

    chart = chart or {}
    if support_resistance is None:
        result["support_resistance"] = _module("unavailable", "support_resistance_not_generated")
    elif chart.get("sr_overlay_allowed") is True:
        result["support_resistance"] = _module("available", None)
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
