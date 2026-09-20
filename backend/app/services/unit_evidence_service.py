from __future__ import annotations

from sqlalchemy import select

from app.models import DailyBar, Instrument, UnitCertificationEvidence
from app.providers.composite import CompositeProvider
from app.providers.unit_certification import (
    DOCUMENTED_ENDPOINT_FIELDS,
    UnitCertification,
    UnitObservation,
    certify_absolute_units,
)
from app.utils.hashing import stable_hash


def _observation_hash(value: UnitObservation) -> str:
    return stable_hash({
        "ts_code": value.ts_code, "trade_date": value.trade_date.isoformat(),
        "close": value.close, "source": value.source, "raw_volume": value.raw_volume,
        "raw_amount": value.raw_amount, "converted_volume": value.converted_volume,
        "converted_amount": value.converted_amount,
    })


def _units(source: str) -> tuple[str | None, str | None]:
    contract = DOCUMENTED_ENDPOINT_FIELDS.get(source) or {}
    return contract.get("volume_raw_unit"), contract.get("amount_raw_unit")


def record_unit_evidence(db, instrument, bar, primary: UnitObservation, independent: UnitObservation,
                         *, primary_upstream: str, independent_upstream: str):
    if primary.ts_code != instrument.ts_code or independent.ts_code != instrument.ts_code:
        raise ValueError("unit evidence instrument mismatch")
    if primary.trade_date != bar.trade_date or independent.trade_date != bar.trade_date:
        raise ValueError("unit evidence trade date mismatch")
    result = certify_absolute_units(primary, independent)
    reasons = list(result.reasons)
    if bar.volume is None or bar.amount is None or result.volume is None or result.amount is None:
        reasons.append("daily_bar_quantity_missing")
    else:
        if abs(float(bar.volume) - float(result.volume)) > 0.5:
            reasons.append("daily_bar_volume_binding_mismatch")
        if abs(float(bar.amount) - float(result.amount)) > 0.5:
            reasons.append("daily_bar_amount_binding_mismatch")
    if not primary_upstream or not independent_upstream or primary_upstream == independent_upstream:
        reasons.append("independent_observation_not_second_upstream")
    certified = result.certified and not reasons
    primary_units = _units(primary.source)
    independent_units = _units(independent.source)
    primary_hash = _observation_hash(primary)
    independent_hash = _observation_hash(independent)
    existing = db.scalar(select(UnitCertificationEvidence).where(
        UnitCertificationEvidence.instrument_id == instrument.id,
        UnitCertificationEvidence.trade_date == bar.trade_date,
        UnitCertificationEvidence.adjust == bar.adjust,
        UnitCertificationEvidence.daily_bar_quality_hash == bar.quality_hash,
        UnitCertificationEvidence.primary_input_hash == primary_hash,
        UnitCertificationEvidence.independent_input_hash == independent_hash,
    ))
    if existing is not None:
        return existing
    row = UnitCertificationEvidence(
        instrument_id=instrument.id, trade_date=bar.trade_date, adjust=bar.adjust,
        daily_bar_quality_hash=bar.quality_hash,
        primary_source=primary.source, independent_source=independent.source,
        primary_upstream=primary_upstream, independent_upstream=independent_upstream,
        primary_endpoint_version=primary.source, independent_endpoint_version=independent.source,
        primary_close=primary.close, independent_close=independent.close,
        primary_raw_volume=primary.raw_volume, primary_raw_amount=primary.raw_amount,
        independent_raw_volume=independent.raw_volume, independent_raw_amount=independent.raw_amount,
        primary_volume_unit=primary_units[0], primary_amount_unit=primary_units[1],
        independent_volume_unit=independent_units[0], independent_amount_unit=independent_units[1],
        converted_volume=result.volume, converted_amount=result.amount,
        primary_input_hash=primary_hash, independent_input_hash=independent_hash,
        certified=certified, reasons_json=list(dict.fromkeys(reasons)),
    )
    db.add(row)
    db.flush()
    return row


