"""Failure-first tests for an atomic, bounded shadow generation store."""
from datetime import datetime, timedelta, timezone
import pytest
from app.workspace.shadow_bundle import ShadowStore, make_bundle

NOW = datetime(2026, 10, 11, 6, 30, tzinfo=timezone.utc)
def bundle(sequence=1):
    chart = {
        'ts_code': '510300.SH',
        'as_of': NOW.isoformat(),
        'source_as_of': None,
        'interval': '1d',
        'available': False,
        'qualification': 'UNKNOWN',
        'research_only': True,
        'actionable': False,
        'cost_overlay_allowed': False,
        'research_cost_overlay_allowed': False,
        'unsupported_intervals': ['1w', '1mo', '5m', '15m'],
        'bars': [],
        'research_bars': [],
    }
    return make_bundle({'rows': [{'ts_code': '510300.SH'}]}, {'510300.SH': chart}, {'references': []}, sequence=sequence, generated_at=NOW, expires_at=NOW+timedelta(hours=1), code_sha='a'*40, config_hash='b'*64)

def test_complete_generation_and_replay(tmp_path):
    store=ShadowStore(tmp_path, code_sha='a'*40, config_hash='b'*64)
    first=bundle(); receipt=store.publish(first, now=NOW)
    assert store.read(now=NOW)['bundle_id']==receipt['bundle_id']
    assert store.read(now=NOW)['charts']['510300.SH']['bars']==[]
    with pytest.raises(ValueError): store.publish(first, now=NOW)
    store.publish(bundle(2), now=NOW)
    assert store.read(now=NOW)['sequence']==2
    assert (tmp_path/'previous.json').exists()

def test_interruption_keeps_previous(tmp_path, monkeypatch):
    store=ShadowStore(tmp_path, code_sha='a'*40, config_hash='b'*64);store.publish(bundle(),now=NOW)
    import app.workspace.shadow_bundle as module
    original=module.os.replace
    def fail(src,dst):
        if str(dst).endswith('latest.json'): raise OSError('interrupted')
        return original(src,dst)
    monkeypatch.setattr(module.os,'replace',fail)
    with pytest.raises(OSError):store.publish(bundle(2),now=NOW)
    assert store.read(now=NOW)['sequence']==1

@pytest.mark.parametrize('mutation', ['nan','path','missing','version','future','hash','expired','private'])
def test_reject_invalid(tmp_path, mutation):
    value=bundle()
    if mutation=='nan':value['blobs']['board']['rows'][0]['x']=float('nan')
    if mutation=='path':value['manifest']['parts']['../escape']=value['manifest']['parts'].pop('board')
    if mutation=='missing':del value['blobs']['charts']
    if mutation=='version':value['manifest']['contract']='unknown'
    if mutation=='future':value['manifest']['generated_at']=(NOW+timedelta(hours=1)).isoformat()
    if mutation=='hash':value['manifest']['parts']['board']='c'*64
    if mutation=='expired':value['manifest']['expires_at']=NOW.isoformat()
    if mutation=='private':value['blobs']['board']['holdings']=[]
    with pytest.raises(ValueError):ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64).publish(value,now=NOW)

def test_capacity_and_collision(tmp_path):
    store=ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64,max_bytes=10)
    with pytest.raises(ValueError):store.publish(bundle(),now=NOW)
    store=ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64)
    value=bundle(); digest=value['manifest']['parts']['board']
    (tmp_path/'blobs').mkdir(exist_ok=True);(tmp_path/'blobs'/digest).write_bytes(b'collision')
    with pytest.raises(ValueError):store.publish(value,now=NOW)

def test_bounded_generation_rotation(tmp_path):
    store=ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64,max_generations=2)
    for sequence in range(1,8):store.publish(bundle(sequence),now=NOW)
    assert len(list((tmp_path/'manifests').iterdir()))==2
    assert store.read(now=NOW)['sequence']==7

def test_concurrent_writer_busy(tmp_path):
    tmp_path.joinpath('publish.lock').write_text('owned')
    with pytest.raises(ValueError,match='busy'):ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64).publish(bundle(),now=NOW)

def test_out_of_order_and_source_contract(tmp_path):
    from app.workspace.shadow_bundle import digest
    store=ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64);store.publish(bundle(),now=NOW)
    value=bundle(2);value['manifest']['generated_at']=(NOW-timedelta(minutes=1)).isoformat();value['manifest']['source_snapshot_time']=value['manifest']['generated_at'];value['blobs']['charts']['510300.SH']['as_of']=value['manifest']['generated_at'];value['manifest']['parts']['charts']=digest(value['blobs']['charts'])
    with pytest.raises(ValueError,match='order'):store.publish(value,now=NOW)
    value=bundle(2);value['manifest']['permission_scope']='ADMIN'
    with pytest.raises(ValueError,match='producer'):store.publish(value,now=NOW)
    value=bundle(2);future_bar={'date':'2026-10-12','open':10,'high':11,'low':9,'close':10,'source':'fixture','indicators':{}}
    chart=value['blobs']['charts']['510300.SH'];chart['bars']=[future_bar];chart['research_bars']=[future_bar.copy()];chart['source_as_of']='2026-10-12';value['manifest']['parts']['charts']=digest(value['blobs']['charts'])
    with pytest.raises(ValueError,match='future'):store.publish(value,now=NOW)

def test_private_cost_whitelist_rejected_even_with_valid_hash(tmp_path):
    from app.workspace.shadow_bundle import digest
    value=bundle();value['blobs']['board']['rows'][0]['avg_cost']=12;value['manifest']['parts']['board']=digest(value['blobs']['board'])
    with pytest.raises(ValueError,match='nonpublic'):ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64).publish(value,now=NOW)

@pytest.mark.parametrize('key,value',[('actionable',True),('research_only',False)])
def test_nested_unsafe_flag_valid_hash(tmp_path,key,value):
    from app.workspace.shadow_bundle import digest
    data=bundle();data['blobs']['board']['rows'][0][key]=value;data['manifest']['parts']['board']=digest(data['blobs']['board'])
    with pytest.raises(ValueError,match='safety'):ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64).publish(data,now=NOW)


def test_byte_budget_collects_only_unprotected_old_generations(tmp_path):
    from app.workspace.shadow_bundle import digest
    store=ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64,max_bytes=20000,max_generations=20)
    for sequence in range(1,8):
        value=bundle(sequence);value['blobs']['board']['rows'][0]['name']=str(sequence)+'x'*4500
        value['manifest']['parts']['board']=digest(value['blobs']['board'])
        store.publish(value,now=NOW)
    assert store.read(now=NOW)['sequence']==7
    import json
    previous=json.loads((tmp_path/'previous.json').read_bytes())['bundle_id']
    assert store.read(now=NOW,bundle_id=previous)['sequence']==6
    assert sum(p.stat().st_size for p in tmp_path.rglob('*') if p.is_file())<=20000
