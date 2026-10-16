"""CLI integration preserves the execution lock and actual input checks."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


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
    def export(*a, **k):
        assert k['unavailable_parts'] == ['market_context', 'sectors']
        assert checks[-2:] == ['base', 'quotes']
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
