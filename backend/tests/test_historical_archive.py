"""Synthetic archive-only safety regressions. Never read real outboxes/providers."""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from app.workspace.historical_archive import ArchivePolicy, ArchiveStore
from app.workspace.local_display_contract import compute_parts_hashes
from app.workspace.local_display_read import LocalDisplayStore
from app.workspace.shadow_bundle import canonical, digest

GENERATED = datetime(2026, 11, 9, 6, 30, tzinfo=UTC)
NOW = GENERATED + timedelta(days=2)
PRODUCER = ("a" * 40, "b" * 64)


def bundle(sequence=1):
    parts = {"overview": {"rows": [], "generated_at": GENERATED.isoformat()},
             "details": {}, "charts": {}, "sectors": {"sectors": []}}
    return {"manifest": {"contract_version": "local-display-v2", "code_sha": PRODUCER[0],
                         "config_hash": PRODUCER[1], "sequence": sequence,
                         "generated_at": GENERATED.isoformat(),
                         "expires_at": (GENERATED + timedelta(hours=1)).isoformat(),
                         "actionable": False, "universe": ["510300.SH"],
                         "parts_hashes": compute_parts_hashes(parts)}, "parts": parts}


def evidence(**updates):
    value = {"version": "history-evidence-v1", "original_delivery_status": "FAILED_DELIVERY",
             "declared_slot": "2026-11-09T14:30:00+08:00", "market_observed_at": None,
             "attempts": [{"attempted_at": "2026-11-09T14:31:00+08:00", "status": "FAILED_DELIVERY",
                           "error_code": "timeout", "request_id": "request-1"}]}
    value.update(updates)
    return value


def store(tmp_path, **overrides):
    options = dict(root=tmp_path / "archive", protected_roots=(tmp_path / "live", tmp_path / "outbox"),
                   trusted_producers=frozenset({PRODUCER}), max_bytes=32 * 1024 * 1024,
                   min_free_bytes=0, max_payload_bytes=1024 * 1024)
    options.update(overrides)
    return ArchiveStore(ArchivePolicy(**options))


def submit(target, value=None, proof=None, **kwargs):
    raw = canonical(bundle() if value is None else value)
    return target.ingest(raw, proof or evidence(), original_sha256=hashlib.sha256(raw).hexdigest(),
                         submitter_id="archive-writer", now=NOW, **kwargs)


def test_preserves_exact_bytes_and_separate_receipt(tmp_path):
    target = store(tmp_path)
    raw = json.dumps(bundle(), indent=2).encode() + b"\n"
    proof = evidence()
    before = copy.deepcopy(proof)
    result = target.ingest(raw, proof, original_sha256=hashlib.sha256(raw).hexdigest(),
                           submitter_id="archive-writer", now=NOW)
    assert result["status"] == "ARCHIVED"
    assert result["receipt_contract"] == "historical-archive-receipt-v1"
    assert result["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["bundle_id"] == digest(bundle()["manifest"])
    assert result["sequence"] == 1
    assert result["realtime_acceptance"] == "UNKNOWN"
    assert result["original_delivery_status"] == "FAILED_DELIVERY"
    assert result["expired_at_arrival"] is True
    assert result["declared_lateness_seconds"] == 172800
    assert result["verified_slot"] is None
    assert result["evidence_level"] == "UPLOADER_CLAIM"
    assert target.read_original(result["archive_id"]) == raw
    assert target.get_receipt(result["archive_id"]) == result
    assert result["evidence"] == before and proof == before
    assert result["actionable"] is False


def test_duplicate_restart_and_lost_receipt(tmp_path):
    target = store(tmp_path)
    first = submit(target)
    # A client with an uncertain response must query by content-derived archive ID.
    second = submit(store(tmp_path))
    assert first == second
    assert target.get_receipt(first["archive_id"]) == first
    assert target.get_receipt("f" * 64) == {"archive_id": "f" * 64, "status": "UNKNOWN",
                                               "realtime_acceptance": "UNKNOWN"}


def test_duplicate_cannot_silently_replace_evidence(tmp_path):
    target = store(tmp_path)
    first = submit(target)
    with pytest.raises(ValueError, match="evidence_conflict"):
        submit(target, proof=evidence(original_delivery_status="SUPERSEDED"))
    assert target.get_receipt(first["archive_id"]) == first


def test_concurrent_duplicate_and_sequence_conflict(tmp_path):
    target = store(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: submit(target), range(12)))
    assert len({json.dumps(result, sort_keys=True) for result in results}) == 1
    changed = bundle()
    changed["parts"]["overview"]["rows"] = [{"ts_code": "510300.SH", "price": 99}]
    changed["manifest"]["parts_hashes"] = compute_parts_hashes(changed["parts"])
    conflict = submit(target, changed)
    assert conflict["status"] == "QUARANTINED"
    assert "producer_sequence_conflict" in conflict["reasons"]
    assert conflict["conflicts_with"] == [results[0]["archive_id"]]
    assert target.get_receipt(results[0]["archive_id"]) == results[0]


