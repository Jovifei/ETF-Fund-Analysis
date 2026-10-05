from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest
from app.core.config import get_settings
from app.services.factor_analysis_service import FactorAnalysisService
from app.services.global_model_research_service import GlobalModelResearchService
from app.utils.hashing import stable_hash
from app.utils.historical_classification_contract import current_metadata_classification_contract
from app.workspace.read_model import factor_view
from test_report_artifact_contract import _factor_payload, _write_report


def _contract():
    return current_metadata_classification_contract([
        SimpleNamespace(ts_code='510300.SH', theme_l1='宽基', theme_l2=None),
        SimpleNamespace(ts_code='512170.SH', theme_l1='医药', theme_l2='医疗'),
    ])


def test_classification_identity_binds_codes_and_both_labels_without_order_dependence():
    rows = [
        SimpleNamespace(ts_code='510300.SH', theme_l1='宽基', theme_l2=None),
        SimpleNamespace(ts_code='512170.SH', theme_l1='医药', theme_l2='医疗'),
    ]
    original = current_metadata_classification_contract(rows)
    assert stable_hash(original) == stable_hash(current_metadata_classification_contract(reversed(rows)))
    for attribute, changed in [('ts_code', '510500.SH'), ('theme_l1', '科技'), ('theme_l2', '创新药')]:
        altered = deepcopy(rows)
        setattr(altered[0], attribute, changed)
        assert stable_hash(original) != stable_hash(current_metadata_classification_contract(altered))
    assert original['instrument_classifications']['510300.SH']['theme_l2'] is None
    assert original['theme_point_in_time_qualified'] is False
    assert original['qualification'] == 'UNKNOWN'


@pytest.mark.parametrize('defect', ['missing', 'hash', 'version', 'snapshot', 'count', 'pit_claim', 'source', 'policy', 'label_type', 'count_bool', 'empty', 'wrong_codes'])
def test_factor_current_read_rejects_unbound_or_invalid_classification(db_session, defect):
    settings = get_settings()
    payload, metadata = _factor_payload(settings)
    contract = _contract()
    payload['panel']['classification_contract'] = contract
    metadata['classification_contract_hash'] = stable_hash(contract)
    payload['panel']['universe_contract']['instrument_codes'] = sorted(contract['instrument_classifications'])
    metadata['universe_contract_hash'] = stable_hash(payload['panel']['universe_contract'])
    if defect == 'missing':
        payload['panel'].pop('classification_contract')
        metadata.pop('classification_contract_hash')
    elif defect == 'hash':
        metadata['classification_contract_hash'] = 'mismatched'
    else:
        if defect == 'version':
            contract['version'] = 'historical-classification-obsolete'
        elif defect == 'snapshot':
            contract.pop('instrument_classifications', None)
        elif defect == 'count':
            contract['instrument_count'] += 1
        elif defect == 'pit_claim':
            contract['theme_point_in_time_qualified'] = True
        elif defect == 'source':
            contract['source'] = 'unbound-other-source'
        elif defect == 'policy':
            contract['historical_projection_policy'] = 'historically_qualified'
        elif defect == 'label_type':
            contract['instrument_classifications']['510300.SH']['theme_l1'] = {'unexpected': 'object'}
        elif defect == 'count_bool':
            contract['instrument_count'] = True
        elif defect == 'empty':
            contract['instrument_classifications'] = {}
            contract['instrument_count'] = 0
        else:
            labels = contract['instrument_classifications'].pop('510300.SH')
            contract['instrument_classifications']['510500.SH'] = labels
        metadata['classification_contract_hash'] = stable_hash(contract)
    _write_report(db_session, report_type='factor_effectiveness', payload=payload,
                  metadata=metadata, as_of_time=datetime.now(settings.timezone))
    result = factor_view(db_session, settings)
    assert result['report_state'] == 'incompatible'
    assert result['report'] is None
    assert 'classification' in result['report_reason']
    assert result['actionable'] is False
    db_session.rollback()


def test_factor_current_read_preserves_valid_classification_evidence(db_session):
    settings = get_settings()
    payload, metadata = _factor_payload(settings)
    contract = _contract()
    payload['panel']['classification_contract'] = contract
    metadata['classification_contract_hash'] = stable_hash(contract)
    payload['panel']['universe_contract']['instrument_codes'] = sorted(contract['instrument_classifications'])
    metadata['universe_contract_hash'] = stable_hash(payload['panel']['universe_contract'])
    _write_report(db_session, report_type='factor_effectiveness', payload=payload,
                  metadata=metadata, as_of_time=datetime.now(settings.timezone))
    result = factor_view(db_session, settings)
    assert result['report_state'] == 'current'
    assert result['report']['panel']['classification_contract'] == contract
    assert result['actionable'] is False
    db_session.rollback()


