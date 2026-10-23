"""Behavioral receipt-proof regressions against the actual receiver and store."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.workspace.shadow_auth import signed_headers
from app.workspace.shadow_bundle import canonical, digest
from test_receiver_safety import NOW, receiver_settings, rehash, snapshot, v2


from app.workspace import local_display_read as reader_module, shadow_api as api_module

Store = reader_module.LocalDisplayStore


@pytest.mark.parametrize("existing", [False, True])
def test_unknown_history_not_proved_by_valid_body_or_disk(tmp_path, existing):
    store = Store(tmp_path)
    store.publish(v2(2), now=NOW)
    store.publish(v2(3), now=NOW)
    unknown = v2(1)
    if existing:
        identity = digest(unknown["manifest"])
        (tmp_path / f"bundle_1_{identity[:16]}.json").write_bytes(canonical(unknown))
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="not accepted|proof"):
        store.publish(unknown, now=NOW + timedelta(days=1))
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("changed_field", ["body", "code_sha", "config_hash"])
def test_history_identity_covers_body_code_and_config(tmp_path, changed_field):
    store = Store(tmp_path)
    store.publish(v2(1), now=NOW)
    store.publish(v2(2), now=NOW)
    store.publish(v2(3), now=NOW)
    changed = deepcopy(v2(1))
    if changed_field == "body":
        changed["parts"]["overview"]["description"] = "unaccepted"
        rehash(changed)
    else:
        changed["manifest"][changed_field] = "c" * (40 if changed_field == "code_sha" else 64)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="not accepted|proof"):
        store.publish(changed, now=NOW + timedelta(days=1))
    assert snapshot(tmp_path) == before


def test_proved_expired_evicted_history_restores_after_restart_without_promotion(tmp_path):
    store = Store(tmp_path)
    first = store.publish(v2(1), now=NOW)
    store.publish(v2(2), now=NOW)
    store.publish(v2(3), now=NOW)
    next(tmp_path.glob("bundle_1_*.json")).unlink()
    before = {name: (tmp_path / name).read_bytes() for name in ("latest.json", "previous.json")}
    again = Store(tmp_path).publish(v2(1), now=NOW + timedelta(days=1))
    assert again["status"] == "already_accepted"
    assert again["bundle_id"] == first["bundle_id"]
    assert set(again) == {"bundle_id", "manifest_hash", "sequence", "status", "received_at"}
    assert {name: (tmp_path / name).read_bytes() for name in before} == before


@pytest.mark.parametrize("after_replace", [False, True])
def test_failed_atomic_pointer_commit_rolls_back_history(tmp_path, monkeypatch, after_replace):
    store = Store(tmp_path)
    store.publish(v2(1), now=NOW)
    store.publish(v2(2), now=NOW)
    before = snapshot(tmp_path)
    native = store._atomic
    failed = False
    def fail_once(path, data):
        nonlocal failed
        if path == store.latest_link and not failed:
            failed = True
            if after_replace:
                native(path, data)
            raise OSError("synthetic final pointer failure")
        return native(path, data)
    monkeypatch.setattr(store, "_atomic", fail_once)
    with pytest.raises(OSError):
        store.publish(v2(3), now=NOW)
    assert snapshot(tmp_path) == before


def test_crash_before_latest_never_proves_orphan_generation(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.publish(v2(1), now=NOW)
    store.publish(v2(2), now=NOW)
    native = store._atomic
    def crash(path, data):
        if path == store.latest_link:
            raise KeyboardInterrupt("synthetic stop before atomic acceptance")
        return native(path, data)
    monkeypatch.setattr(store, "_atomic", crash)
    with pytest.raises(KeyboardInterrupt):
        store.publish(v2(3), now=NOW)
    restarted = Store(tmp_path)
    restarted.publish(v2(4), now=NOW)
    with pytest.raises(ValueError, match="not accepted|proof"):
        restarted.publish(v2(3), now=NOW + timedelta(days=1))


@pytest.mark.parametrize("damage", ["malformed", "version", "identity", "size", "symlink"])
def test_corrupt_pointer_history_never_reconstructed_from_files(tmp_path, monkeypatch, damage):
    store = Store(tmp_path)
    for seq in (1, 2, 3):
        store.publish(v2(seq), now=NOW)
    pointer = json.loads(store.latest_link.read_bytes())
    if damage == "malformed":
        store.latest_link.write_bytes(b'{"accepted":[')
    elif damage == "size":
        store.latest_link.write_bytes(b" " * 65537)
    elif damage == "symlink":
        native = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == store.latest_link or native(path))
    else:
        if damage == "version":
            pointer["acceptance_history_version"] = "unsupported"
        else:
            pointer["accepted"][-1]["bundle_id"] = "0" * 64
        store.latest_link.write_bytes(canonical(pointer))
    with pytest.raises(ValueError, match="pointer|symlink|unsafe"):
        store.publish(v2(1), now=NOW + timedelta(days=1))


def test_history_pruned_identity_stays_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(reader_module, "ACCEPTANCE_HISTORY_LIMIT", 3)
    store = Store(tmp_path, max_generations=3)
    for seq in range(1, 8):
        store.publish(v2(seq), now=NOW)
    assert len(json.loads(store.latest_link.read_bytes())["accepted"]) == 3
    with pytest.raises(ValueError, match="not accepted|proof"):
        Store(tmp_path, max_generations=3).publish(v2(1), now=NOW + timedelta(days=1))


def test_legacy_pointers_prove_only_their_own_identity(tmp_path):
    store = Store(tmp_path)
    for seq in (1, 2, 3):
        store.publish(v2(seq), now=NOW)
    for path in (store.latest_link, store.previous_link):
        pointer = json.loads(path.read_bytes())
        pointer.pop("accepted")
        pointer.pop("acceptance_history_version")
        path.write_bytes(canonical(pointer))
    assert store.publish(v2(2), now=NOW + timedelta(days=1))["status"] == "already_accepted"
    assert store.publish(v2(3), now=NOW + timedelta(days=1))["status"] == "already_accepted"
    with pytest.raises(ValueError, match="not accepted|proof"):
        store.publish(v2(1), now=NOW + timedelta(days=1))


def test_historical_restore_charges_temporary_peak(tmp_path):
    store = Store(tmp_path)
    for seq in (1, 2, 3):
        store.publish(v2(seq), now=NOW)
    next(tmp_path.glob("bundle_1_*.json")).unlink()
    store.max_bytes = store.domain.used_bytes() + len(canonical(v2(1))) - 1
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="capacity"):
        store.publish(v2(1), now=NOW + timedelta(days=1))
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("proved", [False, True])
def test_signed_api_historical_cutover_requires_actual_history(tmp_path, monkeypatch, proved):
    monkeypatch.setattr(api_module, "get_settings", lambda: receiver_settings(tmp_path))
    old = v2(1)
    old["manifest"].update(code_sha="c" * 40, config_hash="d" * 64)
    store = Store(tmp_path / "v2")
    if proved:
        store.publish(old, now=NOW)
    for seq in (2, 3):
        store.publish(v2(seq), now=NOW)
    if proved:
        next((tmp_path / "v2").glob("bundle_1_*.json")).unlink()
    app = FastAPI()
    app.include_router(api_module.router)
    body = canonical(old)
    headers = {**signed_headers(body, "synthetic", "s" * 32), "Authorization": "Bearer " + "x" * 32}
    result = TestClient(app).post("/api/shadow/sync", content=body, headers=headers)
    assert result.status_code == (200 if proved else 409), result.text
