"""Chunked local-display-v2 delivery: each request <=chunk limit, atomic commit, fail-closed."""
import gzip
import hashlib
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.workspace import shadow_api, shadow_chunks
from app.workspace.local_display_contract import CONTRACT_VERSION, compute_parts_hashes
from app.workspace.shadow_auth import signed_headers
from app.workspace.shadow_bundle import canonical

CHUNK = 4096


def _bundle(seq=1, pad=10000):
    parts = {
        "overview": {"rows": [{"ts_code": "510300.SH", "price": 4.12}], "note": "x" * pad},
        "details": {"510300.SH": {"quote": {"price": 4.12}}},
        "charts": {"510300.SH": {"bars": []}},
        "sectors": {"sectors": []},
    }
    return {
        "manifest": {
            "contract_version": CONTRACT_VERSION, "code_sha": "a" * 40, "config_hash": "c" * 64,
            "sequence": seq, "generated_at": "2026-10-12T06:30:00Z", "expires_at": "2026-10-12T08:30:00Z",
            "actionable": False, "data_origin": "local_research", "universe": ["510300.SH"],
            "parts_hashes": compute_parts_hashes(parts),
        },
        "parts": parts,
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow_chunks, "CHUNK_MAX_DECODED_BYTES", CHUNK)
    monkeypatch.setattr(shadow_chunks, "CHUNK_MAX_WIRE_BYTES", CHUNK)
    monkeypatch.setattr(shadow_chunks, "MAX_TOTAL_DECODED_BYTES", CHUNK * 4)
    settings = SimpleNamespace(
        shadow_sync_enabled=True, shadow_sync_root=str(tmp_path / "sync"), shadow_sync_code_sha="a" * 40,
        shadow_sync_config_hash="b" * 64, shadow_sync_producer_token=SecretStr("x" * 32),
        shadow_sync_active_key_id="test-1", shadow_sync_signing_secret=SecretStr("s" * 32),
        shadow_sync_max_bytes=33554432, shadow_sync_max_generations=20, shadow_sync_max_request_bytes=CHUNK,
        workspace_research_source="local_bundle", local_display_v2_store_root=str(tmp_path / "v2"),
        local_display_v2_max_decompressed_bytes=CHUNK * 4,
    )
    monkeypatch.setattr(shadow_api, "get_settings", lambda: settings)
    monkeypatch.setenv("SHADOW_PRODUCER_TOKEN", "x" * 32)
    monkeypatch.setenv("SHADOW_SIGNING_KEY_ID", "test-1")
    monkeypatch.setenv("SHADOW_SIGNING_SECRET", "s" * 32)
    app = FastAPI(); app.include_router(shadow_api.router)
    client = TestClient(app)
    sent = []

    def opener(request, **kwargs):
        path = request.full_url.split("etf.example", 1)[1]
        sent.append((path, len(request.data)))
        res = client.post(path, content=request.data, headers=dict(request.header_items()))

        @contextmanager
        def ctx():
            yield SimpleNamespace(status=res.status_code, read=lambda n: res.content)
        return ctx()

    return SimpleNamespace(client=client, opener=opener, sent=sent, settings=settings, tmp=tmp_path)


def _chunk_headers(upload_id, index, total, part, wire, secret="s" * 32):
    sha = hashlib.sha256(part).hexdigest()
    h = {"Authorization": "Bearer " + "x" * 32, "X-Chunk-Upload-Id": upload_id, "X-Chunk-Index": str(index),
         "X-Chunk-Total": str(total), "X-Chunk-Sha256": sha}
    h.update(signed_headers(shadow_chunks.chunk_meta(upload_id, index, total, sha) + b"\n" + wire, "test-1", secret,
                            path="/api/shadow/sync/chunk"))
    return h


def _commit_headers(body):
    return {"Authorization": "Bearer " + "x" * 32, **signed_headers(body, "test-1", "s" * 32, path="/api/shadow/sync/commit")}


def test_chunked_upload_every_request_bounded_and_receipt_v2(env):
    from app.workspace.shadow_client import upload_bundle_auto
    bundle = _bundle()
    assert len(canonical(bundle)) > CHUNK
    receipt = upload_bundle_auto("https://etf.example/api/shadow/sync", bundle, opener=env.opener, chunk_size=CHUNK)
    assert receipt["status"] == "accepted" and receipt["sequence"] == 1
    assert set(receipt) == {"bundle_id", "manifest_hash", "status", "sequence", "received_at"}
    chunk_posts = [s for s in env.sent if s[0] == "/api/shadow/sync/chunk"]
    assert len(chunk_posts) >= 2 and all(size <= CHUNK for _, size in chunk_posts)
    assert env.sent[-1][0] == "/api/shadow/sync/commit"
    assert not any((env.tmp / "sync" / "chunks").iterdir())  # staging cleaned after commit
    # Duplicate delivery of the same immutable bundle with new nonces does not re-activate.
    again = upload_bundle_auto("https://etf.example/api/shadow/sync", bundle, opener=env.opener, chunk_size=CHUNK)
    assert again["bundle_id"] == receipt["bundle_id"] and again["status"] in {"accepted", "already_accepted"}


def test_small_bundle_keeps_single_request_path(env):
    from app.workspace.shadow_client import upload_bundle_auto
    receipt = upload_bundle_auto("https://etf.example/api/shadow/sync", _bundle(pad=10), opener=env.opener, chunk_size=CHUNK)
    assert receipt["status"] == "accepted"
    assert [p for p, _ in env.sent] == ["/api/shadow/sync"]


