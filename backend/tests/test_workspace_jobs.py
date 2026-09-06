import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.main import app
from app.workspace import jobs
from app.workspace.models import WorkspaceResearchJob
from app.workspace.protocol import ResearchRequest, ResearchResult, content_hash


def result_for(row):
    return ResearchResult(
        schema_version='etf-research-result-v1', job_id=row.job_id,
        input_hash=row.input_hash, producer='manual', producer_version='test-v1',
        model='test-only-no-model', summary='测试数据，不是投资结论',
        limitations=['仅用于自动化测试'], report_markdown='<script>alert(1)</script>',
    )


def test_research_idempotency_and_human_review(bootstrapped):
    request = ResearchRequest(kind='daily', request_key=uuid4().hex)
    with session_scope() as db:
        row, created = jobs.enqueue(db, get_settings(), request, None)
        assert created and row.quality == 'mock'
        assert content_hash(row.bundle_json) == row.input_hash
        again, created = jobs.enqueue(db, get_settings(), request, None)
        assert again.job_id == row.job_id and not created
        output = result_for(row)
        jobs.accept_result(db, row, output)
        assert row.status == 'completed' and row.review_status == 'pending'
        jobs.accept_result(db, row, output)
        jobs.review(db, row, row.result_hash, 'accepted', '人工测试审核')
        assert row.review_status == 'accepted' and row.quality == 'mock'
        assert jobs.job_view(row)['actionable'] is False
        with pytest.raises(jobs.WorkspaceError, match='already_final'):
            jobs.review(db, row, row.result_hash, 'rejected', '')


def test_research_rejects_hash_unknown_evidence_and_wrong_owner(bootstrapped):
    with session_scope() as db:
        row, _ = jobs.enqueue(db, get_settings(), ResearchRequest(kind='daily', request_key=uuid4().hex), None)
        output = result_for(row)
        with pytest.raises(jobs.WorkspaceError, match='input_mismatch'):
            jobs.accept_result(db, row, output.model_copy(update={'input_hash': 'a' * 64}))
        with pytest.raises(jobs.WorkspaceError, match='unknown_evidence'):
            jobs.accept_result(db, row, output.model_copy(update={'evidence_ids': ['invented:source']}))
        with pytest.raises(jobs.WorkspaceError, match='not_found'):
            jobs.owned_job(db, row.job_id, 'user:999999')
        row.status = 'cancelled'
        db.flush()
        with pytest.raises(jobs.WorkspaceError, match='queued'):
            jobs.accept_result(db, row, output)


def test_workspace_job_http_does_not_execute_a_model(bootstrapped):
    with TestClient(app) as client:
        response = client.post('/api/workspace/research-jobs', json={'kind': 'daily', 'request_key': uuid4().hex})
        assert response.status_code == 202
        assert response.json()['model_called'] is False
        job_id = response.json()['job']['job_id']
        exported = client.get(f'/api/workspace/research-jobs/{job_id}/export')
        assert exported.status_code == 200
        assert content_hash(exported.json()['bundle']) == exported.json()['input_hash']
        assert client.post(f'/api/workspace/research-jobs/{job_id}/cancel').status_code == 200
        assert client.get('/api/workspace/status').status_code == 200


def signed(token, path, data):
    raw = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
    timestamp = str(int(time.time()))
    message = f'POST\n{path}\n{timestamp}\n{hashlib.sha256(raw).hexdigest()}'.encode()
    return raw, {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
                 'X-Bridge-Time': timestamp, 'X-Bridge-Signature': hmac.new(token.encode(), message, hashlib.sha256).hexdigest()}


def test_bridge_pair_scope_signature_and_revocation(monkeypatch, bootstrapped):
    monkeypatch.setenv('WORKSPACE_BRIDGE_ENABLED', 'true')
    with TestClient(app) as client:
        pair = client.post('/api/workspace/devices/pairing', json={'label': 'test-device'})
        assert pair.status_code == 200
        code = pair.json()['pairing_code']
        joined = client.post('/api/bridge/pair', json={'pairing_code': code})
        assert joined.status_code == 200
        token, device_id = joined.json()['device_token'], joined.json()['device_id']
        assert client.post('/api/bridge/pair', json={'pairing_code': code}).status_code == 401
        data = {'bridge_version': 'test-v1', 'login_state': 'unknown', 'mode': 'manual'}
        raw, headers = signed(token, '/api/bridge/heartbeat', data)
        assert client.post('/api/bridge/heartbeat', content=raw, headers=headers).status_code == 200
        assert client.post('/api/bridge/heartbeat', content=raw + b' ', headers=headers).status_code == 401
        listed = client.get('/api/workspace/devices').json()
        assert token not in json.dumps(listed) and code not in json.dumps(listed)
        assert client.delete(f'/api/workspace/devices/{device_id}').status_code == 200
        assert client.post('/api/bridge/heartbeat', content=raw, headers=headers).status_code == 401
