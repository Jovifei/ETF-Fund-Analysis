"""Pinned-generation selectors: decimal sequences are not limited to hash width."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.workspace import local_display_read as ldr
from app.workspace.local_display_contract import compute_parts_hashes
from app.workspace.local_display_read import LocalDisplayStore
from app.workspace.shadow_bundle import digest

NOW = datetime(2026, 10, 23, 7, tzinfo=timezone.utc)


def bundle(sequence):
    parts = {"overview": {"rows": []}, "details": {}, "charts": {}, "sectors": {"sectors": []}}
    return {"manifest": {"contract_version": "local-display-v2", "code_sha": "a" * 40,
                         "config_hash": "b" * 64, "sequence": sequence,
                         "generated_at": NOW.isoformat(), "expires_at": (NOW + timedelta(hours=1)).isoformat(),
                         "actionable": False, "universe": ["510300.SH"],
                         "parts_hashes": compute_parts_hashes(parts)}, "parts": parts}


@pytest.mark.parametrize("digits", [16, 63, 64, 65, 191])
@pytest.mark.parametrize("as_text", [False, True], ids=["integer", "string"])
def test_published_long_sequence_is_readable_by_exact_generation(tmp_path, monkeypatch, digits, as_text):
    sequence = int("9" * digits)
    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(1), now=NOW)
    accepted = store.publish(bundle(sequence), now=NOW)
    store.publish(bundle(sequence + 1), now=NOW)
    ldr.clear_bundle_cache()
    native = Path.read_bytes
    reads = []

    def track(path):
        if path.name.startswith("bundle_"):
            reads.append(path.name)
        return native(path)

    monkeypatch.setattr(Path, "read_bytes", track)
    generation = str(sequence) if as_text else sequence
    loaded = LocalDisplayStore(tmp_path).load_bundle(generation)
    assert loaded is not None
    assert loaded["manifest"]["sequence"] == sequence
    assert digest(loaded["manifest"]) == accepted["bundle_id"]
    assert reads == [f"bundle_{sequence}_{accepted['bundle_id'][:16]}.json"]


def test_numeric_full_hash_and_sequence_collision_is_ambiguous(tmp_path, monkeypatch):
    alias = "1" * 64
    original = ldr.digest

    def identities(value):
        if isinstance(value, dict) and "contract_version" in value:
            return alias if value["sequence"] == 1 else "b" * 64
        return original(value)

    monkeypatch.setattr(ldr, "digest", identities)
    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(1), now=NOW)
    store.publish(bundle(int(alias)), now=NOW)
    # Both candidates are valid: string aliases cannot silently choose either.
    assert store.load_bundle(alias) is None
    assert store.load_bundle(int(alias))["manifest"]["sequence"] == int(alias)
    assert store.load_bundle("b" * 64)["manifest"]["sequence"] == int(alias)


@pytest.mark.parametrize("selector", ["9" * 65, "a" * 65, "9" * 190, "-" + "9" * 64])
def test_missing_or_invalid_long_selector_never_loads_unrelated_bundles(tmp_path, monkeypatch, selector):
    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(1), now=NOW)
    monkeypatch.setattr(store, "_load_file", lambda *a, **k: pytest.fail("unrelated bundle read"))
    assert store.load_bundle(selector) is None
