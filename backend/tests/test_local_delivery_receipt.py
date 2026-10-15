from datetime import datetime, timezone
import pytest
from app.workspace.local_display_contract import CONTRACT_VERSION, compute_parts_hashes
from app.workspace.local_display_read import LocalDisplayStore


def test_delivery_receipt_idempotence_and_replay(tmp_path):
    store_dir = tmp_path / "store"
    store = LocalDisplayStore(store_dir)

    parts = {
        "overview": {"rows": []},
        "details": {},
        "charts": {},
        "sectors": {"sectors": []},
    }
    hashes = compute_parts_hashes(parts)
    bundle = {
        "manifest": {
            "contract_version": CONTRACT_VERSION,
            "code_sha": "a" * 40,
            "config_hash": "c" * 64,
            "sequence": 1,
            "generated_at": "2026-10-12T06:30:00Z",
            "expires_at": "2026-10-12T08:30:00Z",
            "actionable": False,
            "data_origin": "local_research",
            "universe": ["510300.SH"],
            "parts_hashes": hashes,
        },
        "parts": parts,
    }

    # First delivery
    receipt1 = store.publish(bundle, now=datetime(2026, 10, 12, 7, tzinfo=timezone.utc))
    assert receipt1["status"] == "accepted"

    # Second delivery with identical bundle
    receipt2 = store.publish(bundle, now=datetime(2026, 10, 12, 7, tzinfo=timezone.utc))
    assert receipt2["status"] == "already_accepted"
    assert receipt2["bundle_id"] == receipt1["bundle_id"]


def test_delivery_rejects_corrupted_manifest(tmp_path):
    store_dir = tmp_path / "store"
    store = LocalDisplayStore(store_dir)

    bundle = {
        "manifest": {
            "contract_version": "invalid-version",
        },
        "parts": {},
    }
    with pytest.raises(ValueError, match="contract_version"):
        store.publish(bundle, now=datetime(2026, 10, 12, 7, tzinfo=timezone.utc))
