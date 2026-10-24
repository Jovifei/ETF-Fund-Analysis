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


def test_legacy_upgrade_uses_only_current_and_previous_pointer_proof(tmp_path):
    import json
    store = LocalDisplayStore(tmp_path)
    for seq in (1, 2, 3):
        store.publish(bundle(seq), now=NOW)
    for name in ('latest.json', 'previous.json'):
        path = tmp_path / name
        pointer = json.loads(path.read_bytes())
        pointer.pop('accepted')
        pointer.pop('acceptance_history_version')
        path.write_bytes(canonical(pointer))
    assert store.load_bundle('1') is not None  # Legacy history remains readable.
    with pytest.raises(ValueError, match='historical identity'):
        store.publish(bundle(1), now=NOW)
    assert store.publish(bundle(2), now=NOW)['status'] == 'already_accepted'
    store.publish(bundle(4), now=NOW)
    assert store.publish(bundle(2), now=NOW)['status'] == 'already_accepted'


def test_pruned_acceptance_proof_is_not_recreated_from_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ldr, 'ACCEPTANCE_HISTORY_LIMIT', 3)
    store = LocalDisplayStore(tmp_path)
    for seq in range(1, 6):
        store.publish(bundle(seq), now=NOW)
    assert store.load_bundle('1') is not None
    with pytest.raises(ValueError, match='pruned'):
        store.publish(bundle(1), now=NOW)
    assert store.publish(bundle(3), now=NOW)['status'] == 'already_accepted'


@pytest.mark.parametrize('mutation', ['duplicate', 'wrong_head', 'missing_version', 'too_many'])
def test_corrupt_acceptance_history_fails_closed(tmp_path, mutation):
    import json
    store = LocalDisplayStore(tmp_path)
    for seq in (1, 2):
        store.publish(bundle(seq), now=NOW)
    pointer = json.loads(store.latest_link.read_bytes())
    if mutation == 'duplicate':
        pointer['accepted'].insert(0, pointer['accepted'][0])
    elif mutation == 'wrong_head':
        pointer['accepted'][-1]['bundle_id'] = 'f' * 64
    elif mutation == 'missing_version':
        pointer.pop('acceptance_history_version')
    else:
        pointer['accepted'] *= 256
    store.latest_link.write_bytes(canonical(pointer))
    before = files(tmp_path)
    with pytest.raises(ValueError, match='pointer'):
        store.publish(bundle(3), now=NOW)
    assert files(tmp_path) == before


def test_failed_pointer_commit_does_not_create_acceptance_proof(tmp_path, monkeypatch):
    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(1), now=NOW)
    store.publish(bundle(2), now=NOW)
    before = files(tmp_path)
    native = store._atomic
    def fail_latest(path, data):
        if path == store.latest_link:
            raise OSError('synthetic interrupted activation')
        return native(path, data)
    monkeypatch.setattr(store, '_atomic', fail_latest)
    with pytest.raises(OSError):
        store.publish(bundle(3), now=NOW)
    assert files(tmp_path) == before
    monkeypatch.setattr(store, '_atomic', native)
    store.publish(bundle(4), now=NOW)
    with pytest.raises(ValueError, match='historical identity'):
        store.publish(bundle(3), now=NOW)


def test_acceptance_history_is_included_in_peak_budget(tmp_path):
    store = LocalDisplayStore(tmp_path)
    for seq in (1, 2):
        store.publish(bundle(seq), now=NOW)
    before = files(tmp_path)
    store.max_bytes = store.domain.used_bytes() + len(canonical(bundle(3)))
    with pytest.raises(ValueError, match='capacity'):
        store.publish(bundle(3), now=NOW)
    assert files(tmp_path) == before


@pytest.mark.parametrize('offset', [-2, 2])
def test_new_expired_or_future_activation_cannot_create_proof(tmp_path, offset):
    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(1), now=NOW)
    before = files(tmp_path)
    with pytest.raises(ValueError, match='expired|future'):
        store.publish(bundle(2), now=NOW + timedelta(hours=offset))
    assert files(tmp_path) == before


