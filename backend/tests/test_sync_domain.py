"""Shared staging/publication budget and interrupted transport regressions."""
import gzip
import hashlib
from pathlib import Path

import pytest

from app.workspace.shadow_chunks import ChunkStaging, ChunkRejected
from app.workspace.sync_domain import SyncDomain


def put(stage, data=b"payload", upload=None):
    identity = upload or hashlib.sha256(data).hexdigest()
    return stage.put(identity, 0, 1, hashlib.sha256(data).hexdigest(), gzip.compress(data))


def test_duplicate_chunk_at_capacity_is_idempotent(tmp_path, monkeypatch):
    from app.workspace import shadow_chunks
    monkeypatch.setattr(shadow_chunks, "MAX_TOTAL_DECODED_BYTES", 10)
    stage = ChunkStaging(tmp_path)
    put(stage, b"x" * 10)
    assert put(stage, b"x" * 10)["status"] == "staged"


def test_one_writer_cannot_steal_a_live_transport_lock(tmp_path):
    domain = SyncDomain(tmp_path)
    with domain.locked():
        with pytest.raises(ValueError, match="busy"):
            put(ChunkStaging(tmp_path))


def test_staging_includes_existing_display_nonce_and_temporary_bytes(tmp_path):
    other = tmp_path / "display"
    other.mkdir()
    (other / "bundle.json").write_bytes(b"x" * 100)
    (tmp_path / ".pending-interrupted").write_bytes(b"x" * 90)
    domain = SyncDomain(tmp_path, roots=(other,), max_bytes=200)
    with pytest.raises(ValueError, match="capacity"):
        put(ChunkStaging(tmp_path, domain=domain), b"x" * 20)
    assert (other / "bundle.json").stat().st_size == 100


def test_missing_part_and_publish_failure_keep_retryable_staging(tmp_path):
    stage = ChunkStaging(tmp_path)
    data = b"payload"
    uid = hashlib.sha256(data).hexdigest()
    put(stage, data)
    def fail(_):
        raise OSError("synthetic disk failure")
    with pytest.raises(OSError):
        stage.commit(uid, 1, fail)
    assert stage.assemble(uid, 1) == data
    receipt = {"status": "accepted", "bundle_id": "f" * 64, "manifest_hash": "f" * 64,
               "sequence": 1, "received_at": "2026-10-15T06:00:00Z"}
    assert stage.commit(uid, 1, lambda body: receipt) == receipt
    def no_republish(_):
        pytest.fail("same committed upload must only return the durable receipt")
    assert stage.commit(uid, 1, no_republish) == receipt


def test_same_chunk_cannot_be_replaced_by_other_bytes(tmp_path):
    stage = ChunkStaging(tmp_path)
    uid = hashlib.sha256(b"payload").hexdigest()
    put(stage, b"payload", upload=uid)
    with pytest.raises(ChunkRejected):
        put(stage, b"changed", upload=uid)
    assert stage.assemble(uid, 1) == b"payload"
