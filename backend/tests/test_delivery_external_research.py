"""No model called: actual Vibe-shaped files -> safe packet -> private candidate."""
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.db.session import session_scope
from app.workspace.models import WorkspaceResearchJob


def packet():
    bodies = {'manifest.json': json.dumps({'run_id':'unit-research', 'status':'complete', 'symbol':'512480'}),
              'evidence.json': json.dumps({'evidence':[{'id':'upstream-1', 'source':'fixture', 'value':12}]}),
              'report.md':'# Test report\n<script>untrusted()</script>\nThis is a fixture, not a model conclusion.\n'}
    return {'schema_version':'etf-external-research-v1', 'kind':'etf', 'ts_code':'512480.SH',
            'producer':'vibe', 'producer_version':'fixture-not-installed-upstream', 'run_id':'unit-'+uuid4().hex,
            'model':'fixture-no-model', 'upstream_status':'complete',
            'source_as_of':(datetime.now(UTC)-timedelta(hours=1)).isoformat(),
            'artifacts':[{'name':k, 'sha256':hashlib.sha256(v.encode()).hexdigest(), 'text':v} for k,v in bodies.items()]}


def test_external_preview_is_read_only_and_import_requires_consent(bootstrapped):
    from app.workspace.protocol import content_hash
    payload=packet()
    with TestClient(app) as client:
        with session_scope() as db: before=len(db.scalars(select(WorkspaceResearchJob)).all())
        preview=client.post('/api/workspace/external-research/preview', json=payload)
        assert preview.status_code==200
        from app.workspace.external_research import ExternalPacket
        assert preview.json()['packet_hash']==ExternalPacket.model_validate(payload).digest()
        with session_scope() as db: assert len(db.scalars(select(WorkspaceResearchJob)).all())==before
        denied=client.post('/api/workspace/external-research/import', json={'packet':payload,'packet_hash':preview.json()['packet_hash'],'confirm_public_data':False})
        assert denied.status_code==422
        body={'packet':payload,'packet_hash':preview.json()['packet_hash'],'confirm_public_data':True}
        imported=client.post('/api/workspace/external-research/import', json=body)
        assert imported.status_code==201, imported.text
        job=imported.json()['job']
        assert job['review_status']=='pending' and not job['actionable']
        assert job['origin']=='external_archive' and job['upstream_status']=='complete'
        assert job['quality']=='external_unverified'
        again=client.post('/api/workspace/external-research/import',json=body).json()
        assert again['created'] is False and again['job']['job_id']==job['job_id']
        detail=client.get('/api/workspace/research-jobs/'+job['job_id']).json()
        assert '<script>' in detail['result']['report_markdown']  # stored text, never executable HTML
        assert detail['result']['facts']==[]  # upstream assertions not certified facts
        review=client.post('/api/workspace/research-jobs/'+job['job_id']+'/review/accepted',json={'result_hash':job['result_hash'],'note':'fixture review'})
        assert review.status_code==200 and review.json()['quality']=='external_unverified'
        assert review.json()['actionable'] is False


@pytest.mark.parametrize('fault', ['hash','path','duplicates','future','credential','failed','json-duplicate','oversize'])
def test_bad_external_packet_rejected_before_storage(fault):
    payload=packet()
    if fault=='hash': payload['artifacts'][0]['sha256']='0'*64
    elif fault=='path': payload['artifacts'][0]['name']='../../auth.json'
    elif fault=='duplicates': payload['artifacts'].append(payload['artifacts'][0])
    elif fault=='future': payload['source_as_of']=(datetime.now(UTC)+timedelta(days=2)).isoformat()
    elif fault=='credential': payload['artifacts'][0]['text']='Bearer '+'x'*40
    elif fault=='failed': payload['upstream_status']='failed'
    elif fault=='json-duplicate':
        a=payload['artifacts'][0]; a['text']='{"status":1,"status":2}';a['sha256']=hashlib.sha256(a['text'].encode()).hexdigest()
    elif fault=='oversize': payload['artifacts'][0]['text']='x'*250001
    with TestClient(app) as client:
        assert client.post('/api/workspace/external-research/preview', json=payload).status_code==422


def test_file_adapter_refuses_symlinks_and_preserves_original_hash(tmp_path):
    from app.workspace.external_research import packet_from_directory
    (tmp_path/'manifest.json').write_text('{"status":"complete"}')
    (tmp_path/'report.md').write_bytes(b'  # original report\n')
    p=packet_from_directory(tmp_path,kind='daily',ts_code=None,source_as_of=datetime.now(UTC),model='fixture',run_id='test',producer_version='fixture',upstream_status='complete')
    assert p.artifacts[1].text=='  # original report\n'
    target=tmp_path/'hidden';target.write_text('{}')
    try:
        (tmp_path/'evidence.json').symlink_to(target)
    except OSError as exc:
        if getattr(exc, 'winerror', None) == 1314:
            pytest.skip('Windows symlink privilege is unavailable')
        raise
    with pytest.raises(ValueError,match='symbolic'):
        packet_from_directory(tmp_path,kind='daily',ts_code=None,source_as_of=datetime.now(UTC),model='fixture',run_id='test',producer_version='fixture',upstream_status='complete')


def test_style_registry_is_versioned_reference_only():
    with TestClient(app) as client:
        payload=client.get('/api/workspace/research-styles').json()
        assert not payload['production_enabled'] and not payload['actionable']
        assert len(payload['content_hash'])==64
        assert all(t['references'] and t['qualification']=='not_qualified' for t in payload['templates'])


def test_external_archive_is_isolated_by_database_user(bootstrapped):
    from app.core.config import get_settings
    from app.services.auth_service import AuthService
    settings=get_settings().model_copy(update={'auth_enabled':True,'auth_cookie_secure':False})
    users=['external-'+uuid4().hex[:10] for _ in range(2)]
    with session_scope() as db:
        for name in users: AuthService().create_user(db,username=name,password='test-only-bridge-login-9248',role='member')
    app.dependency_overrides[get_settings]=lambda:settings
    try:
        with TestClient(app) as a,TestClient(app) as b:
            for client,name in zip((a,b),users):
                assert client.post('/api/auth/login',json={'identifier':name,'password':'test-only-bridge-login-9248'}).status_code==200
            csrf={'X-CSRF-Token':a.cookies['fund-csrf']};p=packet()
            view=a.post('/api/workspace/external-research/preview',json=p,headers=csrf).json()
            body={'packet':p,'packet_hash':view['packet_hash'],'confirm_public_data':True}
            assert a.post('/api/workspace/external-research/import',json=body).status_code==403
            own=a.post('/api/workspace/external-research/import',json=body,headers=csrf).json()['job']
            assert b.get('/api/workspace/research-jobs/'+own['job_id']).status_code==404
            assert b.get('/api/workspace/research-jobs/'+own['job_id']+'/export').status_code==404
            assert b.post('/api/workspace/research-jobs/'+own['job_id']+'/review/accepted',json={'result_hash':own['result_hash'],'note':'attempt'},headers={'X-CSRF-Token':b.cookies['fund-csrf']}).status_code==404
    finally: app.dependency_overrides.pop(get_settings,None)
