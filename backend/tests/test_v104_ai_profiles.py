import json
from datetime import UTC,datetime,timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.core.config import get_settings
from app.core.security import require_current_user
from app.db.session import session_scope
from app.services.auth_service import AuthService
from app.workspace import ai_profiles as svc,ai_secrets,memberships
from app.workspace.jobs import WorkspaceError,content_hash,owner_scope
from app.workspace.models import WorkspaceResearchJob,WorkspaceDataJob,WorkspacePreference

@pytest.fixture
def ai_env(monkeypatch,tmp_path):
    monkeypatch.setenv('WORKSPACE_AI_API_ENABLED','true')
    monkeypatch.setenv('WORKSPACE_AI_KEY_FILE',str(tmp_path/'private'/'key'))
    ai_secrets.create_master(tmp_path/'private'/'key')


def user(db,role='member'):
    return AuthService().create_user(db,username='ai-'+uuid4().hex[:10],password='test-only-passphrase',role=role)


def data(**extra):
    return svc.ProfileInput(name='研究模型',base_url='https://api.openai.com/v1',model='model-test',api_key='fixture-key-only',**extra)


def test_profile_encrypted_private_revision_no_auto_model_calls(db_session,ai_env,monkeypatch):
    db=db_session;u=user(db);other=user(db)
    monkeypatch.setattr(svc,'completion',lambda *a,**k:pytest.fail('saving must not call model'))
    r=svc.save(db,u.id,data());pid=r['id']
    serialized=json.dumps(svc.list_profiles(db,u.id));assert 'fixture-key-only' not in serialized and 'ciphertext' not in serialized
    stored=svc.profile(db,u.id,pid).settings_json
    assert 'fixture-key-only' not in json.dumps(stored)
    assert ai_secrets.decrypt(stored['ciphertext'],str(u.id)+':'+pid)=='fixture-key-only'
    with pytest.raises(WorkspaceError):ai_secrets.decrypt(stored['ciphertext'],str(other.id)+':'+pid)
    with pytest.raises(WorkspaceError,match='not_found'):svc.profile(db,other.id,pid)
    with pytest.raises(WorkspaceError,match='revision_changed'):svc.save(db,u.id,data(expected_revision=99),pid)
    svc.set_default(db,u.id,pid);assert svc.list_profiles(db,u.id)['default_id']==pid
    svc.remove(db,u.id,pid);assert not svc.list_profiles(db,u.id)['items'];db.rollback()


def test_endpoint_rejects_private_and_nonwhitelisted_ai_urls(monkeypatch):
    for url in ('http://api.openai.com/v1','https://localhost/v1','https://127.0.0.1/v1','https://api.openai.com@evil.invalid/v1','https://api.openai.com/v1?x=1','https://api.openai.com/v1/chat/completions'):
        with pytest.raises((WorkspaceError,ValueError)):svc.endpoint(url)
    monkeypatch.setattr(svc.socket,'getaddrinfo',lambda *a,**k:[(None,None,None,None,('127.0.0.1',443))])
    with pytest.raises(WorkspaceError,match='private_endpoint'):svc.endpoint('https://api.openai.com/v1',resolve=True)


def test_validation_never_echoes_api_key_and_cost_requires_consent(db_session,ai_env):
    u=user(db_session);db_session.commit();app.dependency_overrides[require_current_user]=lambda:u
    try:
        with TestClient(app) as client:
            key='do-not-echo-'+uuid4().hex
            r=client.post('/api/workspace/ai/profiles',json={'name':'x','base_url':'wrong','model':'a','api_key':key,'extra':key})
            assert r.status_code==422 and key not in r.text and 'input' not in r.text
            r=client.post('/api/workspace/ai/profiles/'+('a'*32)+'/test',json={'confirm_cost':False,'request_key':uuid4().hex})
            assert r.status_code==422 and 'cost_consent' in r.text
    finally:app.dependency_overrides.pop(require_current_user,None);db_session.rollback()


def make_research(db,u):
    bundle={'evidence':[],'quality':'incomplete','source_as_of':None}
    job=WorkspaceResearchJob(job_id=uuid4().hex,user_id=u.id,owner_scope=owner_scope(u.id),idempotency_key=uuid4().hex,
        kind='daily',input_hash=content_hash(bundle),bundle_json=bundle,expires_at=datetime.now(UTC)+timedelta(hours=1))
    db.add(job);db.flush();return job


def test_bounded_api_task_accepts_only_hash_bound_candidate(ai_env,monkeypatch):
    with session_scope() as db:
        u=user(db);uid=u.id;r=svc.save(db,uid,data());job=make_research(db,u);rid=job.job_id;ihash=job.input_hash
        ticket,created=svc.enqueue(db,uid,r['id'],research_id=rid,request_key='k'*20);tid=ticket.job_id
        again,fresh=svc.enqueue(db,uid,r['id'],research_id=rid,request_key='k'*20);assert not fresh and again.job_id==tid
        db.get(WorkspaceDataJob,tid).status='running'
    def fake(value,key,messages,**kwargs):
        assert key=='fixture-key-only' and 'evidence_bundle' in messages[-1]['content']
        return json.dumps({'schema_version':'etf-research-result-v1','job_id':rid,'input_hash':ihash,'producer':'api',
            'producer_version':svc.VERSION,'model':'model-test','summary':'缺少数据，暂不作判断','limitations':['仅固定证据；未校准']}),{'prompt_tokens':10,'completion_tokens':20}
    monkeypatch.setattr(svc,'completion',fake)
    assert svc.execute_ticket(tid)==0
    with session_scope() as db:
        result=db.get(WorkspaceResearchJob,rid);assert result.status=='completed' and result.review_status=='pending'
        assert result.result_json['producer']=='api'
        assert db.get(WorkspaceDataJob,tid).status=='succeeded'
        # Keys and provider text never appear in task transport/result metadata.
        assert 'fixture-key-only' not in json.dumps(db.get(WorkspaceDataJob,tid).request_json)


