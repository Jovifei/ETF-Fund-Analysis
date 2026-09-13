"""Read-only artifact inventory. Never reads credentials, private env or the DB.

A build image ID is NOT a registry digest. Missing fields stay missing; this
manifest is provenance, not a data-source or trading qualification certificate.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import tomllib


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tracked_hash(root: Path, relative: str) -> str:
    path = root / relative
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('manifest_source_file_missing_or_unsafe')
    return digest(path.read_bytes())


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def valid_digest(value: str | None) -> str | None:
    if value is not None and not re.fullmatch(r'sha256:[a-f0-9]{64}', value):
        raise ValueError('invalid_image_digest')
    return value


def inventory(root: Path, *, image_id: str | None = None, image_digest: str | None = None, runtime_packages: list | None = None) -> dict:
    root = root.resolve()
    source = git(root, 'rev-parse', 'HEAD')
    tree = git(root, 'rev-parse', 'HEAD^{tree}')
    dirty = bool(git(root, 'diff', 'HEAD', '--name-only'))
    # An untracked application module can be imported even when git diff is
    # empty. Count it, but never publish private file names in the receipt.
    critical = {'backend', 'frontend', 'bridge', 'scripts', 'config', '.github'}
    untracked = [p for p in git(root, 'ls-files', '--others', '--exclude-standard').splitlines()
                 if p.split('/', 1)[0] in critical]
    hashes = {name: tracked_hash(root, name) for name in
              ['pyproject.toml', 'frontend/package.json', 'frontend/package-lock.json', 'config/strategy.json']}
    backend = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    frontend = json.loads((root / 'frontend/package.json').read_text(encoding='utf-8'))['version']
    lock = json.loads((root / 'frontend/package-lock.json').read_text(encoding='utf-8'))
    versions_match = backend == frontend == lock['version'] == lock['packages']['']['version']
    assets = {}
    directory = root / 'backend/app/workspace_dist'
    if directory.is_dir():
        for path in sorted(directory.rglob('*')):
            if path.is_symlink():
                raise ValueError('symlink_build_asset_rejected')
            if path.is_file():
                name = path.relative_to(root).as_posix()
                assets[name] = tracked_hash(root, name)
    # Exact installed names/versions, no pip URLs or environment secrets.
    installed = sorted({(str(d.metadata.get('Name','')).lower(), d.version) for d in metadata.distributions()})
    resolved = [{'name': name, 'version': version} for name, version in installed if name]
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(root / 'alembic.ini'))
    cfg.set_main_option('script_location', str(root / 'backend/alembic'))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    image_id, image_digest = valid_digest(image_id), valid_digest(image_digest)
    if runtime_packages is not None:
        if not isinstance(runtime_packages, list) or len(runtime_packages) > 5000:
            raise ValueError('invalid_runtime_package_inventory')
        for row in runtime_packages:
            if (not isinstance(row, dict) or set(row) != {'name', 'version'}
                or not all(isinstance(row[k], str) and re.fullmatch(r'[A-Za-z0-9_.+!\-]{1,200}', row[k]) for k in row)):
                raise ValueError('invalid_runtime_package_inventory')
        runtime_packages = sorted(runtime_packages, key=lambda row: (row['name'], row['version']))
    missing = []
    if not runtime_packages: missing.append('runtime_package_inventory_missing')
    if dirty: missing.append('tracked_worktree_dirty')
    if untracked: missing.append('untracked_application_files')
    if not versions_match: missing.append('application_version_mismatch')
    if 'backend/app/workspace_dist/index.html' not in assets: missing.append('frontend_build_missing')
    if len(heads) != 1: missing.append('migration_head_not_unique')
    if not image_digest: missing.append('published_image_digest_missing')
    return {'manifest_version':'etf-release-inventory-v1', 'created_at':datetime.now(timezone.utc).isoformat(),
            'source_sha':source, 'source_tree':tree, 'tracked_worktree_dirty':dirty,
            'untracked_application_file_count':len(untracked),
            'application_version':backend, 'frontend_version':frontend, 'version_match':versions_match,
            'source_hashes':hashes, 'frontend_assets':assets,
            'frontend_tree_hash':digest(json.dumps(assets,sort_keys=True).encode()),
            'python_version':platform.python_version(), 'python_resolved':resolved,
            'python_resolved_hash':digest(json.dumps(resolved,sort_keys=True).encode()),
            'python_resolved_scope':'manifest_process', 'runtime_packages':runtime_packages,
            'runtime_packages_hash':digest(json.dumps(runtime_packages,sort_keys=True).encode()) if runtime_packages else None,
            'migration_heads':heads, 'image_id':image_id, 'registry_image_digest':image_digest,
            'missing':missing, 'release_inventory_complete':not missing,
            'data_qualification':'not_asserted', 'production_deployed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--image-id')
    parser.add_argument('--image-digest')
    parser.add_argument('--runtime-packages',type=Path)
    args=parser.parse_args()
    packages=json.loads(args.runtime_packages.read_text(encoding='utf-8')) if args.runtime_packages else None
    value=inventory(args.repo,image_id=args.image_id,image_digest=args.image_digest,runtime_packages=packages)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    # Refuse overwriting a prior receipt. A new deployment gets a new file.
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps({'source_sha':value['source_sha'],'complete':value['release_inventory_complete'],
                      'missing':value['missing']},ensure_ascii=False))


if __name__=='__main__':
    main()
