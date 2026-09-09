from datetime import date, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from app.main import app
from app.workspace.protocol import DataRequest
from app.workspace.journal import Note, scope
from app.workspace.data_jobs import enqueue
from app.workspace.worker import task_sequence
from app.workspace.models import WorkspacePreference
from app.core.security import optional_current_user
from types import SimpleNamespace


def test_recompute_never_requests_provider_tasks():
    assert [name for name,_ in task_sequence('recompute',[],420)] == [
      'refresh_indicators','refresh_forecasts','refresh_signals','refresh_decision_board']


def test_factor_names_only_for_diagnostics_and_legacy_idempotency(db_session):
    key=uuid4().hex
    with pytest.raises(ValidationError): DataRequest(task='prices',factor_names=['rsi14'],request_key=key)
    with pytest.raises(ValidationError): DataRequest(task='factors',factor_names=['rsi14','rsi14'],request_key=key)
    req=DataRequest(task='prices',request_key=key)
    job,created=enqueue(db_session,req,None)
    job.request_json={k:v for k,v in job.request_json.items() if k!='factor_names'};db_session.flush()
    assert enqueue(db_session,req,None)[1] is False
    db_session.rollback()


def test_factor_diagnostics_keeps_price_only_history_read_only(db_session):
    from app.core.config import get_settings
    from app.models import DailyBar, Instrument
    from app.workspace.factor_diagnostics import run

    code = "598" + uuid4().hex[:3].upper() + ".SH"
    instrument = Instrument(ts_code=code, symbol=code[:6], name="price-only factor fixture", kind="ETF", enabled=True)
    db_session.add(instrument)
    db_session.flush()
    for offset in range(180):
        close = 2.0 + offset * 0.01
        db_session.add(DailyBar(
            instrument_id=instrument.id,
            trade_date=date(2025, 1, 1) + timedelta(days=offset),
            open=close,
            high=close + 0.02,
            low=close - 0.02,
            close=close + 0.01,
            volume=None,
            amount=None,
            source="akshare:sina:v101",
            adjust="none",
            quality_hash=str(offset),
        ))
    db_session.flush()
    settings = get_settings().model_copy(update={"market_provider": "public_composite"})
    report = run(db_session, settings, selected=["return_20d"])
    assert report["status"] == "diagnostic"
    assert report["actionable"] is False
    assert report["price_only_instruments"] >= 1
    assert report["metrics"] and report["metrics"][0]["factor"] == "return_20d"
    db_session.rollback()


def test_review_notes_are_private_revision_checked_and_not_strategy_edits(bootstrapped):
    # Existing user ids are not invented; test auth-disabled local owner first.
    day='2025-01-02'
    with TestClient(app) as client:
        result=client.put('/api/workspace/review-notes/'+day,json={'revision':0,'thesis':'人工记录','proposal':'待检验假设'})
        assert result.status_code==200,result.text
        note=result.json()['note']; assert note['source']=='manual' and note['revision']==1
        assert result.json()['model_called'] is False and result.json()['strategy_modified'] is False
        conflict=client.put('/api/workspace/review-notes/'+day,json={'revision':0,'thesis':'旧写入'})
        assert conflict.status_code==409
        saved=client.put('/api/workspace/review-notes/'+day,json={'revision':1,'thesis':'修订','outcome':'未兑现'})
        assert saved.status_code==200
        assert len(saved.json()['note']['recent_revisions'])==1
        assert saved.json()['note']['context']==note['context']
        assert client.get('/api/workspace/review-notes/'+day).headers['cache-control']=='private, no-store'
        app.dependency_overrides[optional_current_user]=lambda: SimpleNamespace(id=999999)
        try:
            assert client.get('/api/workspace/review-notes/'+day).json()['note'] is None
            assert client.get('/api/workspace/review-notes').json()['items']==[]
        finally: app.dependency_overrides.clear()
        assert client.put('/api/workspace/review-notes/2099-01-01',json={'thesis':'future'}).status_code==422
        assert client.post('/api/workspace/data-jobs',json={'task':'factors','factor_names':['nonexistent_abc'],'request_key':uuid4().hex}).status_code==422


def test_local_ocr_is_opt_in_and_requires_external_models(tmp_path):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('v103_live',Path(__file__).resolve().parents[2]/'scripts/run_workspace_live.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    config=tmp_path/'config.env';config.write_text('OCR_MODE=local_paddle\n');config.chmod(0o600)
    with pytest.raises(ValueError): module.prepare(config,tmp_path/'data')
    models=tmp_path/'models';models.mkdir()
    config.write_text('OCR_MODE=local_paddle\nOCR_LOCAL_MODEL_DIR='+str(models)+'\n')
    env,_=module.prepare(config,tmp_path/'data')
    assert env['OCR_MODE']=='local_paddle' and env['OCR_CLOUD_REVIEW_ENABLED']=='false'
    config.write_text('OCR_MODE=disabled\n')
    assert module.prepare(config,tmp_path/'data')[0]['OCR_MODE']=='disabled'


def test_archive_contains_only_market_records_and_does_not_write_db(bootstrapped,tmp_path):
    import importlib.util, gzip, json, hashlib
    from pathlib import Path
    from sqlalchemy import event
    from app.db.session import get_engine, session_scope
    spec=importlib.util.spec_from_file_location('v103_archive',Path(__file__).resolve().parents[2]/'scripts/archive_market_history.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    statements=[]
    def sql(*args): statements.append(args[2])
    engine=get_engine();event.listen(engine,'before_cursor_execute',sql)
    try:
        with session_scope() as db:
            output=tmp_path/'archive'
            value=module.export(db,output,['512480.SH'],30)
            assert value['etf_rows']==30 and value['includes_holdings'] is False
            assert hashlib.sha256((output/value['file']).read_bytes()).hexdigest()==value['sha256']
            lines=gzip.decompress((output/value['file']).read_bytes()).decode().splitlines()
            assert json.loads(lines[0])['ts_code']=='512480.SH'
            assert not any(line.lstrip().upper().startswith(('UPDATE','INSERT','DELETE')) for line in statements)
            with pytest.raises(FileExistsError): module.export(db,output,['512480.SH'])
            with pytest.raises(ValueError): module.export(db,tmp_path/'bad',['not-code'])
    finally: event.remove(engine,'before_cursor_execute',sql)