def test_out_of_order_chunks_commit_atomically_and_nothing_visible_before_commit(env):
    body = canonical(_bundle(seq=2))
    parts = shadow_chunks.split_canonical(body, chunk_size=CHUNK)
    uid = hashlib.sha256(body).hexdigest()
    for index in reversed(range(len(parts))):
        wire = gzip.compress(parts[index])
        r = env.client.post("/api/shadow/sync/chunk", content=wire, headers=_chunk_headers(uid, index, len(parts), parts[index], wire))
        assert r.status_code == 200, r.text
    assert not (env.tmp / "v2").exists() or not any((env.tmp / "v2").rglob("*.json"))
    cbody = shadow_chunks.commit_body(uid, len(parts))
    r = env.client.post("/api/shadow/sync/commit", content=cbody, headers=_commit_headers(cbody))
    assert r.status_code == 200 and r.json()["sequence"] == 2


def test_interrupted_upload_missing_chunk_rejected_and_staging_dropped(env):
    body = canonical(_bundle(seq=3))
    parts = shadow_chunks.split_canonical(body, chunk_size=CHUNK)
    uid = hashlib.sha256(body).hexdigest()
    wire = gzip.compress(parts[0])
    assert env.client.post("/api/shadow/sync/chunk", content=wire, headers=_chunk_headers(uid, 0, len(parts), parts[0], wire)).status_code == 200
    cbody = shadow_chunks.commit_body(uid, len(parts))
    assert env.client.post("/api/shadow/sync/commit", content=cbody, headers=_commit_headers(cbody)).status_code == 422
    assert not (env.tmp / "sync" / "chunks" / uid).exists()


def test_corrupt_tampered_oversized_and_busy_chunks_rejected(env):
    body = canonical(_bundle(seq=4))
    parts = shadow_chunks.split_canonical(body, chunk_size=CHUNK)
    uid = hashlib.sha256(body).hexdigest()
    wire = gzip.compress(parts[0])
    # tampered index after signing -> signature mismatch
    h = _chunk_headers(uid, 0, len(parts), parts[0], wire); h["X-Chunk-Index"] = "1"
    assert env.client.post("/api/shadow/sync/chunk", content=wire, headers=h).status_code == 401
    # wrong secret
    assert env.client.post("/api/shadow/sync/chunk", content=wire, headers=_chunk_headers(uid, 0, len(parts), parts[0], wire, secret="t" * 32)).status_code == 401
    # declared digest does not match decoded bytes
    other = b"y" * 100; owire = gzip.compress(other)
    h = _chunk_headers(uid, 0, len(parts), other, owire); 
    bad = dict(h); bad_sha = hashlib.sha256(b"z").hexdigest()
    bad["X-Chunk-Sha256"] = bad_sha
    bad.update(signed_headers(shadow_chunks.chunk_meta(uid, 0, len(parts), bad_sha) + b"\n" + owire, "test-1", "s" * 32, path="/api/shadow/sync/chunk"))
    assert env.client.post("/api/shadow/sync/chunk", content=owire, headers=bad).status_code == 422
    # decoded chunk larger than limit (gzip bomb style)
    big = b"0" * (CHUNK + 1); bwire = gzip.compress(big)
    assert env.client.post("/api/shadow/sync/chunk", content=bwire, headers=_chunk_headers(uid, 0, len(parts), big, bwire)).status_code == 422
    # too many chunks declared
    assert env.client.post("/api/shadow/sync/chunk", content=wire, headers=_chunk_headers(uid, 0, 5, parts[0], wire)).status_code == 422
    # a second concurrent upload id is refused while one is staging
    assert env.client.post("/api/shadow/sync/chunk", content=wire, headers=_chunk_headers(uid, 0, len(parts), parts[0], wire)).status_code == 200
    other_uid = "f" * 64
    assert env.client.post("/api/shadow/sync/chunk", content=wire, headers=_chunk_headers(other_uid, 0, len(parts), parts[0], wire)).status_code == 409
    # unauthenticated
    assert env.client.post("/api/shadow/sync/chunk", content=wire).status_code == 401


def test_assembled_digest_mismatch_rejected(env):
    body = canonical(_bundle(seq=5))
    parts = shadow_chunks.split_canonical(body, chunk_size=CHUNK)
    uid = hashlib.sha256(b"different").hexdigest()
    for index, part in enumerate(parts):
        wire = gzip.compress(part)
        assert env.client.post("/api/shadow/sync/chunk", content=wire, headers=_chunk_headers(uid, index, len(parts), part, wire)).status_code == 200
    cbody = shadow_chunks.commit_body(uid, len(parts))
    assert env.client.post("/api/shadow/sync/commit", content=cbody, headers=_commit_headers(cbody)).status_code == 422


def test_split_rejects_over_domain_budget(monkeypatch):
    monkeypatch.setattr(shadow_chunks, "MAX_TOTAL_DECODED_BYTES", 10)
    with pytest.raises(ValueError):
        shadow_chunks.split_canonical(b"0" * 11, chunk_size=4)


def test_legacy_signature_domain_unchanged():
    from app.workspace.shadow_auth import DOMAIN, message
    assert message(b"b", "k", "t", "n") == DOMAIN + b"k\x00t\x00n\x00" + hashlib.sha256(b"b").digest()
    with pytest.raises(ValueError):
        message(b"b", "k", "t", "n", "/api/other")
