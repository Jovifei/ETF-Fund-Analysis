from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app


def test_import_revision_is_explicit_idempotent_and_preserves_old_audit(bootstrapped):
    with TestClient(app) as client:
        payload={'candidates':[{'row_index':1,'ts_code':'512480.SH','shares':'123.78','cost_price':'1.232','selected':True}]}
        original=client.post('/api/workspace/imports/preview-rows',json=payload).json()
        client.post(f"/api/workspace/imports/{original['batch_id']}/cancel")
        assert client.post('/api/workspace/imports/preview-rows',json=payload).json()['batch_id']==original['batch_id']
        path=f"/api/workspace/imports/{original['batch_id']}/revision"
        key={'request_key':uuid4().hex}
        revised=client.post(path,json=key)
        assert revised.status_code==201
        row=revised.json()
        assert row['batch_id'] != original['batch_id'] and row['status']=='preview'
        assert client.post(path,json=key).json()['batch_id']==row['batch_id']
        assert client.get(f"/api/workspace/imports/{original['batch_id']}").json()['status']=='cancelled'
        client.post(f"/api/workspace/imports/{row['batch_id']}/cancel")
