"""Negative cases for the offline gate, not a live data qualification test."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/production_data_gate.py'
spec = importlib.util.spec_from_file_location('production_data_gate_negative', SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
NOW = datetime.fromisoformat('2026-09-15T14:35:00+08:00')


def valid():
    return {'schema_version': 'production-freshness-v2', 'captured_at': NOW.isoformat(),
        'source_tree': 'a' * 40, 'target_trade_date': '2026-09-14', 'calendar_verified': True,
        'expected_codes': ['510300.SH'],
        'expected_versions': {'indicator': 'ind-test', 'forecast': 'forecast-test',
                              'feature_schema': 'features-test', 'config_hash': 'b' * 64},
        'decision': {'target_trade_date': '2026-09-14', 'input_dates_verified': True,
                     'config_hash': 'b' * 64, 'generated_at': NOW.isoformat()},
        'items': [{'ts_code': '510300.SH', 'daily_latest': '2026-09-14', 'daily_rows': 300,
            'missing_volume': 0, 'missing_amount': 0,
            'ohlc_valid': True, 'price_basis_verified': True, 'units_verified': True,
            'history_blockers': [], 'indicator_latest': '2026-09-14',
            'indicator_version': 'ind-test', 'indicator_config_hash': 'b' * 64,
            'indicator_feature_schema': 'features-test', 'indicator_input_hash_verified': True,
            'forecast_latest': '2026-09-14', 'forecast_horizons': 4,
            'forecasts': [{'horizon': h, 'as_of_date': '2026-09-14',
                          'model_version': 'forecast-test', 'config_hash': 'b' * 64,
                          'feature_schema': 'features-test', 'input_hash_verified': True,
                          'values_valid': True} for h in (1, 3, 5, 10)],
            'quote_latest': '2026-09-15T14:34:00+08:00',
            'quote_realtime': True, 'quote_timestamp_verified': True}]}


def evaluate(data, **kwargs):
    return gate.evaluate_snapshot(data, now=NOW, **kwargs)


def test_complete_evidence_pass_is_never_actionability_or_deployment_approval():
    result = evaluate(valid(), require_realtime=True)
    assert result['status'] == 'pass'
    assert result['qualification_granted'] is False
    assert result['actionable'] is False
    assert result['deployment_approved'] is False


@pytest.mark.parametrize('key', ['missing_volume', 'missing_amount'])
@pytest.mark.parametrize('value', [None, -1, True, '0', 1.5])
def test_unknown_missing_counts_are_not_coerced_to_zero(key, value):
    data = valid(); data['items'][0][key] = value
    assert evaluate(data)['status'] == 'fail'


@pytest.mark.parametrize('key', ['ohlc_valid', 'price_basis_verified', 'units_verified', 'indicator_input_hash_verified'])
def test_missing_independent_evidence_blocks(key):
    data = valid(); del data['items'][0][key]
    assert evaluate(data)['status'] == 'fail'


def test_explicit_history_blocker_is_not_ignored():
    data = valid(); data['items'][0]['history_blockers'] = ['unexplained_price_discontinuity']
    assert evaluate(data)['status'] == 'fail'


@pytest.mark.parametrize('bad', ['tomorrow', '2026-02-30', '2026-09-16'])
def test_invalid_or_future_target_is_rejected_even_if_all_dates_match(bad):
    data = valid(); data['target_trade_date'] = bad
    for key in ('daily_latest','indicator_latest','forecast_latest'):
        data['items'][0][key] = bad
    assert evaluate(data)['status'] == 'fail'


def test_duplicate_or_missing_universe_is_not_complete():
    data = valid(); data['items'] *= 2
    assert evaluate(data)['status'] == 'fail'
    data = valid(); data['expected_codes'].append('512480.SH')
    assert evaluate(data)['status'] == 'fail'


@pytest.mark.parametrize('key', ['indicator_version', 'indicator_config_hash', 'indicator_feature_schema'])
def test_wrong_indicator_identity_rejected(key):
    data = valid(); data['items'][0][key] = 'obsolete'
    assert evaluate(data)['status'] == 'fail'


def test_four_forecasts_with_wrong_identities_do_not_pass():
    data = valid(); data['items'][0]['forecasts'][-1]['horizon'] = 20
    assert evaluate(data)['status'] == 'fail'


@pytest.mark.parametrize('key,value', [('as_of_date','2026-09-13'),('model_version','old'),('input_hash_verified',False),('values_valid',False)])
def test_each_horizon_has_own_validation(key, value):
    data = valid(); data['items'][0]['forecasts'][1][key] = value
    assert evaluate(data)['status'] == 'fail'


@pytest.mark.parametrize('stamp', ['2026-09-15T12:00:00+08:00', '2026-09-14T14:34:00+08:00', '2026-09-15T14:34:00'])
def test_strict_quote_age_session_and_timezone(stamp):
    data = valid(); data['items'][0]['quote_latest'] = stamp
    assert evaluate(data, require_realtime=True)['status'] == 'fail'


def test_stale_unverified_quotes_can_only_pass_research_checks():
    data=valid(); data['items'][0].update(quote_realtime=False,quote_timestamp_verified=False,quote_latest='2026-09-14T14:30:00+08:00')
    assert evaluate(data)['status'] == 'pass'
    assert evaluate(data,require_realtime=True)['status'] == 'fail'


@pytest.mark.parametrize('stamp', ['2026-09-15T13:00:00+08:00','2026-09-15T14:36:00+08:00'])
def test_stale_or_future_receipt_cannot_certify_now(stamp):
    data = valid(); data['captured_at'] = stamp
    assert evaluate(data)['status'] == 'fail'


def test_old_decision_or_unknown_schema_blocks():
    data = valid(); data['decision']['target_trade_date'] = '2026-09-13'
    assert evaluate(data)['status'] == 'fail'
    data = valid(); data.pop('schema_version')
    assert evaluate(data)['status'] == 'fail'


def test_invalid_code_is_not_reflected_into_report():
    data = valid(); data['items'][0]['ts_code'] = 'SECRET_DO_NOT_ECHO'
    result = evaluate(data)
    assert result['status'] == 'fail'
    assert 'SECRET_DO_NOT_ECHO' not in json.dumps(result)


def cli(tmp_path, text, output=None):
    source = tmp_path / 'input.json'; source.write_text(text, encoding='utf-8')
    target = output or tmp_path / 'new-result.json'
    p=subprocess.run([sys.executable,str(SCRIPT),'--input',str(source),'--output',str(target)],capture_output=True,text=True,timeout=15)
    return p, target


@pytest.mark.parametrize('text', ['{"items":[],"items":[]}', '{"items":NaN}', '[]'])
def test_cli_rejects_ambiguous_or_nonobject_json(tmp_path,text):
    p,_=cli(tmp_path,text)
    assert p.returncode == 2


def test_cli_never_overwrites_previous_evidence(tmp_path):
    target=tmp_path/'preserved.json';target.write_text('keep',encoding='utf-8')
    p,_=cli(tmp_path,json.dumps(valid()),target)
    assert p.returncode == 2 and target.read_text() == 'keep'


def test_cli_data_blocker_writes_report_and_exits_three(tmp_path):
    p, target=cli(tmp_path,json.dumps({'items': []}))
    assert p.returncode == 3
    assert json.loads(target.read_text())['status'] == 'fail'


def test_cli_oversized_input_rejected(tmp_path):
    p,_=cli(tmp_path,' '*(2_000_000+1)+'{}')
    assert p.returncode == 2


def test_current_session_history_cannot_pass_before_settlement():
    # Same-day daily close is not settled at 14:35 Shanghai.
    data=valid(); data['target_trade_date']='2026-09-15'
    data['decision']['target_trade_date']='2026-09-15'
    for key in ('daily_latest','indicator_latest','forecast_latest'):data['items'][0][key]='2026-09-15'
    for f in data['items'][0]['forecasts']:f['as_of_date']='2026-09-15'
    assert 'target_session_not_settled' in evaluate(data, require_realtime=True)['global_blockers']


def test_cli_rejects_named_pipe_without_waiting_for_a_writer(tmp_path):
    import os
    if not hasattr(os, 'mkfifo'):
        pytest.skip('POSIX named pipe boundary')
    source=tmp_path/'pipe';os.mkfifo(source)
    result=subprocess.run([sys.executable,str(SCRIPT),'--input',str(source),'--output',str(tmp_path/'new.json')],capture_output=True,timeout=5)
    assert result.returncode == 2