def collect_unit_evidence(db, provider, *, codes=None, settled_days: int = 5, run_id: str | None = None):
    """Collect bounded same-day observations without changing persisted bars."""
    from app.services.audit_service import AuditTimer, record_provider_audit

    candidates = provider.providers if isinstance(provider, CompositeProvider) else [provider]
    candidates = [item for item in candidates if hasattr(item, "fetch_daily_bars")]
    wanted = {value.upper() for value in codes or []}
    instruments = db.scalars(select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)).all()
    if wanted:
        instruments = [item for item in instruments if item.ts_code.upper() in wanted or item.symbol in wanted]
    saved = 0
    failures = []
    for instrument in instruments:
        bars = db.scalars(select(DailyBar).where(DailyBar.instrument_id == instrument.id)
                          .order_by(DailyBar.trade_date.desc()).limit(settled_days)).all()
        bars.reverse()
        if not bars:
            failures.append({"ts_code": instrument.ts_code, "reason": "history_missing"})
            continue
        observations = {}
        for candidate in candidates:
            records = []
            error = None
            timer = AuditTimer()
            for attempt in range(2):
                try:
                    records = list(candidate.fetch_daily_bars(
                        instrument.ts_code, bars[0].trade_date, bars[-1].trade_date
                    ))
                    error = None
                    break
                except Exception as exc:
                    error = exc
                    if attempt:
                        break
            record_provider_audit(db, run_id=run_id or "unit-evidence", operation="certify_units",
                                  provider=candidate, result=records, error=error, latency_ms=timer.elapsed_ms)
            for item in records:
                if item.raw_volume is None or item.raw_amount is None or not item.source_upstream:
                    continue
                observations[(item.trade_date, item.source)] = item
        for bar in bars:
            primary_row = observations.get((bar.trade_date, bar.source))
            if primary_row is None:
                continue
            independent_row = next((item for (day, _), item in observations.items()
                                    if day == bar.trade_date and item.source_upstream != primary_row.source_upstream), None)
            if independent_row is None:
                continue
            primary = UnitObservation(instrument.ts_code, bar.trade_date, primary_row.close, primary_row.source,
                                      primary_row.raw_volume, primary_row.raw_amount,
                                      primary_row.volume, primary_row.amount)
            independent = UnitObservation(instrument.ts_code, bar.trade_date, independent_row.close, independent_row.source,
                                          independent_row.raw_volume, independent_row.raw_amount,
                                          independent_row.volume, independent_row.amount)
            evidence = record_unit_evidence(
                db, instrument, bar, primary, independent,
                primary_upstream=primary_row.source_upstream,
                independent_upstream=independent_row.source_upstream,
            )
            saved += int(evidence.certified)
    return {"run_id": run_id, "status": "succeeded" if not failures else "partial",
            "instruments": len(instruments), "certified_rows": saved, "failures": failures}


def _recompute(row, ts_code: str) -> UnitCertification:
    primary = UnitObservation(
        ts_code=ts_code, trade_date=row.trade_date, close=row.primary_close,
        source=row.primary_source, raw_volume=row.primary_raw_volume, raw_amount=row.primary_raw_amount,
        converted_volume=row.converted_volume, converted_amount=row.converted_amount,
    )
    independent_contract = DOCUMENTED_ENDPOINT_FIELDS.get(row.independent_source) or {}
    independent_volume = (float(row.independent_raw_volume) * independent_contract.get("volume_to_shares", 1)
                          if row.independent_raw_volume is not None else None)
    independent_amount = (float(row.independent_raw_amount) * independent_contract.get("amount_to_cny", 1)
                          if row.independent_raw_amount is not None else None)
    independent = UnitObservation(
        ts_code=ts_code, trade_date=row.trade_date, close=row.independent_close,
        source=row.independent_source, raw_volume=row.independent_raw_volume,
        raw_amount=row.independent_raw_amount, converted_volume=independent_volume,
        converted_amount=independent_amount,
    )
    result = certify_absolute_units(primary, independent)
    if _observation_hash(primary) != row.primary_input_hash or _observation_hash(independent) != row.independent_input_hash:
        return UnitCertification(False, result.volume, result.amount, result.ratio_sanity_passed,
                                 (*result.reasons, "evidence_input_hash_mismatch"))
    if row.primary_upstream == row.independent_upstream:
        return UnitCertification(False, result.volume, result.amount, result.ratio_sanity_passed,
                                 (*result.reasons, "independent_observation_not_second_upstream"))
    return result


def certify_stored_history(db, instrument_id: int, bars) -> UnitCertification:
    bars = list(bars or [])
    if not bars:
        return UnitCertification(False, None, None, False, ("independent_same_day_observation_missing",))
    instrument = db.get(Instrument, instrument_id)
    rows = db.scalars(select(UnitCertificationEvidence).where(
        UnitCertificationEvidence.instrument_id == instrument_id,
        UnitCertificationEvidence.trade_date.in_([bar.trade_date for bar in bars]),
    )).all()
    by_binding = {(row.trade_date, row.adjust, row.daily_bar_quality_hash): row for row in rows}
    results = []
    reasons = []
    for bar in bars:
        row = by_binding.get((bar.trade_date, bar.adjust, bar.quality_hash))
        if row is None:
            stale = any(item.trade_date == bar.trade_date and item.adjust == bar.adjust for item in rows)
            reasons.append("evidence_binding_stale" if stale else "evidence_range_incomplete")
            continue
        result = _recompute(row, instrument.ts_code if instrument is not None else "unknown")
        results.append(result)
        reasons.extend(result.reasons)
        if not result.certified:
            reasons.append("stored_evidence_recomputation_failed")
    if len(results) != len(bars):
        reasons.append("evidence_range_incomplete")
    certified = len(results) == len(bars) and all(item.certified for item in results)
    last = results[-1] if results else None
    return UnitCertification(certified, last.volume if last else None, last.amount if last else None,
                             bool(results) and all(item.ratio_sanity_passed for item in results),
                             tuple(dict.fromkeys(reasons)))
