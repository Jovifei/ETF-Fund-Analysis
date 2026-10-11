"""Public publish/read recovery under simulated storage faults; no real disk fill.

A real process kill may retain publish.lock. Recovery must first establish that
the publisher is dead and inspect latest/previous plus their complete blobs;
only then may an operator remove that lock. No automatic stale-lock deletion.
"""
from datetime import datetime, timedelta, timezone
import errno
import json
from pathlib import Path

import pytest

import app.workspace.shadow_bundle as module
from app.workspace.shadow_bundle import ShadowStore, make_bundle


NOW = datetime(2026, 10, 11, 6, 30, tzinfo=timezone.utc)


def candidate(sequence):
    return make_bundle(
        {"rows": [{"ts_code": "510300.SH", "price": float(sequence)}]},
        {"510300.SH": {"bars": []}}, {"references": []},
        sequence=sequence, generated_at=NOW, expires_at=NOW + timedelta(hours=1),
        code_sha="a" * 40, config_hash="b" * 64,
    )


def seeded(root):
    store = ShadowStore(root, code_sha="a" * 40, config_hash="b" * 64)
    store.publish(candidate(1), now=NOW)
    store.publish(candidate(2), now=NOW)
    return store


def assert_reachable(store, latest, previous):
    assert store.read(now=NOW)["sequence"] == latest
    pointer = json.loads((store.root / "previous.json").read_bytes())
    assert store.read(now=NOW, bundle_id=pointer["bundle_id"])["sequence"] == previous


@pytest.mark.parametrize("error", [OSError(errno.ENOSPC, "simulated full"), PermissionError("simulated denied")])
@pytest.mark.parametrize("destination", ["blob", "manifest", "previous.json", "latest.json"])
def test_replace_fault_never_publishes_partial_generation(tmp_path, monkeypatch, error, destination):
    store = seeded(tmp_path)
    original = module.os.replace
    touched = []

    def failing_replace(src, dst):
        path = Path(dst)
        match = (destination == "blob" and path.parent.name == "blobs"
                 or destination == "manifest" and path.parent.name == "manifests"
                 or path.name == destination)
        if match:
            touched.append(path)
            raise error
        return original(src, dst)

    with monkeypatch.context() as scoped:
        scoped.setattr(module.os, "replace", failing_replace)
        with pytest.raises(type(error)):
            store.publish(candidate(3), now=NOW)
    assert touched
    # previous update precedes latest, so failed latest may legally make both 2.
    assert_reachable(store, 2, 2 if destination == "latest.json" else 1)
    assert not (tmp_path / "publish.lock").exists()
    assert not list(tmp_path.rglob(".pending-*"))
    store.publish(candidate(3), now=NOW)
    assert_reachable(store, 3, 2)
    with pytest.raises(ValueError, match="replay"):
        store.publish(candidate(3), now=NOW)


def test_partial_write_enospc_is_not_published_and_retry_is_safe(tmp_path, monkeypatch):
    store = seeded(tmp_path)
    original = Path.open
    faults = []

    class PartialWriter:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def write(self, data):
            self.handle.write(data[: max(1, len(data) // 2)])
            self.handle.flush()
            faults.append(True)
            raise OSError(errno.ENOSPC, "simulated partial write")

    def failing_open(path, *args, **kwargs):
        handle = original(path, *args, **kwargs)
        return PartialWriter(handle) if path.name.startswith(".pending-") and args == ("xb",) else handle

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "open", failing_open)
        with pytest.raises(OSError) as caught:
            store.publish(candidate(3), now=NOW)
        assert caught.value.errno == errno.ENOSPC
    assert faults
    assert_reachable(store, 2, 1)
    assert not list(tmp_path.rglob(".pending-*"))
    store.publish(candidate(3), now=NOW)
    assert_reachable(store, 3, 2)


def test_complete_manifest_before_pointer_is_unpublished_until_retry(tmp_path, monkeypatch):
    store = seeded(tmp_path)
    original = module.os.replace
    value = candidate(3)
    identifier = module.digest(value["manifest"])

    def interrupt_pointer(src, dst):
        if Path(dst).name == "latest.json":
            raise PermissionError("simulated interruption before pointer")
        return original(src, dst)

    with monkeypatch.context() as scoped:
        scoped.setattr(module.os, "replace", interrupt_pointer)
        with pytest.raises(PermissionError):
            store.publish(value, now=NOW)
    assert (tmp_path / "manifests" / identifier).exists()
    assert store.read(now=NOW, bundle_id=identifier)["sequence"] == 3
    assert_reachable(store, 2, 2)
    store.publish(value, now=NOW)
    assert_reachable(store, 3, 2)


def test_gc_unlink_interruption_keeps_protected_generations_and_retry(tmp_path, monkeypatch):
    store = seeded(tmp_path)
    store.publish(candidate(3), now=NOW)
    store.max_generations = 2
    original = Path.unlink
    protected = {json.loads((tmp_path / name).read_bytes())["bundle_id"]
                 for name in ("latest.json", "previous.json")}
    faults = []

    def interrupt_gc(path, *args, **kwargs):
        if path.parent.name == "manifests" and path.name not in protected:
            faults.append(path)
            raise PermissionError("simulated gc interruption")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "unlink", interrupt_gc)
        with pytest.raises(PermissionError):
            store.publish(candidate(4), now=NOW)
    assert faults
    assert_reachable(store, 3, 2)
    store.publish(candidate(4), now=NOW)
    assert_reachable(store, 4, 3)
    assert len(list((tmp_path / "manifests").iterdir())) == 2


def test_crash_lock_requires_inspection_and_manual_recovery(tmp_path):
    store = seeded(tmp_path)
    lock = tmp_path / "publish.lock"
    lock.write_text("simulated dead publisher")
    with pytest.raises(ValueError, match="busy"):
        store.publish(candidate(3), now=NOW)
    assert lock.exists()
    assert_reachable(store, 2, 1)
    # This test owns the simulated publisher and tmp directory; not a production
    # stale-lock policy. Inspect complete pointers before operator removal.
    lock.unlink()
    store.publish(candidate(3), now=NOW)
    assert_reachable(store, 3, 2)
