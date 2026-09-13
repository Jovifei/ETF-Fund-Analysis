from datetime import datetime
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import session_scope
from app.models import TaskRun
from app.core.config import get_settings


def test_task_status_exact_identity_no_payload_leak():
    code=uuid4().hex
    with session_scope() as db:
        db.add(TaskRun(run_id=code,task_name='refresh_decision_board',status='failed',
            started_at=datetime.now(get_settings().timezone),result_json={'private':'must-not-return'}))
    with TestClient(app) as client:
        response=client.get('/api/tasks/runs/'+code)
        assert response.status_code==200
        assert response.headers['cache-control']=='private, no-store'
        assert response.json()['run_id']==code and response.json()['status']=='failed'
        assert 'private' not in response.text
        assert client.get('/api/tasks/runs/'+uuid4().hex).status_code==404
    assert 'ETFDecisionRefresh.reconcile' in (__import__('pathlib').Path(__file__).resolve().parents[1]/'app/static/app.js').read_text()
