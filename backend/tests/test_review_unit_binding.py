"""Review R1: rejected unit evidence may never self-promote on a read."""
from datetime import date
from uuid import uuid4
import pytest
from app.models import DailyBar, Instrument
from app.providers.types import BarRecord
from app.providers.unit_certification import UnitObservation
from app.services.unit_evidence_service import certify_stored_history, collect_unit_evidence, record_unit_evidence

@pytest.fixture
def evidence_case(db_session):
    inst = Instrument(ts_code='599911.SH', symbol='599911', name=uuid4().hex, enabled=True)
    db_session.add(inst)
    db_session.flush()
    row = DailyBar(instrument_id=inst.id, trade_date=date(2026, 9, 18),
                   open=1.2, high=1.21, low=1.19, close=1.2,
                   volume=2000, amount=2400, adjust='none',
                   source='tushare:fund_daily:v101', quality_hash=uuid4().hex)
    db_session.add(row)
    db_session.flush()
    primary = UnitObservation(inst.ts_code, row.trade_date, 1.2,
                              'tushare:fund_daily:v101', 20.0, 2.4, 2000.0, 2400.0)
    other = UnitObservation(inst.ts_code, row.trade_date, 1.2,
                            'akshare:em:v101', 20.0, 2400.0, 2000.0, 2400.0)
    yield inst, row, primary, other
    db_session.rollback()


@pytest.mark.parametrize('field,value', [('volume', None), ('amount', None),
                                         ('volume', 2500.0), ('amount', 3000.0)])
def test_rejected_bar_binding_cannot_be_promoted_during_recomputation(db_session, evidence_case, field, value):
    inst, row, primary, other = evidence_case
    setattr(row, field, value)
    saved = record_unit_evidence(db_session, inst, row, primary, other,
                                primary_upstream='tushare', independent_upstream='eastmoney')
    assert saved.certified is False
    check = certify_stored_history(db_session, inst.id, [row])
    assert check.certified is False
    assert any(reason.startswith('daily_bar_') for reason in check.reasons)


def test_recompute_rechecks_actual_bar_not_just_stored_hash(db_session, evidence_case):
    inst, row, primary, other = evidence_case
    saved = record_unit_evidence(db_session, inst, row, primary, other,
                                primary_upstream='tushare', independent_upstream='eastmoney')
    assert saved.certified is True
    row.volume = 3000  # Simulates an import bug that failed to update quality_hash.
    assert certify_stored_history(db_session, inst.id, [row]).certified is False


def test_collection_without_second_source_is_not_succeeded(db_session, evidence_case):
    inst, row, _, _ = evidence_case
    class OneSource:
        name = 'tushare'
        def fetch_daily_bars(self, code, start, end):
            return [BarRecord(code, row.trade_date, 1.2, 1.21, 1.19, 1.2,
                              volume=2000, amount=2400, raw_volume=20, raw_amount=2.4,
                              source=row.source, source_upstream='tushare')]
    result = collect_unit_evidence(db_session, OneSource(), codes=[inst.ts_code])
    assert result['certified_rows'] == 0
    assert result['status'] != 'succeeded'
    assert result['failures']
    assert result['expected_rows'] == 1



def test_identical_values_from_another_instrument_cannot_reuse_evidence(db_session, evidence_case):
    from types import SimpleNamespace
    inst, row, primary, other = evidence_case
    record_unit_evidence(db_session, inst, row, primary, other,
                         primary_upstream='tushare', independent_upstream='eastmoney')
    foreign = SimpleNamespace(**{key: getattr(row,key) for key in
        ('trade_date','adjust','quality_hash','source','close','volume','amount')}, instrument_id=inst.id+999)
    assert certify_stored_history(db_session, inst.id, [foreign]).certified is False
