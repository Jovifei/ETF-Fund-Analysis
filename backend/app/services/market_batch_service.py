"""Batch daily-bar upsert used by MarketService, with the same provider contract.

One query loads each instrument's overlap; no SELECT for every individual bar.
Provider failures and invalid batches are isolated with a SAVEPOINT and audited.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.models import DailyBar, Instrument
from app.providers.base import ProviderError
from app.services.audit_service import AuditTimer, record_provider_audit
from app.services.event_service import emit_event
from app.utils.hashing import stable_hash


def refresh_daily_bars(service, db, lookback_days=900, codes=None, run_id=None):
    run_id = run_id or uuid4().hex
    instruments = db.scalars(select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)).all()
    if codes:
        wanted = {code.upper() for code in codes}
        instruments = [row for row in instruments if row.ts_code.upper() in wanted or row.symbol in wanted]
    ids = [row.id for row in instruments]
    bounds = {row[0]: (row[1], row[2]) for row in db.execute(select(DailyBar.instrument_id, func.min(DailyBar.trade_date), func.max(DailyBar.trade_date)).where(DailyBar.instrument_id.in_(ids)).group_by(DailyBar.instrument_id))} if ids else {}
    end_date = datetime.now(service.settings.timezone).date()
    totals = {"inserted": 0, "updated": 0, "unchanged": 0, "instruments": 0, "failures": []}
    for instrument in instruments:
        start_date = end_date - timedelta(days=lookback_days)
        earliest, latest = bounds.get(instrument.id, (None, None))
        if earliest is not None and latest is not None and earliest <= start_date:
            start_date = max(start_date, latest - timedelta(days=7))
        timer, error, records = AuditTimer(), None, []
        try:
            records = list(service.provider.fetch_daily_bars(instrument.ts_code, start_date, end_date))
            if len(records) > max(lookback_days * 3, 20000):
                raise ProviderError("daily bar response exceeds bounded history")
            unique = {}
            for item in records:
                if item.ts_code != instrument.ts_code or not start_date <= item.trade_date <= end_date:
                    raise ProviderError("daily bar identity or date mismatch")
                prices = (item.open, item.high, item.low, item.close)
                if not all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0 for value in prices) or item.low > min(prices) or item.high < max(prices):
                    raise ProviderError("daily bar OHLC invalid")
                if any(value is not None and (not math.isfinite(float(value)) or value < 0) for value in (item.volume, item.amount)):
                    raise ProviderError("daily bar volume or amount invalid")
                key = (item.trade_date, item.adjust)
                if key in unique and stable_hash(unique[key].to_dict()) != stable_hash(item.to_dict()):
                    raise ProviderError("conflicting duplicate daily bars")
                unique[key] = item
            inserted, updated, unchanged = 0, 0, 0
            with db.begin_nested():
                stored = db.scalars(select(DailyBar).where(DailyBar.instrument_id == instrument.id, DailyBar.trade_date >= start_date, DailyBar.trade_date <= end_date)).all()
                by_key = {(row.trade_date, row.adjust): row for row in stored}
                existing_adjusts = set(db.scalars(select(DailyBar.adjust).where(DailyBar.instrument_id == instrument.id).distinct()))
                incoming_adjusts = {item.adjust for item in unique.values()}
                if existing_adjusts and incoming_adjusts and incoming_adjusts != existing_adjusts:
                    raise ProviderError("price adjustment changed; manual rebase required")
                for key, item in unique.items():
                    digest = stable_hash(item.to_dict())
                    row = by_key.get(key)
                    if row is None:
                        row = DailyBar(instrument_id=instrument.id, trade_date=item.trade_date, adjust=item.adjust)
                        db.add(row)
                        by_key[key] = row
                        inserted += 1
                    else:
                        updated += 1
                        if row.quality_hash == digest:
                            unchanged += 1
                            continue
                    for field in ("open", "high", "low", "close", "pre_close", "volume", "amount", "pct_change", "source"):
                        setattr(row, field, getattr(item, field))
                    row.quality_hash = digest
                db.flush()
            totals["instruments"] += 1
            totals["inserted"] += inserted
            totals["updated"] += updated
            totals["unchanged"] += unchanged
        except Exception as exc:
            error = exc
            # Never persist raw provider errors, URLs, or credentials in reports.
            totals["failures"].append({"ts_code": instrument.ts_code, "error": type(exc).__name__})
        finally:
            if service.persist_provider_audits:
                record_provider_audit(db, run_id=run_id, operation="fetch_daily_bars", provider=service.provider, result=records, error=error, latency_ms=timer.elapsed_ms)
    db.flush()
    emit_event(db, "bars.updated", {**totals, "run_id": run_id})
    return {"run_id": run_id, **totals}
