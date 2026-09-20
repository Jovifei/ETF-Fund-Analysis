from __future__ import annotations

from sqlalchemy import select

from app.models import Instrument, UnitCertificationEvidence
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
    if not primary_upstream or not independent_upstream or primary_upstream == independent_upstream:
        reasons.append("independent_observation_not_second_upstream")
    certified = result.certified and "independent_observation_not_second_upstream" not in reasons
    primary_units = _units(primary.source)
    independent_units = _units(independent.source)
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
        primary_input_hash=_observation_hash(primary), independent_input_hash=_observation_hash(independent),
        certified=certified, reasons_json=list(dict.fromkeys(reasons)),
    )
    db.add(row)
    db.flush()
    return row


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
