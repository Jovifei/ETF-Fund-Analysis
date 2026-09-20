from datetime import date

from app.models import DailyBar, Instrument, ProviderAudit, UnitCertificationEvidence
from app.providers.composite import CompositeProvider
from app.providers.types import BarRecord
from app.providers.unit_certification import UnitObservation
from app.services.unit_evidence_service import collect_unit_evidence, certify_stored_history, record_unit_evidence


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


def test_audited_collection_persists_two_real_upstreams(db_session):
    instrument = Instrument(ts_code="598883.SH", symbol="598883", name="证据采集", enabled=True)
    db_session.add(instrument)
    db_session.flush()
    day = date(2026, 9, 18)
    bar = _bar(instrument.id, day, "collection-quality")
    db_session.add(bar)
    db_session.flush()

    class Source:
        def __init__(self, name, source, upstream, raw_volume, raw_amount, volume, amount):
            self.name, self.source, self.upstream = name, source, upstream
            self.raw_volume, self.raw_amount, self.volume, self.amount = raw_volume, raw_amount, volume, amount
        def fetch_daily_bars(self, ts_code, start_date, end_date):
            return [BarRecord(
                ts_code=ts_code, trade_date=day, open=1.2, high=1.21, low=1.19, close=1.2,
                volume=self.volume, amount=self.amount, source=self.source,
                raw_volume=self.raw_volume, raw_amount=self.raw_amount,
                source_upstream=self.upstream, endpoint_version="fixture:v1",
            )]

    provider = CompositeProvider([
        Source("tushare", "tushare:fund_daily:v101", "tushare", 20, 2.4, 2000, 2400),
        Source("akshare", "akshare:em:v101", "eastmoney", 20, 2400, 2000, 2400),
    ])
    result = collect_unit_evidence(db_session, provider, codes=[instrument.ts_code], run_id="evidence-run")
    assert result["certified_rows"] == 1
    assert db_session.query(UnitCertificationEvidence).filter_by(instrument_id=instrument.id).count() == 1
    assert db_session.query(ProviderAudit).filter_by(run_id="evidence-run", operation="certify_units").count() == 2


def test_price_only_bar_cannot_be_certified_from_raw_cross_source_observations(db_session):
    instrument = Instrument(ts_code="598884.SH", symbol="598884", name="价格仅证据", enabled=True)
    db_session.add(instrument)
    db_session.flush()
    bar = DailyBar(
        instrument_id=instrument.id, trade_date=date(2026, 9, 18), open=1.2,
        high=1.21, low=1.19, close=1.2, volume=None, amount=None,
        pct_change=0.1, adjust="none", source="akshare:sina:v101", quality_hash="price-only",
    )
    db_session.add(bar)
    db_session.flush()

    primary = UnitObservation(
        ts_code=instrument.ts_code, trade_date=bar.trade_date, close=1.2,
        source="akshare:sina:v101", raw_volume=20, raw_amount=2400,
    )
    independent = UnitObservation(
        ts_code=instrument.ts_code, trade_date=bar.trade_date, close=1.2,
        source="tencent:stock_zh_a_hist_tx:v101", raw_volume=2000, raw_amount=2400,
    )
    evidence = record_unit_evidence(
        db_session, instrument, bar, primary, independent,
        primary_upstream="sina", independent_upstream="tencent",
    )

    assert evidence.certified is False
    assert "daily_bar_quantity_missing" in evidence.reasons_json


def test_existing_evidence_is_recomputed_when_contract_changes(db_session):
    instrument = Instrument(ts_code="598885.SH", symbol="598885", name="重算证据", enabled=True)
    db_session.add(instrument)
    db_session.flush()
    bar = _bar(instrument.id, date(2026, 9, 18), "recompute-quality")
    bar.source = "tencent:stock_zh_a_hist_tx:v101"
    db_session.add(bar)
    db_session.flush()
    primary = UnitObservation(
        ts_code=instrument.ts_code, trade_date=bar.trade_date, close=1.2,
        source="tencent:stock_zh_a_hist_tx:v101", raw_volume=2000, raw_amount=2400,
    )
    independent = UnitObservation(
        ts_code=instrument.ts_code, trade_date=bar.trade_date, close=1.2,
        source="akshare:sina:v101", raw_volume=2000, raw_amount=2400,
    )

    first = record_unit_evidence(
        db_session, instrument, bar, primary, independent,
        primary_upstream="tencent", independent_upstream="sina",
    )
    first.certified = False
    db_session.flush()
    second = record_unit_evidence(
        db_session, instrument, bar, primary, independent,
        primary_upstream="tencent", independent_upstream="sina",
    )

    assert second.id == first.id
    assert second.certified is True
