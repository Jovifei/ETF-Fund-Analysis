from datetime import timedelta
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from app.workspace import shadow_api
from app.core.security import require_current_user
from test_shadow_bundle import NOW,bundle

def test_write_only_auth_and_same_bundle(tmp_path,monkeypatch):
    settings=SimpleNamespace(shadow_sync_enabled=True,shadow_sync_root=str(tmp_path),shadow_sync_code_sha='a'*40,shadow_sync_config_hash='b'*64,shadow_sync_producer_token=SecretStr('x'*32),shadow_sync_active_key_id='test-1',shadow_sync_signing_secret=SecretStr('s'*32),shadow_sync_max_bytes=33554432,shadow_sync_max_generations=20,shadow_sync_max_request_bytes=8192)
    monkeypatch.setattr(shadow_api,'get_settings',lambda:settings)
    from app.workspace.shadow_bundle import ShadowStore
    original_publish=ShadowStore.publish;original_read=ShadowStore.read
    monkeypatch.setattr(ShadowStore,'publish',lambda self,value:original_publish(self,value,now=NOW))
    monkeypatch.setattr(ShadowStore,'read',lambda self,**kw:original_read(self,now=NOW,**kw))
    app=FastAPI();app.include_router(shadow_api.router);client=TestClient(app)
    assert client.post('/api/shadow/sync',json=bundle()).status_code==401
    from app.workspace.shadow_auth import signed_headers
    from app.workspace.shadow_bundle import canonical
    body=canonical(bundle())
    def headers():return {**signed_headers(body,'test-1','s'*32),'Authorization':'Bearer '+'x'*32}
    response=client.post('/api/shadow/sync',content=body,headers=headers())
    assert response.status_code==200
    assert client.get('/api/shadow/bundle',headers={'Authorization':'Bearer '+'x'*32}).status_code in (401,403)
    app.dependency_overrides[require_current_user]=lambda:object()
    result=client.get('/api/shadow/bundle').json()
    assert result['bundle_id']==response.json()['bundle_id']
    assert set(result['charts'])=={r['ts_code'] for r in result['board']['rows']}
    assert result['market']=={'references':[]}
    assert client.post('/api/shadow/sync',content=body,headers=headers()).status_code==409
    settings.shadow_sync_enabled=False
    assert client.get('/api/shadow/bundle').status_code==404

def test_http_signature_tamper_replay_and_rotation(tmp_path,monkeypatch):
    from app.workspace.shadow_bundle import canonical
    from app.workspace.shadow_auth import signed_headers
    settings=SimpleNamespace(shadow_sync_enabled=True,shadow_sync_root=str(tmp_path),shadow_sync_code_sha='a'*40,shadow_sync_config_hash='b'*64,shadow_sync_producer_token=SecretStr('x'*32),shadow_sync_active_key_id='key-1',shadow_sync_signing_secret=SecretStr('s'*32),shadow_sync_max_bytes=33554432,shadow_sync_max_generations=20,shadow_sync_max_request_bytes=8192)
    monkeypatch.setattr(shadow_api,'get_settings',lambda:settings)
    app=FastAPI();app.include_router(shadow_api.router);client=TestClient(app)
    body=canonical({'invalid':True});headers={**signed_headers(body,'key-1','s'*32),'Authorization':'Bearer '+'x'*32}
    assert client.post('/api/shadow/sync',content=body+b' ',headers=headers).status_code==401
    assert client.post('/api/shadow/sync',content=body,headers=headers).status_code==409
    assert client.post('/api/shadow/sync',content=body,headers=headers).status_code==401
    settings.shadow_sync_active_key_id='key-2'
    old={**signed_headers(body,'key-1','s'*32),'Authorization':'Bearer '+'x'*32}
    assert client.post('/api/shadow/sync',content=body,headers=old).status_code==401
    assert client.post('/api/shadow/sync',content=body,headers={'Authorization':'Bearer '+'x'*32}).status_code==401


def test_sync_and_preview_local_display_v2(tmp_path, monkeypatch):
    from app.workspace.shadow_bundle import canonical
    from app.workspace.shadow_auth import signed_headers
    from app.workspace.local_display_contract import CONTRACT_VERSION, compute_parts_hashes

    v2_root = tmp_path / "v2_store"
    settings = SimpleNamespace(
        shadow_sync_enabled=True,
        shadow_sync_root=str(tmp_path),
        shadow_sync_code_sha='a'*40,
        shadow_sync_config_hash='b'*64,
        shadow_sync_producer_token=SecretStr('x'*32),
        shadow_sync_active_key_id='test-1',
        shadow_sync_signing_secret=SecretStr('s'*32),
        shadow_sync_max_bytes=33554432,
        shadow_sync_max_generations=20,
        shadow_sync_max_request_bytes=65536,
        workspace_research_source="local_bundle",
        local_display_v2_store_root=str(v2_root),
    )
    monkeypatch.setattr(shadow_api, 'get_settings', lambda: settings)

    parts = {
        "overview": {"rows": [{"ts_code": "510300.SH", "price": 4.12}]},
        "details": {"510300.SH": {"quote": {"price": 4.12}}},
        "charts": {"510300.SH": {"bars": []}},
        "sectors": {"sectors": []},
    }
    v2_bundle = {
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
            "parts_hashes": compute_parts_hashes(parts),
        },
        "parts": parts,
    }
    body = canonical(v2_bundle)
    headers = {**signed_headers(body, 'test-1', 's'*32), 'Authorization': 'Bearer ' + 'x'*32}

    app = FastAPI()
    app.include_router(shadow_api.router)
    client = TestClient(app)

    # Ingestion via /api/shadow/sync
    res = client.post('/api/shadow/sync', content=body, headers=headers)
    assert res.status_code == 200
    assert res.json()['status'] == 'accepted'

    # Preview via /api/shadow/bundle
    app.dependency_overrides[require_current_user] = lambda: object()
    preview = client.get('/api/shadow/bundle')
    assert preview.status_code == 200
    assert preview.json()['manifest']['contract_version'] == CONTRACT_VERSION

