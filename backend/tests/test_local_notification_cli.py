from datetime import datetime,timedelta,timezone
import importlib.util
from pathlib import Path
import json,sqlite3,sys
import pytest
from app.workspace.shadow_bundle import digest
from test_local_digest import packet as packet
from test_local_digest import AT

@pytest.fixture
def cli():
    path=Path(__file__).resolve().parents[2]/"scripts"/"run_local_notifications.py"
    def load():
        assert path.is_file(), "notification CLI is missing"
        spec=importlib.util.spec_from_file_location("notification_cli_test",path)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return load


@pytest.mark.skipif(sys.platform!="win32",reason="CurrentUser DPAPI setup is native Windows only")
def test_configuration_uses_hidden_secret_prompt_and_no_network(cli,tmp_path):
    cli=cli()
    from app.workspace.local_notifications import load_smtp_config
    (tmp_path/".local-live").touch()
    answers=iter(["fixture@example.invalid","smtp.example.invalid","465","ssl",""])
    result=cli.configure(tmp_path,ask=lambda p:next(answers),secret=lambda p:"synthetic-code")
    assert result["state"]=="CONFIGURED" and result["enabled"] is False
    config,policy=load_smtp_config(tmp_path)
    assert config.password=="synthetic-code" and not policy["enabled"]
    assert "synthetic-code" not in str(result) and "fixture@" not in str(result)


def seed(root,bundle,receipt):
    (root/".local-live").touch();(root/"state").mkdir(exist_ok=True);(root/"outbox").mkdir()
    path=root/"outbox"/"bundle_7.json";path.write_text(json.dumps(bundle))
    path.with_suffix(".receipt.json").write_text(json.dumps(receipt))
    with sqlite3.connect(root/"state"/"schedule.sqlite3") as db:
        db.execute("CREATE TABLE attempts (slot_id TEXT,status TEXT,code_sha TEXT,config_hash TEXT,bundle_file TEXT,receipt TEXT,sequence INTEGER,finished_at TEXT)")
        db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?)",("2026-10-26 14:30","DELIVERED","a"*40,"b"*64,path.name,json.dumps(receipt),7,AT.isoformat()))


def test_dispatch_builds_once_and_never_sends_when_preview(cli,tmp_path,packet):
    cli=cli()
    b,r=packet;seed(tmp_path,b,r)
    result=cli.dispatch(tmp_path,now=AT+timedelta(minutes=1),code_sha="a"*40,config_hash="b"*64,
                        dry_run=True,recipient_id="c"*64,slots=("14:30",),calendar_verified=True)
    assert result["state"]=="PREVIEW" and result["queued"]==1
    result=cli.dispatch(tmp_path,now=AT+timedelta(minutes=2),code_sha="a"*40,config_hash="b"*64,
                        dry_run=True,recipient_id="c"*64,slots=("14:30",),calendar_verified=True)
    assert result["queued"]==0


def test_missing_delivery_emits_status_at_deadline(cli,tmp_path):
    cli=cli()
    (tmp_path/".local-live").touch()
    result=cli.dispatch(tmp_path,now=AT+timedelta(minutes=15),code_sha="a"*40,config_hash="b"*64,
                        dry_run=True,recipient_id="c"*64,slots=("14:30",),calendar_verified=True)
    assert result["queued"]==1 and result["notices"][0]["kind"]=="status"
    assert "body" not in str(result)


def test_corrupt_receipt_produces_deadline_status_and_continues_other_slots(cli,tmp_path,packet):
    cli=cli();b,r=packet;seed(tmp_path,b,r)
    (tmp_path/"outbox"/"bundle_7.receipt.json").write_text("not JSON")
    result=cli.dispatch(tmp_path,now=AT+timedelta(minutes=20),code_sha="a"*40,config_hash="b"*64,
        dry_run=True,recipient_id="c"*64,slots=("14:30","11:40"),calendar_verified=True)
    assert result["queued"]==2
    assert [x["kind"] for x in result["notices"]]==["status","status"]


