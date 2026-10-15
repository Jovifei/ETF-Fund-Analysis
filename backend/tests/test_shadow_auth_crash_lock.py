"""Replay reservations survive process death without deleting a lock pathname."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from threading import Barrier

import pytest

from app.workspace.local_schedule import LocalRunLock
from app.workspace.shadow_auth import signed_headers, verify_request
from app.workspace.sync_domain import SyncDomain

NOW = datetime(2026, 10, 15, 6, tzinfo=timezone.utc)


def verify(root, nonce="a" * 32, **kwargs):
    headers = signed_headers(b"{}", "test", "s" * 32, now=NOW, nonce=nonce)
    return verify_request(b"{}", headers, root, "test", "s" * 32, now=NOW, **kwargs)


def test_legacy_crash_marker_does_not_permanently_reject_valid_requests(tmp_path):
    directory = tmp_path / "nonces"
    directory.mkdir()
    lock_path = directory / "reserve.lock"
    lock_path.write_bytes(b"")  # Legacy O_EXCL lock left behind by a killed process.
    inode = lock_path.stat().st_ino
    verify(tmp_path)
    assert lock_path.exists() and lock_path.stat().st_ino == inode
    with pytest.raises(ValueError, match="replay rejected"):
        verify(tmp_path)


def test_live_nonce_owner_cannot_be_stolen_or_unlinked(tmp_path):
    lock = LocalRunLock(tmp_path / "nonces" / "reserve.lock")
    assert lock.acquire()
    try:
        with pytest.raises(ValueError, match="reservation busy"):
            verify(tmp_path)
        assert not list((tmp_path / "nonces").glob("[a-f0-9]" * 64))
        assert lock.lock_path.exists()
    finally:
        lock.release()
    verify(tmp_path)


def test_nonce_reservation_recovers_after_actual_process_exit(tmp_path):
    lock_path = tmp_path / "nonces" / "reserve.lock"
    code = "from app.workspace.local_schedule import LocalRunLock; import os,sys; lock=LocalRunLock(sys.argv[1]); assert lock.acquire(); os._exit(7)"
    child = subprocess.run([sys.executable, "-c", code, str(lock_path)], cwd=Path(__file__).resolve().parents[1],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10)
    assert child.returncode == 7
    inode = lock_path.stat().st_ino
    verify(tmp_path)
    assert lock_path.stat().st_ino == inode


def test_standalone_concurrent_nonce_reservations_keep_count_bound(tmp_path):
    barrier = Barrier(2)
    def attempt(nonce):
        barrier.wait(timeout=5)
        try:
            verify(tmp_path, nonce=nonce, max_nonces=1)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(attempt, ["a" * 32, "b" * 32]))
    assert sum(result) == 1
    assert len([p for p in (tmp_path / "nonces").iterdir() if len(p.name) == 64]) == 1


def test_existing_api_domain_owner_can_reserve_without_nested_domain_deadlock(tmp_path):
    domain = SyncDomain(tmp_path)
    with domain.locked():
        verify(tmp_path, domain=domain)
    assert (tmp_path / "nonces" / "reserve.lock").exists()
