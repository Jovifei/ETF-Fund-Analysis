"""No real model calls: exercise child-only login, ACL policy and retry safety."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_workspace_bridge_client import bridge


def test_doctor_reports_isolation_without_inspecting_login(tmp_path) -> None:
    root = bridge.private_root(tmp_path / "isolated")
    status = bridge.doctor_status(root)
    assert status["reviewed_codex_version"] == bridge.REVIEWED_CODEX
    assert status["model_login"] == "not_inspected"
    assert status["auto_recharge"] is False
    assert status["writes_holdings"] is False
    assert status["computes_official_actions"] is False
    assert status["requires_approve_execution"] is True
    assert status["max_jobs_per_work"] == 1
    assert status["runner_home_present"] is False
    assert not (root / "runner-home" / ".codex" / "auth.json").exists()


def test_login_is_a_child_only_environment_and_same_private_runner(tmp_path, monkeypatch):
    root=bridge.private_root(tmp_path/'isolated')
    before=dict(os.environ); calls=[]; native_run=bridge.subprocess.run
    def run(args, **kwargs):
        if str(args[0]).lower().endswith('powershell.exe'):
            return native_run(args,**kwargs)
        calls.append((args,kwargs))
        return SimpleNamespace(returncode=0,stdout='codex-cli '+bridge.REVIEWED_CODEX)
    monkeypatch.setattr(bridge.subprocess,'run',run)
    bridge.login_codex(root,'codex',timeout=20)
    assert dict(os.environ)==before
    args,kwargs=calls[-1]
    assert args==['codex','login']
    assert Path(kwargs['env']['HOME'])==root/'runner-home'
    assert Path(kwargs['env']['CODEX_HOME'])==root/'runner-home'/'.codex'
    assert bridge.private_root(root/'runner-home')==root/'runner-home'
    assert not any('KEY' in key or 'TOKEN' in key for key in kwargs['env'])
    ui=Path(__file__).resolve().parents[2]/'frontend/src/components/AISetupGuide.vue'
    text=ui.read_text(encoding="utf-8")
    assert '$env:HOME =' not in text and '$env:USERPROFILE =' not in text
    assert ' login' in text and '--approve-execution' in text


def test_windows_acl_rejects_broad_access_and_missing_protection():
    from app.workspace.bridge_runtime import acl_is_private
    me='S-1-5-21-1-2-3-1000'
    good={'owner':me,'protected':True,'rules':[{'sid':me,'allow':True,'rights':2032127}]}
    assert acl_is_private(good,me)
    assert not acl_is_private({**good,'protected':False},me)
    assert not acl_is_private({**good,'rules':good['rules']+[{'sid':'S-1-1-0','allow':True,'rights':1}]},me)
    assert not acl_is_private({**good,'owner':'S-1-5-21-OTHER'},me)
    assert not acl_is_private({**good,'rules':[]},me)


def setup_client(tmp_path, monkeypatch):
    root=bridge.private_root(tmp_path/'device')
    bridge.store_device(root,{'origin':'http://127.0.0.1','device_token':'fixture-only'})
    client=bridge.Bridge(root)
    job_id='a'*32; folder=bridge.private_root(root/'jobs'/job_id)
    bundle={'evidence':[]}; hashed=bridge.content_hash(bundle)
    lease={'job':{'job_id':job_id},'lease_id':'b'*32,'package':{'job_id':job_id,'input_hash':hashed,'bundle':bundle}}
    bridge.atomic_write(folder/'lease.json',bridge.canonical_bytes(lease))
    bridge.atomic_write(folder/'evidence.json',bridge.canonical_bytes(lease['package']))
    monkeypatch.setattr(client,'claim',lambda:lease)
    monkeypatch.setattr(client,'remote_status',lambda j:{'status':'running'})
    failures=[];monkeypatch.setattr(client,'report_failure',lambda j,r:failures.append(r))
    return client,folder,lease,failures


def valid_result(lease):
    return {'schema_version':'etf-research-result-v1','job_id':lease['job']['job_id'],
        'input_hash':lease['package']['input_hash'],'producer':'manual','producer_version':'fixture',
        'model':'none','summary':'test only','limitations':['mock result']}


def test_invalid_existing_result_reports_failure_without_model_retry(tmp_path,monkeypatch):
    client,folder,lease,failures=setup_client(tmp_path,monkeypatch)
    bridge.atomic_write(folder/'result.json',b'{"partial":')
    monkeypatch.setattr(bridge,'codex_once',lambda *a,**kw:pytest.fail('must not repay'))
    with pytest.raises((bridge.BridgeError,ValueError)):
        client.work_once('codex','fixture')
    assert failures==['invalid_result']
    client.http.close()


def test_valid_result_upload_failure_is_retryable_without_new_model(tmp_path,monkeypatch):
    client,folder,lease,failures=setup_client(tmp_path,monkeypatch)
    bridge.atomic_write(folder/'result.json',bridge.canonical_bytes(valid_result(lease)))
    monkeypatch.setattr(bridge,'codex_once',lambda *a,**kw:pytest.fail('must not repay'))
    def offline(*a,**kw):raise bridge.BridgeError('bridge_http_503')
    monkeypatch.setattr(client,'post',offline)
    with pytest.raises(bridge.BridgeError,match='503'):
        client.work_once('codex','fixture')
    assert failures==[] and (folder/'result.json').exists()
    monkeypatch.setattr(client,'post',lambda *a,**kw:{'status':'completed','review_status':'pending'})
    assert client.work_once('codex','fixture')
    assert failures==[]
    client.http.close()


def test_interrupted_attempt_cannot_be_paid_again(tmp_path,monkeypatch):
    client,folder,lease,failures=setup_client(tmp_path,monkeypatch)
    bridge.atomic_write(folder/'execution-attempt.json',bridge.canonical_bytes({'job_id':lease['job']['job_id']}))
    monkeypatch.setattr(bridge,'codex_once',lambda *a,**kw:pytest.fail('must not repay'))
    with pytest.raises(bridge.BridgeError,match='previous_execution'):
        client.work_once('codex','fixture',approved=True)
    assert failures==['runner_failed']
    client.http.close()


def test_model_requires_explicit_approval_before_attempt(tmp_path,monkeypatch):
    client,folder,lease,failures=setup_client(tmp_path,monkeypatch)
    monkeypatch.setattr(bridge,'codex_once',lambda *a,**kw:pytest.fail('approval required'))
    with pytest.raises(bridge.BridgeError,match='explicit_execution_approval_required'):
        client.work_once('codex','fixture')
    assert failures==[] and not (folder/'execution-attempt.json').exists()
    client.http.close()


def test_same_root_runner_is_locked_without_failing_active_job(tmp_path,monkeypatch):
    client,folder,lease,failures=setup_client(tmp_path,monkeypatch)
    lock=bridge.PipelineFileLock(client.root/'runner-execution.lock').acquire()
    try:
        with pytest.raises(bridge.BridgeError,match='runner_execution_busy'):
            client.work_once('codex','fixture',approved=True)
        assert failures==[] and not (folder/'execution-attempt.json').exists()
    finally:
        lock.release();client.http.close()


@pytest.mark.skipif(os.name!='nt',reason='requires actual Windows NTFS ACL')
def test_actual_windows_acl_and_inherited_private_files(tmp_path):
    from app.workspace.bridge_runtime import windows_private_directory,RuntimeSafetyError
    folder=bridge.private_root(tmp_path/'windows-private')
    bridge.atomic_write(folder/'test.json',b'{}')
    assert bridge.read_json(folder/'test.json')=={}
    # Give Everyone read on just this isolated test directory; must not repair it.
    import subprocess
    subprocess.run(['icacls',str(folder),'/grant','*S-1-1-0:(R)'],check=True,capture_output=True)
    try:
        with pytest.raises((bridge.BridgeError,RuntimeSafetyError),match='acl_unsafe'):
            bridge.private_root(folder)
    finally:
        subprocess.run(['icacls',str(folder),'/remove:g','*S-1-1-0'],check=True,capture_output=True)
    windows_private_directory(folder,created=False)
