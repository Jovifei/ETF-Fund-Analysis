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
    """Build detail-availability-v1 from existing evidence.

    Existing eight-module status/reasons are preserved. Forecast horizon reasons
    remain outside this aggregate and are never converted into other module
    shortages. Support/resistance distinguishes missing snapshots from evidence
    that exists but cannot be overlaid because chart qualification blocks it.
    """
    result = {name: existing.get(name, _module("unknown", "not_reported")) for name in MODULE_ORDER[:-1]}

    chart = chart or {}
    if support_resistance:
        if chart.get("sr_overlay_allowed") is False:
            result["support_resistance"] = _module("blocked", chart.get("raw_overlay_reason") or "support_resistance_overlay_blocked")
        else:
            result["support_resistance"] = _module("available", None)
    else:
        result["support_resistance"] = _module("unavailable", "support_resistance_not_generated")

    return {
        "contract_version": DETAIL_AVAILABILITY_VERSION,
        "modules": result,
        "actionable": False,
    }
