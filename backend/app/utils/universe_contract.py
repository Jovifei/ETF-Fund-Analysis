from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

UNIVERSE_CONTRACT_VERSION = "research-universe-v1-current-enabled"


def parse_listing_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text[:8], fmt).date()
        except (TypeError, ValueError):
            pass
    return None


def instrument_listing_date(instrument: Any) -> date | None:
    metadata = getattr(instrument, "metadata_json", None) or {}
    return parse_listing_date(metadata.get("list_date"))


def filter_rows_from_listing(rows: Iterable[Any], instrument: Any) -> tuple[list[Any], dict[str, Any]]:
    ordered = sorted(rows or (), key=lambda row: row.trade_date)
    listing = instrument_listing_date(instrument)
    if listing is None:
        return ordered, {
            "list_date": None,
            "listing_date_known": False,
            "prelisting_rows_removed": 0,
        }
    kept = [row for row in ordered if row.trade_date >= listing]
    return kept, {
        "list_date": listing.isoformat(),
        "listing_date_known": True,
        "prelisting_rows_removed": len(ordered) - len(kept),
    }


def current_enabled_universe_contract(instruments: Iterable[Any]) -> dict[str, Any]:
    rows = list(instruments or ())
    listing_dates = {
        str(item.ts_code): instrument_listing_date(item)
        for item in rows
    }
    known = sum(value is not None for value in listing_dates.values())
    count = len(rows)
    return {
        "version": UNIVERSE_CONTRACT_VERSION,
        "selection": "current_enabled_snapshot",
        "current_enabled_only": True,
        "instrument_count": count,
        "instrument_codes": sorted(str(item.ts_code) for item in rows),
        "listing_date_known_count": known,
        "listing_date_coverage": round(known / count, 6) if count else 0.0,
        "listing_dates": {
            code: value.isoformat() if value is not None else None
            for code, value in sorted(listing_dates.items())
        },
        "historical_membership_available": False,
        "delist_history_available": False,
        "survivorship_bias_controlled": False,
        "qualification": "UNKNOWN",
        "limitations": [
            "current enabled universe is not a point-in-time historical membership series",
            "disabled/delisted historical constituents cannot be reconstructed from Instrument.enabled",
            "known listing dates only prevent pre-listing observations; they do not remove survivorship bias",
        ],
    }