@pytest.mark.parametrize("shape",["row_scalar","quote_string","detail_scalar","quote_flag_string"])
def test_semantic_bad_shapes_become_status_instead_of_stopping_dispatch(cli,tmp_path,packet,shape):
    cli=cli();b,r=packet
    from app.workspace.local_display_contract import compute_parts_hashes
    if shape=="row_scalar":b["parts"]["overview"]["rows"]=[123]
    elif shape=="quote_string":b["parts"]["details"]["510300.SH"]["quote"]="invalid"
    elif shape=="detail_scalar":b["parts"]["details"]["510300.SH"]=17
    else:b["parts"]["details"]["510300.SH"]["quote"]["is_realtime"]="false"
    b["manifest"]["parts_hashes"]=compute_parts_hashes(b["parts"])
    r.update(bundle_id=digest(b["manifest"]),manifest_hash=digest(b["manifest"]))
    seed(tmp_path,b,r)
    result=cli.dispatch(tmp_path,now=AT+timedelta(minutes=20),code_sha="a"*40,config_hash="b"*64,
        dry_run=True,recipient_id="c"*64,slots=("14:30",),calendar_verified=True)
    assert result["queued"]==1 and result["notices"][0]["kind"]=="status"


@pytest.mark.skipif(sys.platform!="win32",reason="CurrentUser DPAPI setup is native Windows only")
def test_enable_and_disable_subcommands(cli,tmp_path):
    cli=cli()
    (tmp_path/".local-live").touch()
    answers=iter(["fixture@example.invalid","smtp.example.invalid","465","ssl",""])
    result=cli.configure(tmp_path,ask=lambda p:next(answers),secret=lambda p:"code-123")
    assert result["enabled"] is False

    # enable command
    rc=cli.main(["enable","--root",str(tmp_path),"--confirm-owner-switchover"])
    assert rc==0
    from app.workspace.local_notifications import load_smtp_config
    _,policy=load_smtp_config(tmp_path)
    assert policy["enabled"] is True

    # disable command
    rc=cli.main(["disable","--root",str(tmp_path)])
    assert rc==0
    _,policy=load_smtp_config(tmp_path)
    assert policy["enabled"] is False


class _RecordingStream:
    def __init__(self,*,fail=False):
        self.reconfigure_calls=[]
        self.fail=fail
        self.written=[]
    def reconfigure(self,**kwargs):
        self.reconfigure_calls.append(kwargs)
        if self.fail:
            raise ValueError("stream does not support reconfigure")
    def write(self,text):
        self.written.append(text)
    def flush(self):
        pass


def test_stdio_is_pinned_to_utf8(cli,monkeypatch):
    cli=cli()
    out,err=_RecordingStream(),_RecordingStream()
    monkeypatch.setattr(sys,"stdout",out)
    monkeypatch.setattr(sys,"stderr",err)
    cli._force_utf8_stdio()
    assert out.reconfigure_calls==[{"encoding":"utf-8"}]
    assert err.reconfigure_calls==[{"encoding":"utf-8"}]


def test_stdio_pinning_survives_streams_without_reconfigure(cli,monkeypatch):
    cli=cli()
    out,err=_RecordingStream(fail=True),_RecordingStream(fail=True)
    monkeypatch.setattr(sys,"stdout",out)
    monkeypatch.setattr(sys,"stderr",err)
    cli._force_utf8_stdio()


def test_main_forces_utf8_stdio_before_printing(cli,tmp_path,monkeypatch):
    cli=cli()
    (tmp_path/".local-live").touch()
    out,err=_RecordingStream(),_RecordingStream()
    monkeypatch.setattr(sys,"stdout",out)
    monkeypatch.setattr(sys,"stderr",err)
    rc=cli.main(["status","--root",str(tmp_path)])
    assert rc==1
    assert out.reconfigure_calls==[{"encoding":"utf-8"}]
    assert err.reconfigure_calls==[{"encoding":"utf-8"}]
    assert "CONFIG_REQUIRED" in "".join(out.written)
