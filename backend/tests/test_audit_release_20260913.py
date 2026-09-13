import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('release_inventory',ROOT/'scripts/release_manifest.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


def test_inventory_is_metadata_only_and_never_upgrades_data():
    value=release.inventory(ROOT)
    assert len(value['source_sha'])==40
    assert value['application_version']==value['frontend_version']=='1.0.5'
    assert value['version_match']
    assert value['registry_image_digest'] is None
    assert 'published_image_digest_missing' in value['missing']
    assert not value['release_inventory_complete'] and not value['production_deployed']
    assert value['data_qualification']=='not_asserted'
    assert value['migration_heads']==['d40609090002']
    assert all(set(row)=={'name','version'} for row in value['python_resolved'])
    assert not any('.env' in path or 'auth.json' in path for path in value['source_hashes'])


def test_image_id_is_not_registry_digest():
    value=release.inventory(ROOT,image_id='sha256:'+'a'*64)
    assert value['image_id'] and value['registry_image_digest'] is None
    assert not value['release_inventory_complete']
    with pytest.raises(ValueError,match='invalid_image_digest'):
        release.valid_digest('latest')


def test_hash_refuses_symlink_escape(tmp_path):
    outside=tmp_path/'outside';outside.write_text('not-secret')
    inside=tmp_path/'source';inside.mkdir()
    try:
        (inside/'escape').symlink_to(outside)
    except OSError:
        pytest.skip('symlink privilege not available')
    with pytest.raises(ValueError,match='unsafe'):
        release.tracked_hash(inside,'escape')


def test_untracked_application_file_prevents_complete_receipt(monkeypatch):
    original=release.git
    def commands(root,*args):
        if args == ('ls-files','--others','--exclude-standard'):
            return 'backend/app/unreviewed.py\nprivate/never-disclose.txt'
        return original(root,*args)
    monkeypatch.setattr(release,'git',commands)
    value=release.inventory(ROOT)
    assert value['untracked_application_file_count']==1
    assert 'untracked_application_files' in value['missing']
    assert 'never-disclose' not in json.dumps(value)
    assert not value['release_inventory_complete']