def test_same_sequence_other_producer_is_separate_unknown_identity(tmp_path):
    target = store(tmp_path)
    submit(target)
    changed = bundle()
    changed["manifest"]["code_sha"] = "c" * 40
    result = submit(target, changed)
    assert result["status"] == "QUARANTINED"
    assert result["reasons"] == ["unknown_historical_producer"]
    assert result["conflicts_with"] == []


def test_unknown_slot_is_not_fabricated(tmp_path):
    result = submit(store(tmp_path), proof=evidence(declared_slot=None))
    assert result["verified_slot"] is None
    assert result["declared_lateness_seconds"] is None
    assert result["evidence"]["declared_slot"] is None


@pytest.mark.parametrize("mutation", ["parts", "actionable", "private", "nan", "duplicate", "envelope"])
def test_invalid_original_rejected_without_retaining_private_bytes(tmp_path, mutation):
    target = store(tmp_path)
    value = bundle()
    if mutation == "parts":
        value["parts"]["overview"]["rows"] = ["tampered"]
    elif mutation == "actionable":
        value["manifest"]["actionable"] = True
    elif mutation == "private":
        value["parts"]["details"]["password"] = "DO-NOT-PERSIST-THIS"
        value["manifest"]["parts_hashes"] = compute_parts_hashes(value["parts"])
    elif mutation == "envelope":
        value["extra"] = "unapproved"
    raw = canonical(value)
    if mutation == "nan":
        raw = raw[:-1] + b',"extra":NaN}'
    elif mutation == "duplicate":
        raw = raw[:-1] + b',"parts":{}}'
    result = target.ingest(raw, evidence(), original_sha256=hashlib.sha256(raw).hexdigest(),
                           submitter_id="archive-writer", now=NOW)
    assert result["status"] == "REJECTED"
    assert target.read_original(result["archive_id"]) is None
    assert b"DO-NOT-PERSIST-THIS" not in target.database_path.read_bytes()


def test_sha_mismatch_does_not_store_bytes(tmp_path):
    target = store(tmp_path)
    result = target.ingest(canonical(bundle()), evidence(), original_sha256="0" * 64,
                           submitter_id="archive-writer", now=NOW)
    assert result["status"] == "REJECTED" and "raw_hash_mismatch" in result["reasons"]


@pytest.mark.parametrize("updates", [{"token": "secret"}, {"declared_slot": "2026-11-09 14:30"},
                                      {"attempts": [{"error_code": "https://secret.example"}]},
                                      {"original_delivery_status": "DELIVERED"}])
def test_invalid_evidence_rejected_before_persisting(tmp_path, updates):
    target = store(tmp_path)
    with pytest.raises(ValueError, match="evidence"):
        submit(target, proof=evidence(**updates))


