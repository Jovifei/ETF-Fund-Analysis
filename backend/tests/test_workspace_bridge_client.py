"""The real outbound client exercised against the ASGI API; no model login."""
import importlib.util
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.core.config import get_settings
from app.db.session import get_engine, session_scope
from app.main import app
from app.services.auth_service import AuthService
from app.workspace.protocol import canonical_bytes

spec = importlib.util.spec_from_file_location('etf_agent_bridge', Path(__file__).resolve().parents[2] / 'bridge' / 'etf_agent_bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


@pytest.mark.parametrize('origin', ['http://example.com', 'https://user:password@example.com', 'https://example.com/path', 'file:///tmp/x', 'https://example.com?token=x'])
def test_bridge_origin_rejects_plaintext_remote_or_credentials(origin):
    with pytest.raises(bridge.BridgeError):
        bridge.base_url(origin)


def test_bridge_atomic_private_files(tmp_path):
    root = bridge.private_root(tmp_path / 'only-bridge')
    bridge.store_device(root, {'origin': 'http://127.0.0.1', 'device_token': 'fixture-not-a-production-token'})
    assert bridge.load_device(root)['origin'] == 'http://127.0.0.1'
    if os.name != 'nt':
        assert (root / 'device.secret').stat().st_mode & 0o077 == 0
        (root / 'device.secret').chmod(0o644)
        with pytest.raises(bridge.BridgeError, match='permissions'):
            bridge.load_device(root)
    target = tmp_path / 'outside'
    target.write_text('untouched')
    link = root / 'linked.json'
    try:
        link.symlink_to(target)
    except OSError as exc:
        if os.name == 'nt' and getattr(exc, 'winerror', None) == 1314:
            pytest.skip('Windows symlink privilege is unavailable')
        raise
    with pytest.raises(bridge.BridgeError):
        bridge.atomic_write(link, b'{}')
    assert target.read_text() == 'untouched'


def test_signed_client_real_user_round_trip_and_revocation(monkeypatch, tmp_path, bootstrapped):
    monkeypatch.setenv('WORKSPACE_BRIDGE_ENABLED', 'true')
    settings = get_settings().model_copy(update={'auth_enabled': True, 'auth_cookie_secure': False})
    name = 'workspace-' + uuid4().hex[:12]
    with session_scope() as db:
        AuthService().create_user(db, username=name, password='test-only-bridge-login-9248', role='member')
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app, base_url='http://127.0.0.1') as user, TestClient(app, base_url='http://127.0.0.1') as device_http:
            assert user.post('/api/auth/login', json={'identifier': name, 'password': 'test-only-bridge-login-9248'}).status_code == 200
            csrf = {'X-CSRF-Token': user.cookies['fund-csrf']}
            pair = user.post('/api/workspace/devices/pairing', json={'label': 'fixture-device'}, headers=csrf)
            assert pair.status_code == 200 and pair.json()['expires_at']
            device = device_http.post('/api/bridge/pair', json={'pairing_code': pair.json()['pairing_code']}).json()
            root = bridge.private_root(tmp_path / 'device')
            bridge.store_device(root, {**device, 'origin': 'http://127.0.0.1'})
            client = bridge.Bridge(root, device_http)
            created = user.post('/api/workspace/research-jobs', headers=csrf, json={'kind': 'daily', 'request_key': uuid4().hex})
            assert created.status_code == 202
            job_id = created.json()['job']['job_id']
            lease = client.claim()
            assert lease['job']['job_id'] == job_id
            assert client.claim()['lease_id'] == lease['lease_id']  # retry-safe with fresh nonce
            assert client.remote_status(job_id)['status'] == 'running'
            assert (root / 'jobs' / job_id / 'prompt.txt').is_file()
            assert not (root / 'jobs' / job_id / 'result.json').exists()
            output = {'schema_version': 'etf-research-result-v1', 'job_id': job_id, 'input_hash': lease['package']['input_hash'], 'producer':'manual','producer_version':'fixture','model':'none','summary':'客户端协议测试，不是真实模型结果','limitations':['没有调用模型']}
            file = root / 'jobs' / job_id / 'result.json'
            bridge.atomic_write(file, canonical_bytes(output))
            result = client.submit(job_id, file)
            assert result['review_status'] == 'pending' and result['actionable'] is False
            assert not (root / 'claim.json').exists()
            assert device_http.get('/api/workspace/holdings', headers={'Authorization': 'Bearer ' + device['device_token']}).status_code == 401
            with pytest.raises(bridge.BridgeError, match='scope'):
                client.post('/api/workspace/research-jobs/' + job_id + '/review/accepted', {})
            assert user.post('/api/workspace/research-jobs/' + job_id + '/review/accepted', json={'result_hash':result['result_hash'],'note':'测试人工审核'}, headers=csrf).status_code == 200
            assert user.delete('/api/workspace/devices/' + device['device_id'], headers=csrf).status_code == 200
            with pytest.raises(bridge.BridgeError, match='401'):
                client.post('/api/bridge/heartbeat', {'bridge_version':'test','mode':'manual'})
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_workspace_read_queries_remain_bounded_and_do_not_call_provider(bootstrapped):
    from app.workspace import read_model
    from app.models import Instrument
    with session_scope() as db:
        for i in range(120):
            db.add(Instrument(ts_code=f'56{i:04d}.SH', symbol=f'56{i:04d}', name='bounded-query-fixture', kind='ETF', enabled=False))
    statements = []
    def capture(*args):
        statements.append(args[2])
    engine = get_engine()
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        with TestClient(app) as client:
            for path in ['/api/search/instruments?q=bounded&limit=100', '/api/workspace/overview?limit=100', '/api/workspace/sectors']:
                statements.clear()
                result = client.get(path)
                assert result.status_code == 200
                assert len(statements) <= 10, (path, len(statements))
                assert not any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for s in statements)
    finally:
        event.remove(engine, 'before_cursor_execute', capture)


def test_reviewed_model_version_is_a_fail_closed_gate(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root = bridge.private_root(tmp_path / 'runner')
    folder = root / 'jobs' / ('a' * 32)
    folder.mkdir(parents=True)
    monkeypatch.setattr(bridge.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout='codex-cli 0.0.1'))
    with pytest.raises(bridge.BridgeError, match='unreviewed_codex_version'):
        bridge.codex_once(root, folder, 'codex', 'model-test-only')
    assert not (folder / 'result.json').exists()
