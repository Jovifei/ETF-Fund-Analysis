"""CLI integration preserves the execution lock and actual input checks."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.workspace.shadow_bundle import digest


@pytest.fixture
def cli():
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'run_local_compute.py'
    spec = importlib.util.spec_from_file_location('cadence_cli_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run_args(tmp_path):
    (tmp_path / '.local-live').touch()
    (tmp_path / 'research.sqlite3').touch()
    config = tmp_path / 'config' / 'live.json'
    config.parent.mkdir()
    config.write_text(json.dumps({'universe': ['510300.SH', '512480.SH']}))
    return SimpleNamespace(root=str(tmp_path), db=str(tmp_path / 'research.sqlite3'), config=str(config),
        profile='live', provider='public_composite', expected_sha='b' * 40, private_research=True,
        closed_session_research=False, no_upload=True, compute_only=False, skip_trade_day_check=True,
        board_only=False, cadence_mode='auto', prepare_base=True)


def test_auto_recovers_missing_base_with_full_pipeline(cli, run_args, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, 'get_current_git_sha', lambda: 'b' * 40)
    monkeypatch.setattr(cli, 'compute_local', lambda *a, **k: calls.append('full') or [{'status': 'succeeded'}])
    monkeypatch.setattr(cli, 'compute_local_fast', lambda *a, **k: pytest.fail('no valid base'))
    monkeypatch.setattr(cli, 'create_base_manifest', lambda *a, **k: {'validated': True})
    monkeypatch.setattr(cli, 'build_execution_lineage', lambda *a, **k: {'mode': k['mode'],
        'execution_hash': k['execution_hash'], 'config_file_hash': k['config_file_hash']})
    monkeypatch.setattr(cli, 'export_local_v2', lambda *a, **k: {'manifest': {'sequence': k['sequence']}})
    assert cli.cmd_run(run_args) == 0
    assert calls == ['full']
    assert json.loads((Path(run_args.root) / 'state' / 'settled_base.json').read_text()) == {'validated': True}


def test_fast_refuses_invalid_base_without_silent_recompute(cli, run_args, monkeypatch):
    run_args.cadence_mode = 'fast'
    monkeypatch.setattr(cli, 'get_current_git_sha', lambda: 'b' * 40)
    monkeypatch.setattr(cli, 'compute_local', lambda *a, **k: pytest.fail('strict fast must block'))
    with pytest.raises(ValueError, match='base unavailable'):
        cli.cmd_run(run_args)


def test_fast_rechecks_inputs_before_export_and_marks_optional_unavailable(cli, run_args, monkeypatch):
    state = Path(run_args.root) / 'state'
    state.mkdir()
    (state / 'settled_base.json').write_text('{}')
    checks = []
    monkeypatch.setattr(cli, 'get_current_git_sha', lambda: 'b' * 40)
    monkeypatch.setattr(cli, 'validate_base_manifest', lambda *a, **k: checks.append('base'))
    monkeypatch.setattr(cli, 'validate_fast_result', lambda *a, **k: checks.append('quotes'))
    monkeypatch.setattr(cli, 'compute_local_fast', lambda *a, **k: [{'status': 'succeeded', 'task_name': 'refresh_quotes'}])
    monkeypatch.setattr(cli, 'build_execution_lineage', lambda *a, **k: {'mode': k['mode'],
        'execution_hash': k['execution_hash'], 'config_file_hash': k['config_file_hash']})
    def export(*a, **k):
        assert k['unavailable_parts'] == []
        assert k['carry_optional'] is True
        assert checks[-2:] == ['base', 'quotes']
        assert k['execution_lineage']['mode'] == 'fast'
        assert len(k['execution_lineage']['execution_hash']) == 64
        return {'manifest': {'sequence': k['sequence']}}
    monkeypatch.setattr(cli, 'export_local_v2', export)
    assert cli.cmd_run(run_args) == 0


@pytest.mark.parametrize('field,value', [('no_upload', True), ('compute_only', True),
                                        ('board_only', True), ('expected_sha', 'a' * 40)])
def test_dispatch_rejects_non_delivery_or_wrong_source(cli, run_args, monkeypatch, field, value):
    run_args.no_upload = False
    setattr(run_args, field, value)
    monkeypatch.setattr(cli, 'get_current_git_sha', lambda: 'b' * 40)
    with pytest.raises(ValueError, match='approved live source'):
        cli.cmd_dispatch(run_args)


@pytest.mark.parametrize('change', ['revoke', 'runtime_config'])
def test_pending_replay_rechecks_current_permissions_and_entire_config(cli, run_args, monkeypatch, change):
    from datetime import datetime, timedelta, timezone
    from app.utils.hashing import stable_hash
    from app.workspace import local_dispatch
    from app.workspace.local_display_contract import compute_parts_hashes
    run_args.no_upload = False
    run_args.sync_url = 'https://etf.joviluma.com/api/shadow/sync'
    monkeypatch.setattr(cli, 'get_current_git_sha', lambda: 'b' * 40)
    cfg, settings, execution, _ = cli.read_execution(run_args)
    config_hash = stable_hash(settings.load_strategy())
    now = datetime.now(timezone.utc)
    parts = {'overview': {'rows': []}, 'details': {}, 'charts': {}, 'sectors': {'sectors': []}}
    manifest = {'contract_version': 'local-display-v2', 'code_sha': 'b'*40, 'config_hash': config_hash,
        'sequence': 12, 'universe': cfg['universe'], 'generated_at': now.isoformat(),
        'expires_at': (now+timedelta(hours=2)).isoformat(), 'actionable': False,
        'parts_hashes': compute_parts_hashes(parts), 'execution_lineage': {
            'contract_version': 'local-execution-lineage-v1', 'mode': 'full', **execution,
            'base_input_hash': 'c'*64, 'quote_batch_hash': 'd'*64}}
    outbox = Path(run_args.root) / 'outbox'
    outbox.mkdir()
    (outbox / 'bundle_12.json').write_text(json.dumps({'manifest': manifest, 'parts': parts}))
    attempt = {'slot_id': now.astimezone(settings.timezone).date().isoformat()+' 13:55',
               'bundle_file': 'bundle_12.json', 'bundle_id': digest(manifest)}
    def dispatch(root, identity, **hooks):
        assert identity['config_hash'] == config_hash  # Strategy hash alone cannot detect this change.
        changed = {**cfg, 'provider_admission': {'status': 'REVOKED'}} if change == 'revoke' else {**cfg, 'cadence_note': 'changed'}
        Path(run_args.config).write_text(json.dumps(changed))
        expected = 'current provider admission blocked' if change == 'revoke' else 'execution configuration mismatch'
        with pytest.raises(ValueError, match=expected):
            hooks['replay'](attempt=attempt, on_receipt=lambda *a: pytest.fail('must not upload'))
        return 1
    monkeypatch.setattr(local_dispatch, 'dispatch_once', dispatch)
    assert cli.cmd_dispatch(run_args) == 1
    assert not (Path(run_args.root) / 'config' / 'producer_auth.json').exists()


def test_full_mode_keeps_partial_market_context_and_flags_failed_sectors(cli, run_args, monkeypatch):
    run_args.cadence_mode = 'full'
    monkeypatch.setattr(cli, 'get_current_git_sha', lambda: 'b' * 40)
    monkeypatch.setattr(cli, 'compute_local', lambda *a, **k: [
        {'status': 'partial', 'task_name': 'refresh_market_context', 'required': False, 'observed': 6},
        {'status': 'failed', 'task_name': 'refresh_sector_snapshots', 'required': False},
        {'status': 'succeeded', 'task_name': 'refresh_decision_board'}])
    monkeypatch.setattr(cli, 'create_base_manifest', lambda *a, **k: {'validated': True})
    monkeypatch.setattr(cli, 'build_execution_lineage', lambda *a, **k: {'mode': k['mode'],
        'execution_hash': k['execution_hash'], 'config_file_hash': k['config_file_hash']})
    def export(*a, **k):
        assert k['unavailable_parts'] == ['sectors']
        assert k['carry_optional'] is False
        return {'manifest': {'sequence': k['sequence']}}
    monkeypatch.setattr(cli, 'export_local_v2', export)
    assert cli.cmd_run(run_args) == 0


@pytest.mark.parametrize('failure_stage', ['pre_upload_validation', 'transport_receipt'])
def test_upload_failure_reports_actual_safe_diagnostic(cli, run_args, monkeypatch, failure_stage):
    from app.workspace import shadow_client
    run_args.no_upload = False
    run_args.cadence_mode = 'full'
    events = []
    run_args._on_diagnostic = lambda phase, **event: events.append({'phase': phase, **event})
    monkeypatch.setattr(cli, 'get_current_git_sha', lambda: 'b' * 40)
    monkeypatch.setattr(cli, 'compute_local', lambda *a, **k: [{'status': 'succeeded'}])
    monkeypatch.setattr(cli, 'create_base_manifest', lambda *a, **k: {'validated': True})
    checks = []
    original_read = cli.read_execution
    def read(args):
        checks.append('check')
        if len(checks) == 3 and failure_stage == 'pre_upload_validation':
            raise TypeError('secret=private-payload https://private.invalid')
        return original_read(args)
    monkeypatch.setattr(cli, 'read_execution', read)
    monkeypatch.setattr(cli, 'build_execution_lineage', lambda *a, **k: {})
    monkeypatch.setattr(cli, 'export_local_v2', lambda *a, **k: {'manifest': {'sequence': k['sequence']}})
    def upload(*a):
        assert failure_stage == 'transport_receipt', 'validation must block transport'
        raise TimeoutError('secret=private-payload https://private.invalid')
    monkeypatch.setattr(shadow_client, 'upload_bundle_auto', upload)
    # Synthetic authentication is confined to pytest's temporary root.
    (Path(run_args.root) / 'config' / 'producer_auth.json').write_text(json.dumps({
        'producer_token': 'test-only', 'key_id': 'test-only', 'signing_secret': 'test-only'}))
    for key in ('SHADOW_PRODUCER_TOKEN', 'SHADOW_SIGNING_KEY_ID', 'SHADOW_SIGNING_SECRET'):
        monkeypatch.setenv(key, 'test-only')
    assert cli.cmd_run(run_args) == 1
    failed = [event for event in events if event['status'] == 'failed']
    assert len(failed) == 1
    assert failed[0]['phase'] == failure_stage
    assert failed[0]['error_type'] == ('TypeError' if failure_stage == 'pre_upload_validation' else 'TimeoutError')
    assert failed[0]['reason'] == f'{failure_stage}_failed'
    assert failed[0]['duration_seconds'] >= 0
    assert 'private-payload' not in str(events)
    assert {'base_validation', 'projection_export', 'bundle_write'} <= {event['phase'] for event in events}


def test_dispatch_cli_persists_first_upload_error_through_real_ledger(cli, run_args, monkeypatch, capsys):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from app.utils.hashing import stable_hash
    from app.workspace import local_dispatch, shadow_client
    from app.workspace.local_job_ledger import LocalJobLedger
    at = datetime(2026, 10, 16, 16, 10, tzinfo=ZoneInfo('Asia/Shanghai'))
    run_args.no_upload = False
    run_args.cadence_mode = 'full'
    monkeypatch.setattr(cli, 'get_current_git_sha', lambda: 'b' * 40)
    monkeypatch.setattr(cli, 'compute_local', lambda *a, **k: [{'status': 'succeeded'}])
    monkeypatch.setattr(cli, 'create_base_manifest', lambda *a, **k: {'validated': True})
    monkeypatch.setattr(cli, 'build_execution_lineage', lambda *a, **k: {
        'contract_version': 'local-execution-lineage-v1', 'mode': k['mode'],
        'execution_hash': k['execution_hash'], 'config_file_hash': k['config_file_hash'],
        'base_input_hash': 'c'*64, 'quote_batch_hash': 'd'*64})
    def export(settings, **kwargs):
        return {'manifest': {'contract_version': 'local-display-v2', 'sequence': kwargs['sequence'],
            'code_sha': kwargs['code_sha'], 'config_hash': stable_hash(settings.load_strategy()),
            'universe': kwargs['universe'], 'generated_at': at.isoformat(),
            'expires_at': (at + timedelta(hours=2)).isoformat(), 'execution_lineage': kwargs['execution_lineage']}}
    monkeypatch.setattr(cli, 'export_local_v2', export)
    (Path(run_args.root) / 'config' / 'producer_auth.json').write_text(json.dumps({
        'producer_token': 'test-only', 'key_id': 'test-only', 'signing_secret': 'test-only'}))
    for key in ('SHADOW_PRODUCER_TOKEN', 'SHADOW_SIGNING_KEY_ID', 'SHADOW_SIGNING_SECRET'):
        monkeypatch.setenv(key, 'test-only')
    def upload(*a):
        raise TypeError('private-payload must not persist')
    monkeypatch.setattr(shadow_client, 'upload_bundle_auto', upload)
    dispatch_once = local_dispatch.dispatch_once
    def dispatch(root, identity, **kwargs):
        kwargs.update(calendar=SimpleNamespace(decision=lambda day: SimpleNamespace(verified=True, is_trade_day=True)),
                      now=lambda: at)
        return dispatch_once(root, identity, **kwargs)
    monkeypatch.setattr(local_dispatch, 'dispatch_once', dispatch)
    assert cli.cmd_dispatch(run_args) == 1
    summary = LocalJobLedger(Path(run_args.root)).summary()
    upload_job = next(job for job in summary['jobs'] if job['job_name'] == 'upload_1')
    assert upload_job['details'] == {'error_type': 'TypeError', 'failure_stage': 'transport_receipt',
                                     'reason': 'transport_receipt_failed'}
    assert summary['attempts'][0]['status'] == 'EXPORTED'
    assert len(summary['diagnostics']) == 6
    assert 'private-payload' not in str(summary) + capsys.readouterr().out


def test_diagnostic_elapsed_uses_monotonic_clock_and_sanitizes_custom_error(cli, monkeypatch):
    events = []
    ticks = iter([500.0, 501.75])
    monkeypatch.setattr(cli, 'monotonic', lambda: next(ticks))
    args = SimpleNamespace(_on_diagnostic=lambda phase, **event: events.append(event))
    unsafe_type = type('private-payload', (TimeoutError,), {})
    with pytest.raises(TimeoutError):
        with cli.phase_diagnostic(args, 'transport_receipt'):
            raise unsafe_type('private-body')
    assert events == [{'status': 'failed', 'duration_seconds': 1.75,
                      'error_type': 'TimeoutError', 'reason': 'transport_receipt_failed'}]


def test_dispatch_exit_zero_does_not_claim_daily_acceptance(cli, run_args, monkeypatch, capsys):
    from app.workspace import local_dispatch
    run_args.no_upload = False
    monkeypatch.setattr(cli, 'get_current_git_sha', lambda: 'b' * 40)
    monkeypatch.setattr(local_dispatch, 'dispatch_once', lambda *a, **k: 0)
    assert cli.cmd_dispatch(run_args) == 0
    summary = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert summary['status'] == 'dispatch_finished' and summary['exit_code'] == 0
    assert summary['daily_acceptance'] == 'NOT_EVALUATED'
