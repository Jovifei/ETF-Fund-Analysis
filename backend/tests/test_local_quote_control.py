"""Real provider-adapter/TaskService/SQLite quote shape, not a fabricated result."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.models import Instrument, QuoteSnapshot, TaskRun
from app.providers.types import QuoteRecord
from app.services.execution_policy import TaskExecutionPolicy
from app.services.task_service import TaskService
from app.workspace import local_compute
from app.workspace.local_dispatch import dispatch_once
from app.workspace.local_job_ledger import LocalJobLedger
from app.workspace.shadow_bundle import digest
from test_closed_session_research import accept, closing_batch as closing_batch

TZ = ZoneInfo("Asia/Shanghai")
CODES = ["510300.SH", "512480.SH"]


@pytest.fixture
def real_quotes(tmp_path, monkeypatch):
    from app.services import market_service, task_service
    at = datetime(2026, 10, 16, 14, 30, tzinfo=TZ)
    class ClockMeta(type):
        def __instancecheck__(cls, value):
            return isinstance(value, datetime)
    class Clock(datetime, metaclass=ClockMeta):
        @classmethod
        def now(cls, tz=None):
            return at.astimezone(tz) if tz else at.replace(tzinfo=None)
    for module in (market_service, task_service, local_compute):
        monkeypatch.setattr(module, "datetime", Clock)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'quotes.sqlite3').as_posix()}",
                        market_provider="public_composite")
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        db.add_all([Instrument(ts_code=code, symbol=code[:6], name="synthetic", enabled=True) for code in CODES])
    class Provider:
        name = "sina"
        missing = False
        partial = False
        def fetch_spot_quotes(self, codes):
            selected = codes[:1] if self.missing else codes
            return [QuoteRecord(ts_code=code, quote_time=at-timedelta(minutes=30 if self.partial else 0),
                    price=1.2, source="sina:hq_sinajs:v1", is_realtime=True) for code in selected]
    provider = Provider()
    factory = TaskService
    def service(settings, **kwargs):
        return factory(settings, provider=provider,
                       execution_policy=TaskExecutionPolicy(resolve_runtime_provider=False))
    monkeypatch.setattr(task_service, "TaskService", service)
    yield settings, provider, engine, at
    engine.dispose()


def _quote_only_chain(monkeypatch):
    original_run = TaskService.run
    def run(self, db, task, **kwargs):
        if task == "refresh_quotes":
            return original_run(self, db, task, **kwargs)
        return {"status": "succeeded", "coverage_complete": True, "run_id": kwargs["run_id"]}
    monkeypatch.setattr(TaskService, "run", run)


@pytest.mark.parametrize("compute_mode", ["full", "fast"])
def test_real_task_quote_shape_gets_only_typed_control_coverage(real_quotes, monkeypatch, tmp_path, compute_mode):
    from app.workspace.local_execution import execution_identity
    from app.workspace.local_stability import _delivery, DEFAULT_DEADLINES
    from app.workspace.local_atomic import write_json_atomic
    settings, provider, engine, at = real_quotes
    _quote_only_chain(monkeypatch)
    monkeypatch.setattr(local_compute, "validate_base_manifest", lambda *args, **kwargs: {})
    identity = {"code_sha": "a"*40, "config_hash": "b"*64, "scope_hash": digest(sorted(CODES))}
    execution = execution_identity(b'{"universe":["510300.SH","512480.SH"]}',
        database=tmp_path / "quotes.sqlite3", profile="live", provider="public_composite",
        private_research=True, closed_session_research=False, sync_url="https://etf.joviluma.com/api/shadow/sync")
    def run(mode, **hooks):
        if compute_mode == "full":
            results = local_compute.compute_local(settings, universe=CODES, private_research=True,
                closed_session_research=True, on_task=hooks["on_task"])
        else:
            results = local_compute.compute_local_fast(settings, CODES, base_manifest={}, code_sha=identity["code_sha"],
                private_research=True, now=at, on_task=hooks["on_task"])
        quote = next(result for result in results if result["task_name"] == "refresh_quotes")
        manifest = {"contract_version": "local-display-v2", "sequence": 1,
            "code_sha": identity["code_sha"], "config_hash": identity["config_hash"], "universe": CODES,
            "generated_at": at.isoformat(), "expires_at": (at + timedelta(hours=2)).isoformat(),
            "execution_lineage": {"contract_version": "local-execution-lineage-v1", "mode": compute_mode,
                                  **execution, "base_input_hash": digest({"synthetic_base": compute_mode}),
                                  "quote_batch_hash": quote.proof["quote_batch_hash"]}}
        bundle, path = {"manifest": manifest}, tmp_path / "outbox" / "bundle_1.json"
        hooks["on_export_intent"](bundle, path)
        write_json_atomic(path, bundle)
        hooks["on_export"](bundle, path)
        # Synthetic transport acknowledgment, no HTTP call or live acceptance claim.
        hooks["on_receipt"](manifest, {"status": "accepted", "sequence": 1, "bundle_id": digest(manifest),
                                      "manifest_hash": digest(manifest), "received_at": at.isoformat()})
        return 0
    calendar = SimpleNamespace(decision=lambda day: SimpleNamespace(verified=True, is_trade_day=True))
    assert dispatch_once(tmp_path / "ledger", identity, calendar=calendar, run_job=run,
                         replay=None, now=lambda: at, execution=execution) == 0
    summary = LocalJobLedger(tmp_path / "ledger").summary()
    quote = next(job for job in summary["jobs"] if job["job_name"] == "refresh_quotes")
    assert quote["details"].get("coverage_complete") is True
    assert quote["details"]["scope_hash"] == identity["scope_hash"]
    delivery = _delivery(at.date(), summary, identity["code_sha"], identity["config_hash"],
                         identity["scope_hash"], DEFAULT_DEADLINES)
    current = next(row for row in delivery["slots"] if row["slot_id"].endswith("14:30"))
    assert current["state"] == "PASS"
    assert delivery["state"] != "PASS"  # Other slots were not run, never infer a two-day pass.
    with Session(engine) as db:
        raw = db.scalar(select(TaskRun).where(TaskRun.task_name == "refresh_quotes")).result_json
        assert raw["status"] == "succeeded" and raw["requested"] == raw["received"] == 2
        assert not {"coverage_complete", "completed", "execution_scope"} & set(raw)


@pytest.mark.parametrize("mode", ["missing", "wrong_scope", "partial"])
def test_bad_real_quote_batch_does_not_gain_control_coverage(real_quotes, monkeypatch, tmp_path, mode):
    settings, provider, engine, at = real_quotes
    _quote_only_chain(monkeypatch)
    provider.missing = mode == "missing"
    provider.partial = mode == "partial"
    codes = [*CODES, "999999.SH"] if mode == "wrong_scope" else CODES
    captured = []
    local_compute.compute_local(settings, universe=codes, private_research=True,
        on_task=lambda name, result, run_id: captured.append((result, run_id))
        if name == "refresh_quotes" and result is not None else None)
    result, run_id = captured[0]
    assert local_compute.quote_control_coverage(result, scope_hash=digest(sorted(codes)), run_id=run_id) is None


def test_plain_json_or_mutated_typed_result_cannot_claim_control_scope(real_quotes, monkeypatch):
    settings, _, _, _ = real_quotes
    _quote_only_chain(monkeypatch)
    results = local_compute.compute_local(settings, universe=CODES, private_research=True)
    quote = next(result for result in results if result["task_name"] == "refresh_quotes")
    args = {"scope_hash": digest(sorted(CODES)), "run_id": quote["run_id"]}
    assert local_compute.quote_control_coverage(quote, **args)["coverage_complete"] is True
    assert local_compute.quote_control_coverage(dict(quote), **args) is None
    assert local_compute.quote_control_coverage(quote, **{**args, "scope_hash": "f"*64}) is None
    quote["received"] = 1
    assert local_compute.quote_control_coverage(quote, **args) is None


@pytest.mark.parametrize("change", ["old_batch", "wrong_run", "wrong_counts", "future_fetch", "changed_task", "wrong_selector"])
def test_real_quote_control_proof_requires_exact_db_task_and_new_batch(real_quotes, change):
    settings, provider, engine, at = real_quotes
    service = TaskService(settings, provider=provider,
        execution_policy=TaskExecutionPolicy(resolve_runtime_provider=False))
    try:
        with Session(engine) as db, db.begin():
            after_id = 0
            if change == "wrong_selector":
                old = QuoteSnapshot(instrument_id=db.scalar(select(Instrument.id)),
                    quote_time=at + timedelta(seconds=1), fetched_at=at-timedelta(seconds=5),
                    source="sina:hq_sinajs:v1", price=1.2, is_realtime=True,
                    timestamp_verified=True, quality_hash="e"*64)
                db.add(old); db.flush(); after_id = old.id
            raw = service.run(db, "refresh_quotes", codes=CODES, run_id="actual-quote-run")
            result, run_id = dict(raw), raw["run_id"]
            if change == "old_batch":
                after_id = max(row.id for row in db.scalars(select(QuoteSnapshot)))
            elif change == "wrong_run":
                run_id = "different-run"
            elif change == "wrong_counts":
                raw = {**raw, "received": 1}
            elif change == "future_fetch":
                db.scalar(select(QuoteSnapshot)).fetched_at = at + timedelta(seconds=5)
            elif change == "changed_task":
                db.scalar(select(TaskRun)).result_json = {**raw, "received": 1}
            db.flush()
            captured = local_compute._captured_quote_result(db, settings, universe=CODES,
                result=result, raw_result=raw, run_id=run_id, after_id=after_id,
                started_at=at, finished_at=at)
            assert local_compute.quote_control_coverage(captured, scope_hash=digest(sorted(CODES)), run_id=run_id) is None
    finally:
        service.close()


def test_closed_partial_proof_and_raw_quality_remain_unchanged(closing_batch):
    result = accept(closing_batch)
    raw = dict(result)
    captured = local_compute._captured_quote_result(closing_batch,
        Settings(_env_file=None, market_provider="public_composite"), universe=CODES,
        result=result, raw_result=result, run_id=result["run_id"], after_id=0,
        started_at=datetime(2026, 10, 15, 16, 10, tzinfo=TZ),
        finished_at=datetime(2026, 10, 15, 16, 10, 10, tzinfo=TZ))
    assert captured is result and dict(captured) == raw
    assert local_compute.closed_session_result_accepted(captured)
    assert captured["coverage_complete"] is False and captured["status"] == "partial"
    assert local_compute.quote_control_coverage(captured, scope_hash=digest(sorted(CODES)), run_id=result["run_id"]) is None