def test_global_research_rejects_nonempty_but_unbound_classification(db_session, monkeypatch):
    panel = pd.DataFrame({'trade_date': [datetime(2026, 1, 1).date()], 'ts_code': ['510300.SH']})
    panel.attrs['universe_contract'] = {'version': 'fixture'}
    panel.attrs['classification_contract'] = {'version': 'not-empty-but-unbound'}
    monkeypatch.setattr(FactorAnalysisService, '_panel', lambda self, db: panel)
    service = GlobalModelResearchService()
    monkeypatch.setattr(service, '_backend', lambda: 'stub')
    with pytest.raises(ValueError, match='classification'):
        service.run(db_session)
    db_session.rollback()


def test_classification_builder_rejects_duplicate_or_invalid_identity():
    first = SimpleNamespace(ts_code='510300.SH', theme_l1=None, theme_l2=None)
    with pytest.raises(ValueError, match='duplicate'):
        current_metadata_classification_contract([first, first])
    with pytest.raises(ValueError, match='code'):
        current_metadata_classification_contract([SimpleNamespace(ts_code=' ' )])


def test_crosscheck_rejects_current_version_without_bound_classification_rows(db_session):
    from app.services.crosscheck_engine import CrosscheckEngine
    from app.utils.universe_contract import UNIVERSE_CONTRACT_VERSION

    settings = get_settings()
    contract = _contract()
    contract.pop('instrument_classifications')
    payload = {
        'report_type': 'rotation_backtest',
        'data': {
            'quantity_contract': 'mock_passthrough',
            'universe_contract': {'version': UNIVERSE_CONTRACT_VERSION, 'instrument_codes': ['510300.SH', '512170.SH']},
            'classification_contract': contract,
        },
    }
    _write_report(db_session, report_type='rotation_backtest', payload=payload,
                  as_of_time=datetime.now(settings.timezone))
    result = CrosscheckEngine(settings).run(db_session)
    assert result['status'] == 'skipped'
    assert result['reason'] == 'primary_classification_contract_missing'
    assert 'classification_snapshot_missing' in result['classification_issues']
    db_session.rollback()


@pytest.mark.parametrize('codes', [[], ['511000.SH']])
def test_global_classification_must_cover_actual_panel_codes(db_session, monkeypatch, codes):
    panel = pd.DataFrame({'trade_date': [datetime(2026, 1, 1).date()], 'ts_code': ['510300.SH']})
    panel.attrs['universe_contract'] = {'version': 'fixture'}
    panel.attrs['classification_contract'] = current_metadata_classification_contract(
        SimpleNamespace(ts_code=code, theme_l1=None, theme_l2=None) for code in codes
    )
    monkeypatch.setattr(FactorAnalysisService, '_panel', lambda self, db: panel)
    service = GlobalModelResearchService()
    monkeypatch.setattr(service, '_backend', lambda: 'stub')
    with pytest.raises(ValueError, match='classification'):
        service.run(db_session)
    db_session.rollback()


def test_crosscheck_classification_must_match_primary_universe(db_session):
    from app.services.crosscheck_engine import CrosscheckEngine
    from app.utils.universe_contract import UNIVERSE_CONTRACT_VERSION

    settings = get_settings()
    payload = {
        'report_type': 'rotation_backtest',
        'data': {
            'quantity_contract': 'mock_passthrough',
            'universe_contract': {'version': UNIVERSE_CONTRACT_VERSION, 'instrument_codes': ['511000.SH']},
            'classification_contract': _contract(),
        },
    }
    _write_report(db_session, report_type='rotation_backtest', payload=payload,
                  as_of_time=datetime.now(settings.timezone))
    result = CrosscheckEngine(settings).run(db_session)
    assert result['status'] == 'skipped'
    assert result['reason'] == 'primary_classification_contract_missing'
    assert 'classification_instrument_coverage_mismatch' in result['classification_issues']
    db_session.rollback()


def test_classification_coverage_allows_only_explicit_panel_subset_policy():
    from app.utils.historical_classification_contract import classification_contract_issues

    contract = _contract()
    assert classification_contract_issues(contract, expected_codes=['510300.SH'], allow_superset=True) == []
    assert 'classification_instrument_coverage_mismatch' in classification_contract_issues(
        contract, expected_codes=['510300.SH'],
    )
    assert 'classification_expected_codes_invalid' in classification_contract_issues(
        contract, expected_codes=None,
    )
