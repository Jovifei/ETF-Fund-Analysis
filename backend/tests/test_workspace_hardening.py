"""Regression contracts for the recovered workspace; no real account/model data."""
import hashlib
import hmac
import json
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.workspace.protocol import ResearchRequest


def sign(token, path, payload, nonce=None):
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    timestamp, nonce = str(int(time.time())), nonce or uuid4().hex
    message = f'POST\n{path}\n{timestamp}\n{nonce}\n{hashlib.sha256(raw).hexdigest()}'.encode()
    return raw, {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
                 'X-Bridge-Time': timestamp, 'X-Bridge-Nonce': nonce,
                 'X-Bridge-Signature': hmac.new(token.encode(), message, hashlib.sha256).hexdigest()}


def test_bridge_replay_is_rejected(monkeypatch, bootstrapped):
    monkeypatch.setenv('WORKSPACE_BRIDGE_ENABLED', 'true')
    with TestClient(app) as client:
        pair = client.post('/api/workspace/devices/pairing', json={'label': 'replay-test'}).json()
        joined = client.post('/api/bridge/pair', json={'pairing_code': pair['pairing_code']}).json()
        raw, headers = sign(joined['device_token'], '/api/bridge/heartbeat', {'bridge_version': 'test', 'mode': 'manual'})
        assert client.post('/api/bridge/heartbeat', content=raw, headers=headers).status_code == 200
        assert client.post('/api/bridge/heartbeat', content=raw, headers=headers).status_code == 409
        assert client.delete('/api/workspace/devices/' + joined['device_id']).status_code == 200


def test_data_read_does_not_expose_private_reports(bootstrapped):
    with TestClient(app) as client:
        response = client.get('/api/workspace/portfolio-risk')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'private, no-store'
        assert response.json()['actionable'] is False


def test_daily_job_does_not_accept_irrelevant_code():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ResearchRequest(kind='daily', ts_code='510300.SH')


def test_research_retry_is_explicit_preserves_input(bootstrapped):
    with TestClient(app) as client:
        created = client.post('/api/workspace/research-jobs', json={'kind': 'daily', 'request_key': uuid4().hex}).json()['job']
        job_id = created['job_id']
        client.post('/api/workspace/research-jobs/' + job_id + '/cancel')
        retry = client.post('/api/workspace/research-jobs/' + job_id + '/retry')
        assert retry.status_code == 200
        assert retry.json()['input_hash'] == created['input_hash']
        assert retry.json()['status'] == 'queued'
        client.post('/api/workspace/research-jobs/' + job_id + '/cancel')


@pytest.mark.parametrize('horizon', [1, 3, 5, 10])
def test_horizon_http_query_casts_string_before_validation(horizon, bootstrapped):
    with TestClient(app) as client:
        response = client.get('/api/workspace/overview', params={'horizon': horizon, 'limit': 5})
        assert response.status_code == 200
        assert len(response.json()['rows']) <= 5
        assert client.get('/api/workspace/overview?horizon=20').status_code == 422
