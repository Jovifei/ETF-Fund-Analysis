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
    # Valid signature is authenticated before expiry/payload validation; nonce is durable even on rejected payload.
    assert client.post('/api/shadow/sync',content=body,headers=headers).status_code==409
    assert client.post('/api/shadow/sync',content=body,headers=headers).status_code==401
    settings.shadow_sync_active_key_id='key-2'
    old={**signed_headers(body,'key-1','s'*32),'Authorization':'Bearer '+'x'*32}
    assert client.post('/api/shadow/sync',content=body,headers=old).status_code==401
    assert client.post('/api/shadow/sync',content=body,headers={'Authorization':'Bearer '+'x'*32}).status_code==401
