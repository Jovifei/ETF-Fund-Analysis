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
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.workspace.shadow_bundle import digest
from app.workspace.shadow_client import _validate_receipt, _unique_object
from app.workspace.local_atomic import write_json_atomic

SHANGHAI = ZoneInfo("Asia/Shanghai")
HORIZONS = (1, 5)
REPORT_VERSION = "local-reconcile-v2"


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
        try:
            matches_session = _session_of_sequence(sequence) == session
        except (ValueError, OverflowError, OSError):
            continue
        if not matches_session:
            continue
        entry: dict[str, Any] = {"sequence": sequence, "bundle_file": path.name}
        try:
            with open(path, encoding="utf-8") as handle:
                manifest = json.load(handle, object_pairs_hook=_unique_object)["manifest"]
            if not isinstance(manifest, dict) or type(manifest.get("sequence")) is not int or manifest["sequence"] != sequence:
                raise ValueError("bundle filename/manifest sequence mismatch")
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
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
                if manifest.get("contract_version") != "local-display-v2":
                    raise ValueError("v2 delivery evidence required")
                _validate_receipt(receipt, manifest, "local-display-v2")
                ok = True
            except (OSError, ValueError, TypeError):
                receipt, ok = {}, False
            entry["state"] = "MATCHED" if ok else "RECEIPT_MISMATCH"
            entry["received_at"] = receipt.get("received_at")
        items.append(entry)
    counts: dict[str, int] = {}
    for item in items:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    latest = max((i for i in items if i["state"] == "MATCHED"), key=lambda i: i["sequence"], default=None)
    return {"bundles": items, "counts": counts, "latest_matched": latest}


def realised_outcomes(db, universe: list[str], base_day: date, *, as_of: datetime | None = None,
                      calendar=None, price_evidence: dict | None = None) -> list[dict[str, Any]]:
    from sqlalchemy import select
    from app.models import DailyBar, Instrument

    from app.services.trading_calendar_service import TradingCalendarService
    from app.services.settlement import SETTLEMENT_CUTOFF

    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        raise ValueError("outcome cutoff requires timezone")
    calendar = calendar or TradingCalendarService()
    price_evidence = price_evidence or {}
    local_now = as_of.astimezone(SHANGHAI)
    rows = []
    for code in universe:
        instrument = db.scalar(select(Instrument).where(Instrument.ts_code == code))
        record: dict[str, Any] = {"ts_code": code, "base_trade_date": base_day.isoformat()}
        if instrument is None:
            record["state"] = "NO_INSTRUMENT"
            rows.append(record)
            continue
        base_decision = calendar.decision(base_day)
        sessions = []
        day = base_day
        calendar_verified = base_decision.verified and base_decision.is_trade_day
        for _ in range(40):
            day += timedelta(days=1)
            decision = calendar.decision(day)
            if not decision.verified:
                calendar_verified = False
                break
            if decision.is_trade_day:
                sessions.append(day)
            if len(sessions) == max(HORIZONS):
                break
        for horizon in HORIZONS:
            key = f"t{horizon}"
            if not calendar_verified or len(sessions) < horizon:
                record[key] = {"state": "UNKNOWN", "reason": "calendar_unverified"}
                continue
            target = sessions[horizon - 1]
            if target > local_now.date() or (target == local_now.date() and local_now.time() < SETTLEMENT_CUTOFF):
                record[key] = {"state": "PENDING_OUTCOME"}
                continue
            bars = db.scalars(select(DailyBar).where(DailyBar.instrument_id == instrument.id,
                DailyBar.adjust == "qfq", DailyBar.trade_date.in_((base_day, target)))).all()
            by_day = {bar.trade_date: bar for bar in bars}
            proof = price_evidence.get(code) or {}
            valid = len(by_day) == 2 and all(
                bar.source and "mock" not in bar.source.lower()
                and bar.close is not None and isfinite(bar.close) and bar.close > 0
                and bar.fetched_at is not None
                and (bar.fetched_at.replace(tzinfo=timezone.utc) if bar.fetched_at.tzinfo is None else bar.fetched_at) <= as_of
                and (bar.fetched_at.replace(tzinfo=timezone.utc) if bar.fetched_at.tzinfo is None else bar.fetched_at)
                    >= datetime.combine(bar.trade_date, SETTLEMENT_CUTOFF, SHANGHAI)
                for bar in bars)
            comparable = (isinstance(proof, dict) and proof.get("adjust") == "qfq"
                          and proof.get("settlement_status") == "settled"
                          and isinstance(proof.get("price_basis_id"), str) and proof["price_basis_id"].strip()
                          and proof.get("evidence_ref") and isinstance(proof.get("quality_hashes"), list)
                          and all(bar.quality_hash and bar.quality_hash in proof["quality_hashes"] for bar in bars))
            if not valid or not comparable:
                record[key] = {"state": "UNKNOWN", "reason": "settled_comparable_price_evidence_missing"}
                continue
            record[key] = {"state": "MATURED", "trade_date": target.isoformat(),
                           "return": round(by_day[target].close / by_day[base_day].close - 1.0, 6)}
        record["state"] = "OBSERVATION_ONLY"
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
            "unknown": sum(1 for r in rows if r.get(f"t{horizon}", {}).get("state") == "UNKNOWN"),
            "mean_return": round(sum(values) / len(values), 6) if values else None,
            "positive_share": round(sum(v > 0 for v in values) / len(values), 4) if values else None,
        }
    return out


def run_reconcile(root: Path, *, session: date, db=None, outcome_base_days: list[date] | None = None,
                  as_of: datetime | None = None) -> dict[str, Any]:
    as_of = as_of or datetime.now(timezone.utc)
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
            rows = realised_outcomes(db, universe, base_day, as_of=as_of)
            outcomes.append({"base_trade_date": base_day.isoformat(), "summary": _summary(rows), "rows": rows})
    report = {
        "report_version": REPORT_VERSION,
        "state": "INCOMPLETE",
        "session": session.isoformat(),
        "generated_at": as_of.isoformat(),
        "delivery": delivery,
        "consumer_identity": {"state": "NOT_RUN", "reason": "observer read scope not approved; HTTP 200 is not consumer proof"},
        "outcomes": outcomes,
        "actionable": False,
        "calibration": "not_calibrated",
    }
    target = root / "receipts" / "reconcile"
    target.mkdir(parents=True, exist_ok=True)
    final = target / f"reconcile_{session.isoformat()}.json"
    write_json_atomic(final, report)
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
