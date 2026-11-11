"""Standalone archive permissions and signed request contract, synthetic only."""
from __future__ import annotations

import base64
import hashlib
from datetime import timedelta

import pytest
from app.workspace.historical_archive import ArchivePolicy, ArchiveStore
from app.workspace.historical_archive_api import (
    ArchiveCredential,
    create_archive_app,
    signed_archive_headers,
)
from app.workspace.shadow_auth import signed_headers
from app.workspace.shadow_bundle import canonical
from fastapi.testclient import TestClient
from test_historical_archive import NOW, PRODUCER, bundle, evidence

WRITER = ArchiveCredential("archive-writer", "w" * 40, frozenset({"archive:submit"}))
READER = ArchiveCredential("archive-reader", "r" * 40, frozenset({"archive:read"}))
PATH = "/api/history-archive/objects"


def policy(tmp_path, **updates):
    options = dict(root=tmp_path / "history", protected_roots=(tmp_path / "live",),
                   trusted_producers=frozenset({PRODUCER}), min_free_bytes=0,
                   max_payload_bytes=64 * 1024, max_bytes=8 * 1024 * 1024)
    options.update(updates)
    return ArchivePolicy(**options)


def request_body(raw=None):
    raw = canonical(bundle()) if raw is None else raw
    return canonical({"contract": "historical-archive-submit-v1", "original_sha256": hashlib.sha256(raw).hexdigest(),
                      "original_base64": base64.b64encode(raw).decode(), "evidence": evidence()})


def client(tmp_path, **updates):
    return TestClient(create_archive_app(enabled=True, policy=policy(tmp_path, **updates),
                                        credentials=(WRITER, READER), clock=lambda: NOW))


def send(client, body, key=WRITER, *, path=PATH, now=NOW, nonce=None):
    headers = signed_archive_headers(body, key, method="POST", path=path, now=now, nonce=nonce)
    return client.post(path, content=body, headers=headers)


def get(client, path, key=READER):
    headers = signed_archive_headers(b"", key, method="GET", path=path, now=NOW)
    return client.get(path, headers=headers)


def test_disabled_factory_does_not_create_storage(tmp_path):
    app = create_archive_app(policy=policy(tmp_path), credentials=(WRITER, READER))
    assert TestClient(app).post(PATH, content=request_body()).status_code == 404
    assert not (tmp_path / "history").exists()


def test_distinct_permissions_roundtrip_and_unknown_receipt(tmp_path):
    c = client(tmp_path)
    body = request_body()
    assert c.post(PATH, content=body).status_code == 401
    assert send(c, body, READER).status_code == 403
    response = send(c, body)
    assert response.status_code == 200
    receipt = response.json()
    path = "/api/history-archive/receipts/" + receipt["archive_id"]
    assert get(c, path, WRITER).status_code == 403
    assert get(c, path).json() == receipt
    raw_path = PATH + "/" + receipt["archive_id"]
    assert get(c, raw_path).content == canonical(bundle())
    unknown = get(c, "/api/history-archive/receipts/" + "f" * 64)
    assert unknown.status_code == 200 and unknown.json()["status"] == "UNKNOWN"
    assert response.headers["cache-control"] == "no-store"


def test_live_shadow_signature_cannot_authorize_archive(tmp_path):
    c = client(tmp_path)
    body = request_body()
    headers = signed_headers(body, WRITER.key_id, WRITER.secret, now=NOW)
    assert c.post(PATH, content=body, headers=headers).status_code == 401
    # Even relabelled headers have a different signing domain.
    renamed = {key.replace("Shadow", "Archive"): value for key, value in headers.items()}
    assert c.post(PATH, content=body, headers=renamed).status_code == 401
    assert c.post("/api/shadow/sync", content=body, headers=headers).status_code == 404


def test_signature_binds_bytes_path_method_time_and_replay(tmp_path):
    c = client(tmp_path)
    body = request_body()
    headers = signed_archive_headers(body, WRITER, method="POST", path=PATH, now=NOW, nonce="a" * 32)
    assert c.post(PATH, content=body + b" ", headers=headers).status_code == 401
    assert c.post("/api/history-archive/gaps", content=body, headers=headers).status_code == 401
    assert send(c, body, now=NOW - timedelta(seconds=121)).status_code == 401
    assert c.post(PATH, content=body, headers=headers).status_code == 200
    assert c.post(PATH, content=body, headers=headers).status_code == 409
    assert send(c, body).status_code == 200  # new nonce, same immutable receipt
    assert c.post(PATH + "?ignored=true", content=body, headers=headers).status_code == 400


def test_nonce_persists_across_service_restart(tmp_path):
    body = request_body()
    first = client(tmp_path)
    assert send(first, body, nonce="b" * 32).status_code == 200
    second = client(tmp_path)
    assert send(second, body, nonce="b" * 32).status_code == 409
    assert send(second, body, nonce="c" * 32).status_code == 200