def test_missing_original_gap_is_not_archive_or_market_data(tmp_path):
    target = store(tmp_path)
    result = target.record_gap(evidence(), reason="original_missing", submitter_id="archive-writer", now=NOW)
    assert result["status"] == "GAP_RECORDED"
    assert result["raw_sha256"] is None and result["bundle_id"] is None
    assert result["realtime_acceptance"] == "UNKNOWN"
    assert target.read_original(result["archive_id"]) is None
    assert target.record_gap(evidence(), reason="original_missing", submitter_id="archive-writer", now=NOW) == result


def test_out_of_order_archive_never_changes_live_pointers_or_ledger(tmp_path):
    live = LocalDisplayStore(tmp_path / "live")
    live.publish(bundle(1), now=GENERATED)
    live.publish(bundle(3), now=GENERATED)
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    (outbox / "ledger.json").write_text('{"status":"FAILED_DELIVERY"}')
    before = {str(path.relative_to(tmp_path)): path.read_bytes()
              for root in (tmp_path / "live", outbox) for path in root.rglob("*") if path.is_file()}
    target = store(tmp_path)
    for sequence in (20, 2, 10):
        assert submit(target, bundle(sequence))["status"] == "ARCHIVED"
    with pytest.raises(ValueError, match="historical|identity|sequence"):
        live.publish(bundle(2), now=NOW)
    after = {str(path.relative_to(tmp_path)): path.read_bytes()
             for root in (tmp_path / "live", outbox) for path in root.rglob("*") if path.is_file()}
    assert before == after


@pytest.mark.parametrize("relation", ["same", "child", "parent", pytest.param(
    "symlink", marks=pytest.mark.skipif(
        sys.platform == "win32",
        reason="directory symlinks need Windows privileges; refusal path is exercised on POSIX"))])
def test_store_refuses_overlap_and_symlinks(tmp_path, relation):
    protected = tmp_path / "live"
    protected.mkdir()
    root = {"same": protected, "child": protected / "archive", "parent": tmp_path,
            "symlink": tmp_path / "alias"}[relation]
    if relation == "symlink":
        root.symlink_to(protected, target_is_directory=True)
    with pytest.raises(ValueError, match="isolated|symlink"):
        store(tmp_path, root=root)


def test_no_implicit_trust_and_explicit_protected_paths_required(tmp_path):
    with pytest.raises(ValueError, match="protected"):
        store(tmp_path, protected_roots=())
    result = submit(store(tmp_path, trusted_producers=frozenset()))
    assert result["status"] == "QUARANTINED"


def test_disk_full_and_budget_preserve_prior_records(tmp_path, monkeypatch):
    import app.workspace.historical_archive as module
    target = store(tmp_path)
    first = submit(target)
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: type("Disk", (), {"free": 0})())
    with pytest.raises(ValueError, match="capacity"):
        submit(target, bundle(2))
    assert target.get_receipt(first["archive_id"]) == first
    assert target.get_receipt(target.archive_id(canonical(bundle(2))))["status"] == "UNKNOWN"


def test_write_interruption_rolls_back_bytes_and_receipt(tmp_path, monkeypatch):
    target = store(tmp_path)
    first = submit(target)
    monkeypatch.setattr(target, "_before_commit", lambda _: (_ for _ in ()).throw(OSError("injected failure")))
    with pytest.raises(OSError, match="injected"):
        submit(target, bundle(2))
    recovered = store(tmp_path)
    assert recovered.get_receipt(first["archive_id"]) == first
    assert recovered.get_receipt(target.archive_id(canonical(bundle(2))))["status"] == "UNKNOWN"
    assert submit(recovered, bundle(2))["status"] == "ARCHIVED"


def test_original_read_detects_storage_corruption(tmp_path):
    target = store(tmp_path)
    receipt = submit(target)
    with sqlite3.connect(target.database_path) as db:
        db.execute("UPDATE records SET raw=? WHERE archive_id=?", (b"corrupt", receipt["archive_id"]))
    with pytest.raises(ValueError, match="integrity"):
        target.read_original(receipt["archive_id"])