def test_cancelled_or_disabled_api_task_never_calls_model(ai_env,monkeypatch):
    with session_scope() as db:
        u=user(db);r=svc.save(db,u.id,data());j=make_research(db,u);rid=j.job_id
        ticket,_=svc.enqueue(db,u.id,r['id'],research_id=rid,request_key=uuid4().hex);tid=ticket.job_id
        ticket.status='running';j.status='cancelled'
    monkeypatch.setattr(svc,'completion',lambda *a,**kw:pytest.fail('cancelled must not call provider'))
    assert svc.execute_ticket(tid)==1
    with session_scope() as db:assert db.get(WorkspaceResearchJob,rid).status=='cancelled'


def test_revised_profile_failure_releases_reserved_research(ai_env,monkeypatch):
    with session_scope() as db:
        u=user(db);r=svc.save(db,u.id,data());j=make_research(db,u);rid=j.job_id
        t,_=svc.enqueue(db,u.id,r['id'],research_id=rid,request_key=uuid4().hex);tid=t.job_id;t.status='running'
        svc.save(db,u.id,data(expected_revision=1),r['id'])
    monkeypatch.setattr(svc,'completion',lambda *a,**kw:pytest.fail('profile changed'))
    assert svc.execute_ticket(tid)==1
    with session_scope() as db:
        assert db.get(WorkspaceResearchJob,rid).status=='failed'
        assert db.get(WorkspaceDataJob,tid).failure_reason=='ai_profile_revision_changed'


def test_profile_secret_file_permissions(db_session,ai_env,monkeypatch):
    import os
    if os.name=='nt':pytest.skip('Unix file mode only')
    ai_secrets.key_path().chmod(0o644)
    with pytest.raises(WorkspaceError,match='permissions'):svc.save(db_session,user(db_session).id,data())
    db_session.rollback()


def test_membership_change_protected_audited_and_reversible(db_session):
    db=db_session;a=user(db,'admin');m=user(db);before=m.password_hash
    memberships.change(db,a,m.id,memberships.Change(action='plan',plan='plus',confirm_username=m.username))
    assert memberships.plan_for(db,m.id)=='plus'
    memberships.set_policy(db,a,memberships.Policy(enabled=True,plus_features=['api_research']))
    memberships.check_feature(db,m,'api_research')
    memberships.change(db,a,m.id,memberships.Change(action='plan',plan='free',confirm_username=m.username))
    with pytest.raises(WorkspaceError,match='plus_feature'):memberships.check_feature(db,m,'api_research')
    memberships.change(db,a,m.id,memberships.Change(action='remove',confirm_username=m.username))
    assert m.status=='disabled' and m.password_hash==before and memberships.meta(db,m.id)['removed']
    memberships.change(db,a,m.id,memberships.Change(action='restore',confirm_username=m.username))
    assert m.status=='active' and not memberships.meta(db,m.id)['removed']
    with pytest.raises(WorkspaceError,match='own_access'):memberships.change(db,a,a.id,memberships.Change(action='remove',confirm_username=a.username))
    assert db.scalar(select(WorkspacePreference).where(WorkspacePreference.owner_scope.startswith('member:audit:'))) is not None
    db.rollback()


def test_completion_protocol_has_budget_no_tools_and_no_retry(monkeypatch):
    import httpx
    seen=[]
    original=httpx.Client
    def handle(request):
        body=json.loads(request.content);seen.append(body)
        return httpx.Response(200,json={'choices':[{'message':{'content':'OK'}}],'usage':{'prompt_tokens':1,'completion_tokens':1}})
    monkeypatch.setattr(svc.socket,'getaddrinfo',lambda *a,**kw:[(None,None,None,None,('8.8.8.8',443))])
    monkeypatch.setattr(svc.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    value={'base_url':'https://api.openai.com/v1','model':'account-selected-model','max_tokens':1800}
    answer,_=svc.completion(value,'fixture-credential',[{'role':'user','content':'test'}],test=True)
    assert answer=='OK' and seen[0]['max_completion_tokens']==256 and 'max_tokens' not in seen[0]
    assert 'tools' not in seen[0] and len(seen)==1
    value['base_url']='https://api.deepseek.com/v1'
    svc.completion(value,'fixture-credential',[{'role':'user','content':'JSON'}])
    assert seen[1]['max_tokens']==1800 and seen[1]['response_format']=={'type':'json_object'}


def test_api_budget_counts_queued_and_failed_calls(ai_env):
    with session_scope() as db:
        u=user(db);p=svc.save(db,u.id,data())
        for _ in range(5):
            row,_=svc.enqueue(db,u.id,p['id'],request_key=uuid4().hex);row.status='failed';db.flush()
        with pytest.raises(WorkspaceError,match='daily_budget'):svc.enqueue(db,u.id,p['id'],request_key=uuid4().hex)