def test_sequence_collision_blocks_alias_but_not_exact_hash(tmp_path):
    store = LocalDisplayStore(tmp_path)
    one = bundle(1)
    two = bundle(1)
    two['parts']['overview']['note'] = 'conflicting'
    two['manifest']['parts_hashes'] = compute_parts_hashes(two['parts'])
    for value in (one, two):
        identity = digest(value['manifest'])
        (tmp_path / f'bundle_1_{identity[:16]}.json').write_bytes(canonical(value))
    assert store.load_bundle('1') is None
    assert store.load_bundle(digest(one['manifest'])) == one


def test_accepted_history_remains_bounded_at_production_limit(tmp_path):
    import json
    store = LocalDisplayStore(tmp_path, max_generations=2)
    for seq in range(1, ldr.ACCEPTANCE_HISTORY_LIMIT + 3):
        store.publish(bundle(seq), now=NOW)
    pointer = json.loads(store.latest_link.read_bytes())
    assert len(pointer['accepted']) == ldr.ACCEPTANCE_HISTORY_LIMIT
    assert store.latest_link.stat().st_size < 65536
    with pytest.raises(ValueError, match='pruned'):
        store.publish(bundle(1), now=NOW)


def test_api_optional_status_is_same_generation_without_database_fallback(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from fastapi import Response
    from app.workspace import api
    from app.services.market_context_service import MarketContextService

    store = LocalDisplayStore(tmp_path)
    store.publish(bundle(1), now=NOW)
    settings = SimpleNamespace(workspace_research_source='local_bundle',
        local_display_v2_store_root=tmp_path, local_display_v2_max_bytes=64 * 1024 * 1024,
        shadow_sync_code_sha='a' * 40, shadow_sync_config_hash='b' * 64, timezone=timezone.utc)
    monkeypatch.setattr(MarketContextService, 'latest_view', lambda *a, **k: pytest.fail('database fallback'))
    class NoDatabase:
        def __getattr__(self, name):
            pytest.fail('research GET accessed database: ' + name)
    db = NoDatabase()
    market = api.context_read_view(db, settings, Response(), None, generation='1')
    indexes = api.index_summaries(db, settings, None, Response(), generation='1')
    sectors = api.sectors(db, settings, None, generation='1')
    overview = api.overview(db, settings, None, horizon=1, offset=0, limit=1, theme=None, generation='1')
    assert {value['generation'] for value in (market, indexes, sectors, overview)} == {1}
    assert market['reason'] == indexes['reason'] == 'optional_refresh_failed'
    assert market['latest_view'] == indexes['items'] == []
    assert market['provider_called'] is indexes['provider_called'] is False
    assert overview['research_source'] == 'local_bundle'


def test_api_missing_local_data_does_not_query_cloud_catalog(tmp_path):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.workspace import api
    settings = SimpleNamespace(workspace_research_source='local_bundle',
        local_display_v2_store_root=tmp_path, local_display_v2_max_bytes=64 * 1024 * 1024,
        shadow_sync_code_sha='a' * 40, shadow_sync_config_hash='b' * 64)
    class NoDatabase:
        def __getattr__(self, name):
            pytest.fail('missing local data must not query cloud catalog: ' + name)
    with pytest.raises(HTTPException) as error:
        api.detail('510300.SH', NoDatabase(), settings, None, generation='999')
    assert error.value.status_code == 404 and error.value.detail == 'local_display_data_unavailable'
    with pytest.raises(HTTPException) as error:
        api.overview(NoDatabase(), settings, None, horizon=1, offset=0, limit=1, theme=None, generation='999')
    assert error.value.status_code == 404 and error.value.detail == 'local_display_generation_unavailable'


def test_acceptance_history_byte_limit_never_commits_unreadable_pointer(tmp_path):
    store = LocalDisplayStore(tmp_path, max_generations=2)
    for seq in range(1, 257):
        value = bundle(10 ** 190 + seq)
        before = store.latest_link.read_bytes() if store.latest_link.exists() else None
        try:
            store.publish(value, now=NOW)
        except ValueError as error:
            assert str(error) == 'acceptance history exceeds pointer limit'
            assert store.latest_link.read_bytes() == before
            assert store.load_bundle() is not None
            break
    else:
        pytest.fail('large sequence history must respect the pointer byte cap')
