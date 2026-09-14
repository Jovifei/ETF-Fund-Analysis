"""Runtime diagnostics never dump environments or claim to identify OOM by code 137."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script():
    spec = importlib.util.spec_from_file_location('runtime_diagnostics', ROOT / 'scripts/runtime_diagnostics.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docker_projection_is_bounded_and_has_no_environment(monkeypatch):
    module = load_script()
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            'name': '/etf-scheduler', 'exit_code': 137, 'oom_killed': False,
            'restart_count': 80, 'running': True, 'memory_limit_bytes': 0,
            'started_at': '', 'finished_at': '', 'restart_policy': 'unless-stopped',
        }), stderr='not retained')
    monkeypatch.setattr(module.subprocess, 'run', run)
    report = module.inspect_containers(['etf-scheduler'])
    assert report['containers'][0]['exit_code'] == 137
    assert report['root_cause'] == 'not_determined'
    assert report['writes_performed'] is False
    assert '.Config.Env' not in str(calls) and 'not retained' not in str(report)
    assert calls[0][1]['timeout'] <= 15


@pytest.mark.parametrize('name', ['--help', '../x', 'x; cat .env', '', 'a'*129])
def test_invalid_container_identity_never_runs_a_command(name, monkeypatch):
    module = load_script()
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: pytest.fail('must not run'))
    with pytest.raises(ValueError):
        module.inspect_containers([name])


def test_missing_docker_is_explicit_and_not_an_oom_conclusion(monkeypatch):
    module = load_script()
    def unavailable(*a, **k):
        raise FileNotFoundError('sensitive details')
    monkeypatch.setattr(module.subprocess, 'run', unavailable)
    result = module.inspect_containers(['scheduler'])
    assert result['containers'][0]['status'] == 'unavailable'
    assert 'sensitive' not in json.dumps(result)
    assert result['root_cause'] == 'not_determined'


def test_stage_sample_has_only_resource_and_identity_fields():
    from app.services.runtime_observation import stage_sample
    sample = stage_sample('refresh_decision_board', 'started', elapsed_seconds=0)
    assert sample['stage'] == 'refresh_decision_board'
    assert sample['state'] == 'started'
    assert sample['pid'] > 0
    assert not ({'environment', 'database_url', 'payload', 'token'} & sample.keys())
