"""Read-only, bounded diagnostics. An audit report never grants qualification."""
from __future__ import annotations

from datetime import datetime
import re

from sqlalchemy import select

from app.models import DailyBar, IndicatorSnapshot, Instrument
from app.providers.data_contract import MAX_UNEXPLAINED_GAP, VERSION, assess_history, finite
from app.services.settlement import settled_session
from app.utils.hashing import stable_hash
from app.utils.input_lineage import history_digest

MAX_CODES = 50
MAX_BARS = 20000
CODE = re.compile(r"[0-9]{6}\.(SH|SZ)\Z")


def audit_history(db, settings, codes: list[str], *, now: datetime | None = None) -> dict:
    """Inspect explicit public instrument codes, never accounts or credentials.

    Source rows are not rescaled, deleted, promoted, or written. A clean result
    means only that the current automated guards did not find a blocker, not
    that corporate actions or absolute units have been independently certified.
    """
    if not codes or len(codes) > MAX_CODES or any(not isinstance(c, str) or not CODE.fullmatch(c) for c in codes):
        raise ValueError("one_to_fifty_explicit_exchange_codes_required")
    target = settled_session(settings, now)
    strategy = settings.load_strategy()
    instruments = {i.ts_code: i for i in db.scalars(select(Instrument).where(Instrument.ts_code.in_(codes)))}
    results = []
    for code in dict.fromkeys(codes):
        instrument = instruments.get(code)
        item = {"ts_code": code, "target_trade_date": target.isoformat(), "blockers": [],
                "actionable": False, "independent_unit_verification": "not_asserted",
                "corporate_action_verification": "not_asserted"}
        if instrument is None:
            results.append({**item, "blockers": ["instrument_not_in_catalog"], "bar_count": 0})
            continue
        rows = list(db.scalars(select(DailyBar).where(DailyBar.instrument_id == instrument.id)
            .order_by(DailyBar.trade_date, DailyBar.adjust).limit(MAX_BARS + 1)))
        truncated = len(rows) > MAX_BARS
        if truncated:
            rows = rows[:MAX_BARS]
        reasons = assess_history(rows)
        if truncated:
            reasons.append("audit_limit_exceeded_history_not_fully_checked")
        if not rows or rows[-1].trade_date != target:
            reasons.append("target_trade_date_not_covered")
        if len(rows) < 30:
            reasons.append("indicator_warmup_insufficient")
        breaks = []
        for previous, current in zip(rows, rows[1:]):
            if all(finite(v) and float(v) > 0 for v in (previous.close, current.open, current.close)):
                change = float(current.close) / float(previous.close) - 1
                opening = float(current.open) / float(previous.close) - 1
                if abs(change) > MAX_UNEXPLAINED_GAP or abs(opening) > MAX_UNEXPLAINED_GAP:
                    breaks.append({"previous_date": previous.trade_date.isoformat(),
                        "date": current.trade_date.isoformat(), "previous_close": previous.close,
                        "close": current.close, "close_change": change, "open_change": opening})
        snapshot = db.scalar(select(IndicatorSnapshot).where(IndicatorSnapshot.instrument_id == instrument.id)
            .order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc(), IndicatorSnapshot.id.desc()).limit(1))
        snapshot_reasons = []
        if snapshot is None:
            snapshot_reasons.append("indicator_missing")
        else:
            for key, expected in (("version", strategy["indicator_version"]),
                                  ("config_hash", stable_hash(strategy)),
                                  ("feature_schema_version", strategy["feature_schema_version"])):
                if getattr(snapshot, key) != expected:
                    snapshot_reasons.append("indicator_" + key + "_mismatch")
            if snapshot.as_of_date != target:
                snapshot_reasons.append("indicator_target_not_covered")
        results.append({**item, "bar_count": len(rows), "history_complete_in_audit": not truncated,
            "first_date": rows[0].trade_date.isoformat() if rows else None,
            "last_date": rows[-1].trade_date.isoformat() if rows else None,
            "source_versions": sorted({str(r.source) for r in rows}),
            "price_bases": sorted({str(r.adjust) for r in rows}),
            "missing_or_invalid_volume": sum(not finite(r.volume) or float(r.volume) < 0 for r in rows),
            "missing_or_invalid_amount": sum(not finite(r.amount) or float(r.amount) < 0 for r in rows),
            "unexplained_break_count": len(breaks), "unexplained_breaks": breaks[:50],
            "inspected_history_hash": history_digest(rows),
            "hash_scope": "full_selected_history" if not truncated else "truncated_audit_sample",
            "blockers": list(dict.fromkeys(reasons)), "indicator_blockers": snapshot_reasons,
            "indicator_date": snapshot.as_of_date.isoformat() if snapshot else None,
            "indicator_version": snapshot.version if snapshot else None,
            "candidate_recompute_allowed": not reasons})
    return {"schema_version": "etf-readonly-history-audit-v1", "data_contract": VERSION,
        "target_trade_date": target.isoformat(), "writes_performed": False, "provider_called": False,
        "actionable": False, "items": results,
        "limitations": ["No endpoint or corporate-action approval is issued by this report.",
            "The 35% discontinuity threshold is an anomaly screen, not proof of continuous total returns.",
            "An indicator's stored hash is panel-based; this per-instrument audit hash is not a replacement."]}