def test_stream_and_decoded_body_limits(tmp_path):
    c = client(tmp_path, max_payload_bytes=4096)
    assert send(c, b"x" * 60000).status_code == 413
    response = send(c, request_body(b"x" * 5000))
    assert response.status_code == 413


def test_invalid_envelope_and_conflict_are_not_success(tmp_path):
    c = client(tmp_path)
    assert send(c, b'{"contract":"bad"}').status_code == 400
    assert send(c, request_body()).status_code == 200
    changed = bundle()
    changed["manifest"]["expires_at"] = (NOW + timedelta(hours=1)).isoformat()
    conflict = send(c, request_body(canonical(changed)))
    assert conflict.status_code == 202 and conflict.json()["status"] == "QUARANTINED"
    rejected = send(c, request_body(b'{"password":"not-retained"}'))
    assert rejected.status_code == 422 and rejected.json()["status"] == "REJECTED"


def test_gap_endpoint_never_reads_or_recomputes_a_package(tmp_path):
    c = client(tmp_path)
    body = canonical({"contract": "historical-archive-gap-v1", "reason": "original_missing", "evidence": evidence()})
    response = send(c, body, path="/api/history-archive/gaps")
    assert response.status_code == 200 and response.json()["status"] == "GAP_RECORDED"
    assert response.json()["bundle_id"] is None


def test_explicit_credentials_are_required_and_unknown_scope_rejected(tmp_path):
    with pytest.raises(ValueError, match="credential"):
        create_archive_app(enabled=True, policy=policy(tmp_path))
    invalid = ArchiveCredential("live-writer", "x" * 40, frozenset({"WRITE_ONLY_SHADOW"}))
    with pytest.raises(ValueError, match="credential"):
        create_archive_app(enabled=True, policy=policy(tmp_path), credentials=(invalid,))
    assert not (tmp_path / "history").exists()


def test_full_quota_returns_retryable_error_without_false_receipt(tmp_path, monkeypatch):
    c = client(tmp_path)
    monkeypatch.setattr(ArchiveStore, "_capacity", lambda *args: (_ for _ in ()).throw(ValueError("archive capacity unavailable")))
    response = send(c, request_body())
    assert response.status_code == 503
    assert "archive_id" not in response.json()


def test_receipt_lookup_remains_read_only_when_archive_is_full(tmp_path, monkeypatch):
    c = client(tmp_path)
    accepted = send(c, request_body()).json()
    before = (tmp_path / "history" / "history.sqlite3").read_bytes()
    monkeypatch.setattr(ArchiveStore, "_capacity", lambda *args: (_ for _ in ()).throw(ValueError("archive capacity unavailable")))
    response = get(c, "/api/history-archive/receipts/" + accepted["archive_id"])
    assert response.status_code == 200 and response.json() == accepted
    assert (tmp_path / "history" / "history.sqlite3").read_bytes() == before


def test_slow_body_cannot_outlive_signature_or_backdate_receipt(tmp_path):
    import asyncio

    import httpx

    async def scenario():
        current = [NOW]
        app = create_archive_app(enabled=True, policy=policy(tmp_path), credentials=(WRITER, READER),
                                 clock=lambda: current[0])
        body = request_body()
        headers = signed_archive_headers(body, WRITER, method="POST", path=PATH, now=NOW)
        async def slow_body():
            yield body[:10]
            current[0] = NOW + timedelta(seconds=600)
            yield body[10:]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://archive.test") as c:
            response = await c.post(PATH, content=slow_body(), headers=headers)
            assert response.status_code == 401
        assert ArchiveStore(policy(tmp_path)).get_receipt(ArchiveStore.archive_id(canonical(bundle())))["status"] == "UNKNOWN"
    asyncio.run(scenario())


def test_slow_body_has_hard_timeout_and_does_not_block_receipt_reads(tmp_path, monkeypatch):
    import asyncio

    import app.workspace.historical_archive_api as module
    import httpx

    monkeypatch.setattr(module, "BODY_READ_TIMEOUT_SECONDS", 0.05, raising=False)
    async def scenario():
        app = create_archive_app(enabled=True, policy=policy(tmp_path), credentials=(WRITER, READER), clock=lambda: NOW)
        body = request_body()
        headers = signed_archive_headers(body, WRITER, method="POST", path=PATH, now=NOW)
        started = asyncio.Event()
        async def slow_body():
            yield body[:10]
            started.set()
            await asyncio.sleep(0.25)
            yield body[10:]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://archive.test") as c:
            post = asyncio.create_task(c.post(PATH, content=slow_body(), headers=headers))
            await started.wait()
            receipt_path = "/api/history-archive/receipts/" + "f" * 64
            read_headers = signed_archive_headers(b"", READER, method="GET", path=receipt_path, now=NOW)
            read = await c.get(receipt_path, headers=read_headers)
            assert read.status_code == 200 and read.json()["status"] == "UNKNOWN"
            response = await post
            assert response.status_code == 408
    asyncio.run(scenario())
