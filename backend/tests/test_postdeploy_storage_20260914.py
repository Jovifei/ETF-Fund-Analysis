import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('free,expected', [(50, 0), (14, 0), (8, 3), (1, 3)])
def test_reported_92_percent_is_blocked_not_silently_cleaned(tmp_path, monkeypatch, free, expected):
    module = load('storage_preflight')
    monkeypatch.setattr(module.shutil, 'disk_usage', lambda _: SimpleNamespace(total=100 * module.GIB, free=free * module.GIB))
    monkeypatch.setattr(module.os, 'statvfs', lambda _: SimpleNamespace(f_files=1000, f_favail=500), raising=False)
    result = module.inspect_storage([tmp_path])
    assert result['exit_code'] == expected
    assert not result['writes_performed'] and not result['deletion_performed']
    assert not result['deployment_approved']
    assert list(tmp_path.iterdir()) == []


def test_inode_exhaustion_blocks_even_when_bytes_available(tmp_path, monkeypatch):
    module = load('storage_preflight')
    monkeypatch.setattr(module.shutil, 'disk_usage', lambda _: SimpleNamespace(total=100 * module.GIB, free=80 * module.GIB))
    monkeypatch.setattr(module.os, 'statvfs', lambda _: SimpleNamespace(f_files=1000, f_favail=1), raising=False)
    assert module.inspect_storage([tmp_path])['exit_code'] == 3


def test_unmounted_path_is_unknown_not_a_parent_disk_success(tmp_path):
    result = load('storage_preflight').inspect_storage([tmp_path / 'absent-mount'])
    assert result['exit_code'] == 2 and not result['capacity_ready']
    assert not (tmp_path / 'absent-mount').exists()


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1])
def test_bad_threshold_rejected(tmp_path, value):
    with pytest.raises(ValueError):
        load('storage_preflight').inspect_storage([tmp_path], min_free_gib=value)


def test_workspace_template_has_explicit_scheduler_switch_and_database_log_cap():
    import yaml
    data = yaml.safe_load((ROOT / 'deploy/compose.workspace.yml').read_text(encoding='utf-8'))
    for name in ('api', 'worker', 'scheduler', 'db'):
        options = data['services'][name]['logging']['options']
        assert options['max-size'] == '10m' and options['max-file'] == '3'
    env = data['services']['scheduler']['environment']
    assert env['SCHEDULER_ENABLED'] == '${SCHEDULER_ENABLED:-true}'
    assert env['BALANCED_REFRESH_ENABLED'] == '${BALANCED_REFRESH_ENABLED:-false}'
