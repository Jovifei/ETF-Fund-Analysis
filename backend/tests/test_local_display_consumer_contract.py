"""Trusted local-display consumption. Synthetic files only; no providers or DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.workspace import local_display_read as ldr
from app.workspace.local_display_contract import compute_parts_hashes
from app.workspace.local_display_read import LocalDisplayReader, LocalDisplayStore
from app.workspace.shadow_bundle import canonical, digest

NOW = datetime(2026, 10, 23, 7, tzinfo=timezone.utc)


def bundle(sequence):
    parts = {"overview": {"rows": [], "generated_at": NOW.isoformat()},
             "details": {}, "charts": {}, "sectors": {"sectors": []},
             "market_context": {"items": [], "availability": "unavailable",
                                "reason": "optional_refresh_failed"}}
    return {"manifest": {"contract_version": "local-display-v2", "code_sha": "a" * 40,
                         "config_hash": "b" * 64, "sequence": sequence,
                         "generated_at": NOW.isoformat(), "expires_at": (NOW + timedelta(hours=1)).isoformat(),
                         "actionable": False, "universe": ["510300.SH"],
                         "parts_hashes": compute_parts_hashes(parts)}, "parts": parts}


def files(root):
    return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file() and not p.name.startswith('.')}


@pytest.mark.parametrize("variant", ["never_accepted", "changed_identity", "wrong_runtime"])
def test_unknown_historical_identity_cannot_be_acknowledged(tmp_path, variant):
    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(1), now=NOW)
    store.publish(bundle(3), now=NOW)
    value = bundle(2 if variant == "never_accepted" else 1)
    if variant == "changed_identity":
        value["parts"]["overview"]["note"] = "not previously accepted"
        value["manifest"]["parts_hashes"] = compute_parts_hashes(value["parts"])
    if variant == "wrong_runtime":
        value["manifest"]["code_sha"] = "c" * 40
    before = files(tmp_path)
    with pytest.raises(ValueError, match="historical|identity|sequence"):
        store.publish(value, now=NOW)
    assert files(tmp_path) == before


def test_exact_historical_restore_survives_restart_and_expiry(tmp_path):
    store = LocalDisplayStore(tmp_path)
    first = store.publish(bundle(1), now=NOW)
    store.publish(bundle(2), now=NOW)
    store.publish(bundle(3), now=NOW)
    for path in tmp_path.glob('bundle_1_*.json'):
        path.unlink()
    before = {name: (tmp_path / name).read_bytes() for name in ('latest.json', 'previous.json')}
    restored = LocalDisplayStore(tmp_path).publish(bundle(1), now=NOW + timedelta(days=2))
    assert restored['status'] == 'already_accepted' and restored['bundle_id'] == first['bundle_id']
    assert all((tmp_path / name).read_bytes() == value for name, value in before.items())


def test_orphan_file_is_not_historical_acceptance_proof(tmp_path):
    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(3), now=NOW)
    value = bundle(1)
    path = tmp_path / f"bundle_1_{digest(value['manifest'])[:16]}.json"
    path.write_bytes(canonical(value))
    before = files(tmp_path)
    with pytest.raises(ValueError, match='historical|identity'):
        store.publish(value, now=NOW)
    assert files(tmp_path) == before


@pytest.mark.parametrize('selector', ['sequence', 'hash'])
def test_pinned_reads_do_not_parse_other_generations(tmp_path, monkeypatch, selector):
    store = LocalDisplayStore(tmp_path)
    for seq in range(1, 9):
        store.publish(bundle(seq), now=NOW)
    ldr.clear_bundle_cache()
    monkeypatch.setattr(ldr, '_BUNDLE_CACHE_MAX', 2)
    native = Path.read_bytes
    reads = []
    def track(path):
        if path.name.startswith('bundle_'):
            reads.append(path.name)
        return native(path)
    monkeypatch.setattr(Path, 'read_bytes', track)
    generation = '4' if selector == 'sequence' else digest(bundle(4)['manifest'])
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: store.load_bundle(generation), range(8)))
    assert all(value['manifest']['sequence'] == 4 for value in values)
    assert len(reads) == 1 and reads[0].startswith('bundle_4_'), reads


def test_missing_generation_does_not_read_or_fall_back(tmp_path, monkeypatch):
    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(1), now=NOW)
    monkeypatch.setattr(store, '_load_file', lambda *a, **k: pytest.fail('unrelated bundle read'))
    assert store.load_bundle('987654321') is None


def test_optional_status_and_generation_survive_reader(tmp_path):
    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(1), now=NOW)
    reader = LocalDisplayReader(store)
    part = reader.read_market_context_view('1')
    assert part['items'] == []
    assert part['availability'] == 'unavailable'
    assert part['reason'] == 'optional_refresh_failed'
    assert part['generation'] == 1
    assert part['research_source'] == 'local_bundle'
    assert reader.read_market_context('1') is None
    assert reader.read_overview(generation='1')['research_source'] == 'local_bundle'


def test_missing_optional_generation_has_explicit_reason(tmp_path):
    reader = LocalDisplayReader(LocalDisplayStore(tmp_path))
    part = reader.read_market_context_view('999')
    assert part['availability'] == 'unavailable'
    assert part['reason'] == 'local_display_generation_unavailable'
    assert part['generation'] is None


def test_sector_breadth_adapter_preserves_unknown_not_zero(tmp_path):
    value = bundle(1)
    value['parts']['sectors'] = {'sectors': [{'sector_name': 'market', 'board_type': 'market',
        'trade_date': '2026-10-23', 'up_count': 12, 'down_count': None}],
        'availability': 'carried_forward', 'reason': 'fast_slot_reuses_same_day_refresh'}
    value['manifest']['parts_hashes'] = compute_parts_hashes(value['parts'])
    store = LocalDisplayStore(tmp_path)
    store.publish(value, now=NOW)
    result = LocalDisplayReader(store).read_sectors('1')
    assert result['boards'][0]['breadth'] == {'up': 12, 'down': None, 'flat': None, 'total': None}
    assert result['boards'][0]['source_as_of'] == '2026-10-23'
    assert result['boards'][0].get('source') is None
