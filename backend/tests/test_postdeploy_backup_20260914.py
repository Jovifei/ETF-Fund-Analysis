"""Run the real backup script against a fake docker executable, never a DB."""
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.name == 'nt', reason='Linux host backup script')


@pytest.fixture
def backup(tmp_path):
    repo = tmp_path / 'repo'; (repo / 'scripts').mkdir(parents=True)
    script = repo / 'scripts/backup_postgres.sh'
    shutil.copy2(ROOT / 'scripts/backup_postgres.sh', script)
    fake = tmp_path / 'bin'; fake.mkdir()
    docker = fake / 'docker'
    docker.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$CALL_LOG"\n'
                      'if [[ "$DUMP_MODE" != empty ]]; then printf "-- dump fixture\\n"; fi\n'
                      'exit "${DUMP_EXIT:-0}"\n', encoding='utf-8')
    # bash printf treats a leading -- as an option on some versions.
    docker.write_text(docker.read_text().replace('printf "-- dump fixture\\n"', "printf '%s\\n' '-- dump fixture'"))
    docker.chmod(0o755)
    date = fake / 'date'; date.write_text('#!/bin/sh\nprintf "20260914_120000\\n"\n'); date.chmod(0o755)
    env = {**os.environ, 'PATH': str(fake) + os.pathsep + os.environ['PATH'],
           'CALL_LOG': str(tmp_path / 'calls'), 'DUMP_EXIT': '0', 'DUMP_MODE': 'ok'}
    for key in ('BACKUP_DIR', 'COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'BACKUP_RETENTION_DAYS'):
        env.pop(key, None)
    return script, repo, env


def run(backup, *args, **env_changes):
    script, repo, env = backup
    return subprocess.run(['bash', str(script), *args], cwd=repo,
                          env={**env, **env_changes}, capture_output=True, text=True, timeout=10)


def test_failed_dump_never_publishes_a_backup(backup):
    _, repo, _ = backup
    proc = run(backup, DUMP_EXIT='9')
    assert proc.returncode != 0
    assert not list((repo / 'backups').glob('*.sql.gz'))
    assert not list((repo / 'backups').glob('*.sha256'))


def test_empty_dump_is_not_a_successful_backup(backup):
    _, repo, _ = backup
    assert run(backup, DUMP_MODE='empty').returncode != 0
    assert not list((repo / 'backups').glob('*.sql.gz'))


def test_same_second_backups_do_not_overwrite_and_have_checksums(backup):
    _, repo, _ = backup
    assert run(backup).returncode == 0
    assert run(backup).returncode == 0
    files = list((repo / 'backups').glob('*.sql.gz'))
    assert len(files) == 2
    for path in files:
        assert gzip.decompress(path.read_bytes()) == b'-- dump fixture\n'
        assert path.stat().st_mode & 0o077 == 0
        check = subprocess.run(['sha256sum', '-c', str(path) + '.sha256'],
                               cwd=repo / 'backups', capture_output=True)
        assert check.returncode == 0


def test_backup_never_prunes_an_existing_rollback_archive(backup):
    _, repo, _ = backup
    (repo / 'backups').mkdir()
    old = repo / 'backups/fund_decision_old.sql.gz'; old.write_bytes(b'preserve')
    os.utime(old, (time.time() - 400 * 86400,) * 2)
    assert run(backup).returncode == 0
    assert old.read_bytes() == b'preserve'


def test_explicit_compose_project_and_external_backup_destination(backup, tmp_path):
    _, repo, env = backup
    compose = tmp_path / 'private compose.yml'; compose.write_text('services: {}\n')
    destination = tmp_path / 'private backups'
    proc = run(backup, '--compose-file', str(compose), '--project-name', 'verified-etf',
               '--backup-dir', str(destination))
    assert proc.returncode == 0, proc.stderr
    calls = Path(env['CALL_LOG']).read_text().splitlines()
    assert calls[:5] == ['compose', '-f', str(compose), '-p', 'verified-etf']
    assert len(list(destination.glob('*.sql.gz'))) == 1
    assert not list((repo / 'backups').glob('*.sql.gz'))
