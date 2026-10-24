"""Bounded rolling publication must reclaim only obsolete validated generations."""
from copy import deepcopy
import os

import pytest

from app.workspace.local_display_read import LocalDisplayStore
from app.workspace.shadow_bundle import canonical
from test_receiver_admission import candidate


def watch_atomic_peak(domain, monkeypatch):
    peaks = []
    native = os.replace

    def replace(source, destination):
        peak = domain.used_bytes() + domain.held_bytes
        assert peak <= domain.max_bytes
        peaks.append(peak)
        return native(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    return peaks


def test_single_request_keeps_rolling_under_fixed_peak_budget(tmp_path, monkeypatch):
    value = candidate()
    value["parts"]["overview"]["padding"] = "x" * 2048
    from app.workspace.local_display_contract import compute_parts_hashes
    value["manifest"]["parts_hashes"] = compute_parts_hashes(value["parts"])
    # Both committed pointers now carry bounded acceptance history. Reserve its
    # real temporary peak; the explicit generation cap still forces collection.
    store = LocalDisplayStore(tmp_path, max_bytes=3 * len(canonical(value)) + 8192, max_generations=3)
    peaks = watch_atomic_peak(store.domain, monkeypatch)
    for sequence in range(1, 12):
        item = deepcopy(value)
        item["manifest"]["sequence"] = sequence
        assert store.publish(item)["status"] == "accepted"
        assert store.domain.used_bytes() + store.domain.held_bytes <= store.domain.max_bytes == store.max_bytes
        assert store.domain.held_bytes == 0
        assert store.load_bundle()["manifest"]["sequence"] == sequence
        if sequence > 1:
            assert store.load_bundle(sequence - 1) is not None
        if sequence > 3:
            assert store.load_bundle(sequence - 3) is None
        assert len(list(tmp_path.glob("bundle_*.json"))) == min(sequence, 3)
    assert len(peaks) >= 11


def test_interrupted_rolling_publish_keeps_current_previous_and_unknown_file(tmp_path, monkeypatch):
    value = candidate()
    store = LocalDisplayStore(tmp_path)
    for sequence in range(1, 6):
        item = deepcopy(value)
        item["manifest"]["sequence"] = sequence
        store.publish(item)
    unknown = tmp_path / "bundle_notes.json"
    unknown.write_text("keep synthetic unknown evidence")
    store.max_bytes = store.domain.used_bytes() + 16
    latest = store.latest_link.read_bytes()
    previous = store.previous_link.read_bytes()
    original = store._atomic
    def fail_latest(path, data):
        if path == store.latest_link:
            raise OSError("synthetic failed final switch")
        return original(path, data)
    monkeypatch.setattr(store, "_atomic", fail_latest)
    value["manifest"]["sequence"] = 6
    with pytest.raises(OSError):
        store.publish(value)
    assert store.latest_link.read_bytes() == latest
    assert store.previous_link.read_bytes() == previous
    assert store.load_bundle(5) is not None and store.load_bundle(4) is not None
    assert unknown.read_text() == "keep synthetic unknown evidence"
    assert store.domain.used_bytes() <= store.max_bytes


def test_chunk_commit_reclaims_old_cache_without_discounting_staged_bytes(tmp_path, monkeypatch):
    import gzip
    import hashlib
    import json
    from app.workspace.local_display_contract import compute_parts_hashes
    from app.workspace.shadow_chunks import ChunkStaging
    from app.workspace.sync_domain import SyncDomain
    value = candidate()
    value["parts"]["overview"]["padding"] = "x" * 4096
    value["manifest"]["parts_hashes"] = compute_parts_hashes(value["parts"])
    domain = SyncDomain(tmp_path / "sync", roots=(tmp_path / "display",),
                        max_bytes=4 * len(canonical(value)) + 8192 + 1024)
    store = LocalDisplayStore(tmp_path / "display", domain=domain, max_generations=3)
    peaks = watch_atomic_peak(domain, monkeypatch)
    for sequence in range(1, 4):
        item = deepcopy(value)
        item["manifest"]["sequence"] = sequence
        store.publish(item)
    value["manifest"]["sequence"] = 4
    data = canonical(value)
    uid = hashlib.sha256(data).hexdigest()
    stage = ChunkStaging(tmp_path / "sync", domain=domain)
    stage.put(uid, 0, 1, uid, gzip.compress(data))
    result = stage.commit(uid, 1, lambda body: store.publish(json.loads(body)))
    assert result["status"] == "accepted"
    assert store.load_bundle()["manifest"]["sequence"] == 4
    assert store.load_bundle(3) is not None  # previous pointer protected
    assert store.load_bundle(2) is not None  # retained validated generation
    assert store.load_bundle(1) is None
    assert len(list((tmp_path / "display").glob("bundle_*.json"))) == 3
    assert domain.held_bytes == 0  # 1024 B chunk-commit hold released
    assert domain.used_bytes() <= domain.max_bytes
    assert peaks
