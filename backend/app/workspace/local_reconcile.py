"""16:30 local reconciliation (05 §slot reconcile, 08 acceptance).

Read-only over the owned local root:
1. Delivery: every outbox bundle of the session vs its stored receipt
   (bundle_id/manifest_hash/sequence must equal the local manifest digest).
2. Consumer identity: requires an approved observer scope; until then the field
   is reported as NOT_RUN instead of being inferred from HTTP 200.
3. Outcomes: realised close-to-close T+1/T+5 returns of the session's
   universe from settled local daily bars; immature horizons stay
   PENDING_OUTCOME.  This is an observation log, not a calibration or hit-rate
   claim (Phase 2), and actionable stays false.
Results are written only under ``<root>/receipts/reconcile``.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.workspace.shadow_bundle import digest

SHANGHAI = ZoneInfo("Asia/Shanghai")
HORIZONS = (1, 5)
REPORT_VERSION = "local-reconcile-v1"


def _session_of_sequence(sequence: int) -> date:
    return datetime.fromtimestamp(sequence / 1000, tz=timezone.utc).astimezone(SHANGHAI).date()


def reconcile_delivery(outbox: Path, session: date) -> dict[str, Any]:
    items = []
    for path in sorted(outbox.glob("bundle_*.json")):
        if path.name.endswith(".receipt.json"):
            continue
        try:
            sequence = int(path.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        if _session_of_sequence(sequence) != session:
            continue
        entry: dict[str, Any] = {"sequence": sequence, "bundle_file": path.name}
        try:
            with open(path, encoding="utf-8") as handle:
                manifest = json.load(handle)["manifest"]
            local_id = digest(manifest)
            entry["bundle_id"] = local_id
            entry["universe_size"] = len(manifest.get("universe") or [])
        except (OSError, ValueError, KeyError, TypeError):
            entry["state"] = "LOCAL_BUNDLE_UNREADABLE"
            items.append(entry)
            continue
        receipt_path = path.with_name(f"{path.stem}.receipt.json")
        if not receipt_path.is_file():
            entry["state"] = "RECEIPT_MISSING"
        else:
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                receipt = {}
            ok = (
                receipt.get("bundle_id") == local_id
                and receipt.get("manifest_hash", local_id) == local_id
                and receipt.get("sequence", sequence) == sequence
                and receipt.get("status", "accepted") in {"accepted", "already_accepted"}
            )
            entry["state"] = "MATCHED" if ok else "RECEIPT_MISMATCH"
            entry["received_at"] = receipt.get("received_at")
        items.append(entry)
    counts: dict[str, int] = {}
    for item in items:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    latest = max((i for i in items if i["state"] == "MATCHED"), key=lambda i: i["sequence"], default=None)
    return {"bundles": items, "counts": counts, "latest_matched": latest}


def realised_outcomes(db, universe: list[str], base_day: date) -> list[dict[str, Any]]:
    from sqlalchemy import select
    from app.models import DailyBar, Instrument

    rows = []
    for code in universe:
        instrument = db.scalar(select(Instrument).where(Instrument.ts_code == code))
        record: dict[str, Any] = {"ts_code": code, "base_trade_date": base_day.isoformat()}
        if instrument is None:
            record["state"] = "NO_INSTRUMENT"
            rows.append(record)
            continue
        bars = db.scalars(
            select(DailyBar)
            .where(DailyBar.instrument_id == instrument.id, DailyBar.adjust == "none", DailyBar.trade_date >= base_day)
            .order_by(DailyBar.trade_date)
            .limit(max(HORIZONS) + 1)
        ).all()
        if not bars or bars[0].trade_date != base_day or not bars[0].close:
            record["state"] = "BASE_BAR_MISSING"
            rows.append(record)
            continue
        base = bars[0].close
        for horizon in HORIZONS:
            key = f"t{horizon}"
            if len(bars) > horizon and bars[horizon].close:
                record[key] = {"state": "MATURED", "trade_date": bars[horizon].trade_date.isoformat(),
                               "return": round(bars[horizon].close / base - 1.0, 6)}
            else:
                record[key] = {"state": "PENDING_OUTCOME"}
        record["state"] = "OK"
        rows.append(record)
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for horizon in HORIZONS:
        values = [r[f"t{horizon}"]["return"] for r in rows if r.get(f"t{horizon}", {}).get("state") == "MATURED"]
        pending = sum(1 for r in rows if r.get(f"t{horizon}", {}).get("state") == "PENDING_OUTCOME")
        out[f"t{horizon}"] = {
            "matured": len(values),
            "pending_outcome": pending,
            "mean_return": round(sum(values) / len(values), 6) if values else None,
            "positive_share": round(sum(v > 0 for v in values) / len(values), 4) if values else None,
        }
    return out


def run_reconcile(root: Path, *, session: date, db=None, outcome_base_days: list[date] | None = None) -> dict[str, Any]:
    outbox = root / "outbox"
    delivery = reconcile_delivery(outbox, session)
    universe = []
    latest = delivery.get("latest_matched")
    if latest:
        try:
            with open(outbox / latest["bundle_file"], encoding="utf-8") as handle:
                universe = list(json.load(handle)["manifest"]["universe"])
        except (OSError, ValueError, KeyError):
            universe = []
    outcomes = []
    if db is not None and universe:
        for base_day in outcome_base_days or [session]:
            rows = realised_outcomes(db, universe, base_day)
            outcomes.append({"base_trade_date": base_day.isoformat(), "summary": _summary(rows), "rows": rows})
    report = {
        "report_version": REPORT_VERSION,
        "session": session.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "delivery": delivery,
        "consumer_identity": {"state": "NOT_RUN", "reason": "observer read scope not approved; HTTP 200 is not consumer proof"},
        "outcomes": outcomes,
        "actionable": False,
        "calibration": "not_calibrated",
    }
    target = root / "receipts" / "reconcile"
    target.mkdir(parents=True, exist_ok=True)
    final = target / f"reconcile_{session.isoformat()}.json"
    tmp = final.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, final)
    report["report_file"] = str(final)
    return report


def recent_base_days(db, session: date, count: int = 6) -> list[date]:
    from sqlalchemy import select
    from app.models import DailyBar

    days = db.scalars(
        select(DailyBar.trade_date).where(DailyBar.trade_date <= session).distinct()
        .order_by(DailyBar.trade_date.desc()).limit(count)
    ).all()
    return sorted(days)
