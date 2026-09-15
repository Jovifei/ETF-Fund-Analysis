"""Fail-closed validation for a sanitized production freshness snapshot.

This gate never contacts a provider or database. It consumes the read-only JSON
receipt produced by an external diagnostic and separates research display from
strict release qualification. Missing values remain blockers; they are never
filled or inferred here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def evaluate_snapshot(snapshot: dict, *, now: datetime | None = None,
                      require_realtime: bool = False) -> dict:
    """Return a bounded gate result for one sanitized snapshot.

    ``require_realtime=False`` is the research-display gate: an old/unverified
    quote remains visible as research data but does not grant actionability.
    ``require_realtime=True`` is the release gate and requires a verified
    real-time quote for every tracked instrument.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    target = snapshot.get("target_trade_date") if isinstance(snapshot, dict) else None
    raw_items = snapshot.get("items") if isinstance(snapshot, dict) else None
    if not isinstance(target, str) or not raw_items or not isinstance(raw_items, list):
        return {
            "status": "fail",
            "qualification_granted": False,
            "summary": {"tracked_instruments": 0, "blocked_instruments": 0,
                        "require_realtime": require_realtime, "invalid_snapshot": True},
            "items": [],
        }

    results = []
    for raw in raw_items:
        item = raw if isinstance(raw, dict) else {}
        code = item.get("ts_code") if isinstance(item.get("ts_code"), str) else "unknown"
        blockers: list[str] = []
        if item.get("daily_latest") != target:
            blockers.append("daily_target_not_covered")
        if (_int(item.get("missing_volume")) or 0) > 0:
            blockers.append("volume_missing")
        if (_int(item.get("missing_amount")) or 0) > 0:
            blockers.append("amount_missing")
        if item.get("indicator_latest") != target:
            blockers.append("indicator_target_not_covered")
        if not isinstance(item.get("indicator_version"), str) or not item.get("indicator_version"):
            blockers.append("indicator_version_missing")
        if item.get("forecast_latest") != target:
            blockers.append("forecast_target_not_covered")
        if (_int(item.get("forecast_horizons")) or 0) < 4:
            blockers.append("forecast_horizons_incomplete")
        quote_time = _timestamp(item.get("quote_latest"))
        if quote_time is None:
            blockers.append("quote_source_time_missing")
        elif quote_time > now:
            blockers.append("quote_source_time_in_future")
        if require_realtime and not (item.get("quote_realtime") is True and item.get("quote_timestamp_verified") is True):
            blockers.append("quote_not_realtime_or_verified")
        results.append({"ts_code": code, "blockers": sorted(set(blockers)),
                        "qualification_granted": not blockers,
                        "actionable": False})

    blocked = sum(bool(item["blockers"]) for item in results)
    return {
        "status": "pass" if blocked == 0 else "fail",
        "qualification_granted": blocked == 0,
        "summary": {"tracked_instruments": len(results), "blocked_instruments": blocked,
                    "require_realtime": require_realtime, "invalid_snapshot": False},
        "items": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-realtime", action="store_true")
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.input.read_text(encoding="utf-8"))
        result = evaluate_snapshot(snapshot, require_realtime=args.require_realtime)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": result["status"], **result["summary"]}, ensure_ascii=False))
        return 0 if result["status"] == "pass" else 3
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "reason": type(exc).__name__}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
