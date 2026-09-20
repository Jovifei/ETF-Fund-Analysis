from datetime import date

from app.models import DailyBar, Instrument, UnitCertificationEvidence
from app.providers.unit_certification import UnitObservation
from app.services.unit_evidence_service import certify_stored_history, record_unit_evidence


def _observation(source, day, volume=20.0, amount=2.4, ts_code="598881.SH"):
    multiplier = 1000 if source.startswith("tushare:") else 1
    volume_multiplier = 100 if source in {"tushare:fund_daily:v101", "akshare:em:v101"} else 1
    return UnitObservation(
        ts_code=ts_code, trade_date=day, close=1.2, source=source,
        raw_volume=volume, raw_amount=amount,
        converted_volume=volume * volume_multiplier,
        converted_amount=amount * multiplier,
    )


def _bar(instrument_id, day, quality_hash):
    return DailyBar(
        instrument_id=instrument_id, trade_date=day, open=1.2, high=1.21,
        low=1.19, close=1.2, pre_close=1.19, volume=2000, amount=2400,
        pct_change=0.1, adjust="none", source="tushare:fund_daily:v101",
        quality_hash=quality_hash,
    )


def test_stored_evidence_rejects_same_upstream_partial_range_and_stale_bar(db_session):
    instrument = Instrument(ts_code="598881.SH", symbol="598881", name="证据测试一", enabled=True)
    db_session.add(instrument)
    db_session.flush()
    first = _bar(instrument.id, date(2026, 9, 17), "bar-hash-1")
    second = _bar(instrument.id, date(2026, 9, 18), "bar-hash-2")
    db_session.add_all([first, second])
    db_session.flush()

    primary = _observation("tushare:fund_daily:v101", first.trade_date)
    disguised_same_upstream = _observation("tushare:mirror:v101", first.trade_date)
    rejected = record_unit_evidence(
        db_session, instrument, first, primary, disguised_same_upstream,
        primary_upstream="tushare", independent_upstream="tushare",
    )
    assert rejected.certified is False
    assert "independent_observation_not_second_upstream" in rejected.reasons_json

    independent = _observation("akshare:em:v101", first.trade_date, amount=2400.0)
    accepted = record_unit_evidence(
        db_session, instrument, first, primary, independent,
        primary_upstream="tushare", independent_upstream="eastmoney",
    )
    assert accepted.certified is True

    partial = certify_stored_history(db_session, instrument.id, [first, second])
    assert partial.certified is False
    assert "evidence_range_incomplete" in partial.reasons

    first.quality_hash = "bar-hash-updated"
    stale = certify_stored_history(db_session, instrument.id, [first])
    assert stale.certified is False
    assert "evidence_binding_stale" in stale.reasons


def test_stored_evidence_recomputes_units_and_certifies_complete_range(db_session):
    instrument = Instrument(ts_code="598882.SH", symbol="598882", name="证据测试二", enabled=True)
    db_session.add(instrument)
    db_session.flush()
    bars = []
    for index, day in enumerate((date(2026, 9, 17), date(2026, 9, 18)), start=1):
        bar = _bar(instrument.id, day, f"quality-{index}")
        bar.source = "tushare:fund_daily:v101"
        db_session.add(bar)
        db_session.flush()
        primary = _observation("tushare:fund_daily:v101", day, ts_code=instrument.ts_code)
        independent = _observation("akshare:em:v101", day, amount=2400.0, ts_code=instrument.ts_code)
        record_unit_evidence(
            db_session, instrument, bar, primary, independent,
            primary_upstream="tushare", independent_upstream="eastmoney",
        )
        bars.append(bar)

    result = certify_stored_history(db_session, instrument.id, bars)
    assert result.certified is True
    assert result.volume == 2000.0
    assert result.amount == 2400.0

    evidence = db_session.query(UnitCertificationEvidence).filter_by(instrument_id=instrument.id).first()
    evidence.primary_raw_volume = 21.0
    db_session.flush()
    tampered = certify_stored_history(db_session, instrument.id, bars)
    assert tampered.certified is False
    assert "evidence_input_hash_mismatch" in tampered.reasons
