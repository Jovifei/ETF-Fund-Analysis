"""Bundle parse cache: one parse per immutable file, invalidated on rewrite."""
from datetime import datetime, timezone
import json
import os
import threading

from app.workspace import local_display_read as ldr
from app.workspace.local_display_contract import CONTRACT_VERSION, compute_parts_hashes
from app.workspace.local_display_read import LocalDisplayReader, LocalDisplayStore


def _bundle(seq=1):
    parts = {
        "overview": {"rows": [{"ts_code": "510300.SH", "name": "300ETF", "theme_l1": "x", "actionable": False}],
                     "total": 1, "snapshot_id": f"s{seq}", "generated_at": "2026-10-12T06:30:00Z"},
        "details": {}, "charts": {}, "sectors": {"sectors": []}, "market_context": {"items": []},
    }
    return {"manifest": {"contract_version": CONTRACT_VERSION, "code_sha": "a" * 40, "config_hash": "c" * 64,
                         "sequence": seq, "generated_at": "2026-10-12T06:30:00Z", "expires_at": "2026-10-12T08:30:00Z",
                         "actionable": False, "data_origin": "local_research", "universe": ["510300.SH"],
                         "parts_hashes": compute_parts_hashes(parts)}, "parts": parts}


def _count_parses(monkeypatch):
    calls = {"n": 0}
    real = ldr.json.loads

    def counting(data, *a, **k):
        if isinstance(data, (bytes, bytearray)) and len(data) > 1000:
            calls["n"] += 1
        return real(data, *a, **k)
    monkeypatch.setattr(ldr.json, "loads", counting)
    return calls


def _store(tmp_path):
    store = LocalDisplayStore(tmp_path / "store")
    store.publish(_bundle(), now=datetime(2026, 10, 12, 7, tzinfo=timezone.utc))
    return store


def test_repeated_and_concurrent_reads_parse_once(tmp_path, monkeypatch):
    ldr.clear_bundle_cache()
    store = _store(tmp_path)
    ldr.clear_bundle_cache()
    calls = _count_parses(monkeypatch)
    reader = LocalDisplayReader(store, code_sha="a" * 40, config_hash="c" * 64)
    results = []
    threads = [threading.Thread(target=lambda: results.append(reader.read_overview(1)["total"])) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert results == [1] * 8
    assert calls["n"] == 1


def test_rewritten_file_is_revalidated(tmp_path):
    ldr.clear_bundle_cache()
    store = _store(tmp_path)
    assert store.load_bundle(None) is not None
    path = next((tmp_path / "store").glob("bundle_*.json"))
    raw = json.loads(path.read_bytes())
    raw["parts"]["overview"]["rows"][0]["name"] = "tampered"
    tmp = path.with_name(".tmp-rewrite")
    tmp.write_bytes(json.dumps(raw).encode())
    os.replace(tmp, path)
    assert store.load_bundle(None) is None


def test_cache_disabled_when_zero(tmp_path, monkeypatch):
    ldr.clear_bundle_cache()
    store = _store(tmp_path)
    monkeypatch.setattr(ldr, "_BUNDLE_CACHE_MAX", 0)
    calls = _count_parses(monkeypatch)
    store.load_bundle(None)
    store.load_bundle(None)
    assert calls["n"] == 4
    assert len(ldr._BUNDLE_CACHE) == 0