def test_real_process_exit_recovers_sqlite_rollback_journal(tmp_path):
    import os
    import subprocess
    import sys

    target = store(tmp_path)
    first = submit(target)
    command = '''
import json, os, sys
from pathlib import Path
from app.workspace.historical_archive import ArchivePolicy, ArchiveStore
request = json.load(sys.stdin)
root = Path(request['root'])
store = ArchiveStore(ArchivePolicy(root=root / 'archive', protected_roots=(root / 'live', root / 'outbox'),
    trusted_producers=frozenset({('a' * 40, 'b' * 64)}), min_free_bytes=0,
    max_bytes=32 * 1024 * 1024, max_payload_bytes=1024 * 1024))
store._before_commit = lambda db: os._exit(93)
from datetime import datetime
store.ingest(request['raw'].encode(), request['evidence'], original_sha256=request['sha'],
             submitter_id='archive-writer', now=datetime.fromisoformat(request['now']))
'''
    raw = canonical(bundle(2))
    request = dict(root=str(tmp_path), raw=raw.decode(), evidence=evidence(),
                   sha=hashlib.sha256(raw).hexdigest(), now=NOW.isoformat())
    env = dict(os.environ, PYTHONPATH=str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    result = subprocess.run([sys.executable, "-c", command], input=canonical(request),
                            capture_output=True, env=env, timeout=30)
    assert result.returncode == 93, result.stderr.decode()
    recovered = store(tmp_path)
    assert recovered.get_receipt(first["archive_id"]) == first
    assert recovered.get_receipt(recovered.archive_id(raw))["status"] == "UNKNOWN"
    assert submit(recovered, bundle(2))["status"] == "ARCHIVED"


def test_quota_stops_without_eviction_or_crossing_peak_budget(tmp_path):
    target = store(tmp_path, max_bytes=1024 * 1024)
    accepted = []
    # Synthetic bounded rows inflate originals while staying inside the same contract.
    for sequence in range(1, 100):
        value = bundle(sequence)
        value["parts"]["overview"]["rows"] = [{"ts_code": "510300.SH", "name": "public" * 1000}]
        value["manifest"]["parts_hashes"] = compute_parts_hashes(value["parts"])
        try:
            result = submit(target, value)
        except ValueError as exc:
            assert "capacity" in str(exc)
            break
        accepted.append(result)
        assert target._used_bytes() <= target.policy.max_bytes
    else:
        pytest.fail("bounded archive should have exhausted capacity")
    assert accepted
    for result in accepted:
        assert target.get_receipt(result["archive_id"]) == result
        assert target.read_original(result["archive_id"]) is not None


def test_trust_change_does_not_promote_an_existing_quarantine(tmp_path):
    quarantined = submit(store(tmp_path, trusted_producers=frozenset()))
    assert quarantined["status"] == "QUARANTINED"
    assert submit(store(tmp_path)) == quarantined


def test_claimed_hash_rejection_does_not_poison_valid_original_id(tmp_path):
    target = store(tmp_path)
    raw = canonical(bundle())
    rejected = target.ingest(raw, evidence(), original_sha256="0" * 64,
                              submitter_id="archive-writer", now=NOW)
    accepted = submit(target)
    assert rejected["archive_id"] != accepted["archive_id"]
    assert accepted["status"] == "ARCHIVED"


@pytest.mark.parametrize("variant", ["generated_future", "slot_future", "observation_after_generation"])
def test_contradictory_claims_quarantined_without_rewriting(tmp_path, variant):
    value = bundle()
    proof = evidence()
    if variant == "generated_future":
        value["manifest"]["generated_at"] = (NOW + timedelta(hours=1)).isoformat()
        value["manifest"]["expires_at"] = (NOW + timedelta(hours=2)).isoformat()
    elif variant == "slot_future":
        proof["declared_slot"] = (NOW + timedelta(hours=1)).isoformat()
    else:
        proof["market_observed_at"] = (GENERATED + timedelta(minutes=1)).isoformat()
    target = store(tmp_path)
    result = submit(target, value, proof)
    assert result["status"] == "QUARANTINED"
    assert target.read_original(result["archive_id"]) == canonical(value)
    assert result["evidence"] == proof
