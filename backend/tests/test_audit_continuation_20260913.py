"""Regression obligations from CODE_AUDIT_BLOCKERS_20260912, not live certification."""
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4
import numpy as np
import pytest
from sqlalchemy import select
from app.core.config import get_settings
from app.models import IndicatorSnapshot
from app.providers.data_contract import assess_history, finite, row_units_verified
from app.services.decision_board_service import DecisionBoardService
from app.services.signal_grade_service import SignalGradeService
from app.utils.indicator_state import classify_ma
from test_audit_data_20260912 import bar, frame
from test_v103_history import instrument

@pytest.mark.parametrize('value',[None,True,'oops',float('nan'),float('inf'),{},[]])
def test_malformed_numeric_input_fails_closed(value):
    assert not finite(value)

def test_unknown_unit_source_not_implicitly_qualified():
    row=bar(source='brand-new-provider')
    assert not row_units_verified(row)
    assert 'unknown_endpoint_units_unverified' in assess_history([row])
    assert row_units_verified(bar(source='akshare:em:v101'))

@pytest.mark.parametrize('field',['version','config_hash','feature_schema_version'])
def test_previous_formula_mismatch_not_compared(db_session,field):
    inst=instrument(db_session)
    values=dict(instrument_id=inst.id,version='unit-v1',config_hash='a'*64,
        feature_schema_version='schema-v1',values_json={'ma20':2},technical_score=50,
        risk_score=50,trend_label='test',data_quality=1,input_hash='b'*64)
    prev=IndicatorSnapshot(**values,as_of_date=date(2026,9,10))
    curr=IndicatorSnapshot(**{**values,field:'different'},as_of_date=date(2026,9,11))
    db_session.add_all([prev,curr]);db_session.flush()
    assert inst.id not in SignalGradeService._previous_indicators(db_session,{inst.id:curr})
    assert inst.id not in DecisionBoardService._previous_indicator_values(db_session,{inst.id:curr})
    db_session.rollback()

def test_same_formula_comparison_exposes_date(db_session):
    from app.utils.indicator_history import previous_values
    inst=instrument(db_session)
    kw=dict(instrument_id=inst.id,version='v1',config_hash='c'*64,feature_schema_version='f1',
            technical_score=50,risk_score=50,trend_label='test',data_quality=1,input_hash='d'*64)
    prev=IndicatorSnapshot(**kw,as_of_date=date(2026,9,10),values_json={'ma20':1})
    cur=IndicatorSnapshot(**kw,as_of_date=date(2026,9,11),values_json={'ma20':2})
    db_session.add_all([prev,cur]);db_session.flush()
    assert previous_values(db_session,cur)['_as_of_date']=='2026-09-10'
    assert previous_values(db_session,cur)['ma20']==1
    db_session.rollback()

def test_ma_arrow_does_not_change_meaning_when_previous_present():
    values={'close':1,'ma5':2,'ma10':2.1,'ma20':2.2,'ma30':2.3}
    previous={key:0.1 for key in values}
    no_previous=classify_ma(values,None)
    with_previous=classify_ma(values,previous)
    assert no_previous['arrows']==with_previous['arrows']
    assert {a['dir'] for a in no_previous['arrows']}=={'down'}
    assert with_previous['arrow_basis']=='close_vs_ma'

def test_nondefault_volume_window_uses_raw_input_mask():
    from app.utils.feature_store import build_feature_frame
    cfg=get_settings().load_strategy()['indicator']; cfg={**cfg,'volume':{**cfg.get('volume',{}),'window':30}}
    raw=frame();raw.loc[175,'amount']=np.nan;raw.loc[175,'volume']=np.nan
    rich=build_feature_frame(raw,cfg).frame
    assert np.isnan(rich.iloc[-1]['volume_ratio'])
    assert np.isnan(rich.iloc[-1]['amount_ratio'])
    assert np.isfinite(rich.iloc[-1]['ma20'])

def test_anomaly_count_is_explicit_and_partitioned(db_session):
    inst=instrument(db_session,missing_volume=True)
    settings=get_settings().model_copy(update={'market_provider':'akshare'})
    data=DecisionBoardService(settings).refresh(db_session).payload
    assert data['counts']['数据异常']==len(data['groups']['数据异常'])
    assert sum(data['counts'].values())==len(data['rows'])
    db_session.rollback()
