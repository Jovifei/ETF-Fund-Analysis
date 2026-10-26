"""Synthetic provider input through the real local research pipeline."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import math

import pytest
from sqlalchemy import create_engine, select, event
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.models import Instrument, TaskRun, QuoteSnapshot, DailyBar, IndicatorSnapshot, ForecastSnapshot, SignalSnapshot, DecisionBoardSnapshot
from app.providers.mock import MockProvider
from app.providers.types import BarRecord, QuoteRecord
from app.services.execution_policy import TaskExecutionPolicy
from app.services.task_service import TaskService
from app.workspace import local_compute as local

TZ = ZoneInfo("Asia/Shanghai")
AT = datetime(2026, 10, 26, 17, 40, tzinfo=TZ)
SHA = "a" * 40
CODES = ["510300.SH", "510500.SH"]

@pytest.fixture
def settled_pipeline(tmp_path, monkeypatch):
    from app.services import market_service, task_service, signal_service, indicator_service, forecast_service, decision_board_service
    class ClockMeta(type):
        def __instancecheck__(cls, value):
            return isinstance(value, datetime)
    class Clock(datetime, metaclass=ClockMeta):
        @classmethod
        def now(cls, tz=None):
            return AT.astimezone(tz) if tz else AT.replace(tzinfo=None)
    for module in (market_service, task_service, signal_service, indicator_service, forecast_service, decision_board_service, local):
        if hasattr(module, "datetime"):
            monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setenv("GIT_COMMIT_SHA", SHA)
    settings = Settings(_env_file=None, app_env="test", market_provider="public_composite",
                        database_url=f"sqlite:///{tmp_path / 'research.sqlite3'}")
    cfg = settings.load_strategy()
    cfg["forecast"]["min_history"] = 60
    monkeypatch.setattr(Settings, "load_strategy", lambda self: cfg)
    class Provider(MockProvider):
        name = "synthetic_provider"
        missing_bar = False
        def fetch_daily_bars(self, code, start_date, end_date):
            rows = []
            day = start_date
            while day <= end_date:
                if day.weekday() < 5 and not (self.missing_bar and code == CODES[1] and day == AT.date()):
                    price = 2 + (day.toordinal() % 1000) * .0001 + .01 * math.sin(day.toordinal() / 10)
                    rows.append(BarRecord(ts_code=code, trade_date=day, open=price, high=price+.02,
                        low=price-.02, close=price, pre_close=price-.001, pct_change=.1,
                        volume=1000000, amount=price*1000000, adjust="none", source="akshare:em:v101"))
                day += timedelta(days=1)
            return rows
        def fetch_spot_quotes(self, codes):
            return [QuoteRecord(ts_code=code, quote_time=AT.replace(hour=16, minute=29), price=9.9,
                        pct_change=-12, volume=9, amount=9, premium_rate=50,
                        source="sina:hq_sinajs:v1", is_realtime=True) for code in codes]
    provider = Provider(settings)
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        db.add_all([Instrument(ts_code=code, symbol=code[:6], name="synthetic", enabled=True) for code in CODES])
    factory = TaskService
    monkeypatch.setattr(task_service, "TaskService", lambda settings, **kwargs: factory(settings, provider=provider,
                      execution_policy=TaskExecutionPolicy(resolve_runtime_provider=False)))
    def stamp(mapper, connection, target):
        target.generated_at = AT
    for model in (IndicatorSnapshot, ForecastSnapshot):
        event.listen(model, "before_insert", stamp)
    yield settings, provider, engine
    for model in (IndicatorSnapshot, ForecastSnapshot):
        event.remove(model, "before_insert", stamp)
    engine.dispose()


def test_full_research_uses_complete_settled_bars_when_quotes_are_after_close(settled_pipeline):
    settings, _, engine = settled_pipeline
    results = local.compute_local(settings, CODES, private_research=True, closed_session_research=True)
    assert results[-1]["task_name"] == "refresh_decision_board"
    assert results[-1]["status"] == "succeeded"
    quote_result = next(r for r in results if r["task_name"] == "refresh_quotes")
    assert quote_result["status"] == "partial"
    assert not local.closed_session_result_accepted(quote_result)
    with Session(engine) as db:
        run = db.scalar(select(TaskRun).where(TaskRun.task_name == "refresh_quotes"))
        assert run.status == "partial" and run.result_json["realtime"] == 0
        assert all(not q.is_realtime for q in db.scalars(select(QuoteSnapshot)))
    base = local.create_base_manifest(settings, CODES, code_sha=SHA, now=AT)
    assert base["target_trade_date"] == "2026-10-26"
    assert local.settled_daily_result_accepted(quote_result)
    bundle = local.export_local_v2(settings, sequence=1, code_sha=SHA, universe=CODES, now=AT,
                                  private_research=True, settled_daily_result=quote_result)
    obs = bundle["manifest"]["input_observation"]
    assert obs["basis"] == "settled_daily_bars" and obs["is_realtime"] is False
    assert bundle["manifest"]["source_qualification"] == "UNKNOWN"
    assert bundle["manifest"]["calibration_status"] == "not_calibrated"
    with Session(engine) as db:
        from app.services.signal_grade_service import SignalGradeService
        grades = SignalGradeService(settings).build(db, as_of=AT, research_input=quote_result.context)
        assert all(row["pct_change"] == .001 for row in grades["rows"])
        assert all(row["flow_share"]["premium_rate"] is None for row in grades["rows"])
        board = db.scalar(select(DecisionBoardSnapshot))
        assert all(row["return_1d"] == .001 for row in board.payload_json["rows"])
        assert all(row["provisional"]["used_for_derived_values"] is False for row in board.payload_json["rows"])
        assert all(not row["quote"]["is_realtime"] for row in board.payload_json["rows"])
        assert all(row["flow_share"]["premium_rate"] is None and row["flow_share"]["main_net_inflow"] is None
                   for row in board.payload_json["rows"])
        signals = db.scalars(select(SignalSnapshot)).all()
        assert signals and all(not row.is_actionable for row in signals)
        assert all("50.00%" not in str(row.reasons_json) for row in signals)
        from app.services.signal_service import SignalService
        for signal in signals:
            daily = db.scalar(select(DailyBar).where(DailyBar.instrument_id == signal.instrument_id,
                                                   DailyBar.trade_date == AT.date()))
            indicator = db.scalar(select(IndicatorSnapshot).where(IndicatorSnapshot.instrument_id == signal.instrument_id))
            expected, _ = SignalService._fund_quality(SimpleNamespace(amount=daily.amount, premium_rate=None), indicator)
            assert signal.evidence_json["fund_quality_score"] == expected


def test_complete_daily_research_precedes_legacy_closing_quote_proof(settled_pipeline, monkeypatch):
    from dataclasses import replace
    from app.services.signal_grade_service import SignalGradeService
    from app.services.signal_service import SignalService
    settings, provider, engine = settled_pipeline
    fetch = provider.fetch_spot_quotes
    monkeypatch.setattr(provider, "fetch_spot_quotes", lambda codes: [
        replace(row, quote_time=AT.replace(hour=15, minute=35), amount=200_000_000)
        for row in fetch(codes)
    ])
    results = local.compute_local(settings, CODES, private_research=True, closed_session_research=True)
    assert results[-1]["task_name"] == "refresh_decision_board" and results[-1]["status"] == "succeeded"
    proof = next(row for row in results if row["task_name"] == "refresh_quotes")
    assert local.settled_daily_result_accepted(proof)
    assert not local.closed_session_result_accepted(proof)
    with Session(engine) as db:
        run = db.scalar(select(TaskRun).where(TaskRun.task_name == "refresh_quotes"))
        assert run.status == "partial" and run.result_json["realtime"] == 0
        old_proof = local._closed_session_quote_result(db, settings, universe=CODES, result=run.result_json,
            after_id=0, started_at=AT, finished_at=AT, private_research=True, enabled=True)
        assert local.closed_session_result_accepted(old_proof)  # Input also satisfies the unchanged old window.
        grades = SignalGradeService(settings).build(db, as_of=AT, research_input=proof.context)
        assert all(row["pct_change"] == .001 for row in grades["rows"])
        board = db.scalar(select(DecisionBoardSnapshot)).payload_json
        assert all(row["return_1d"] == .001 for row in board["rows"])
        assert all(row["flow_share"]["premium_rate"] is None for row in board["rows"])
        for signal in db.scalars(select(SignalSnapshot)):
            daily = db.scalar(select(DailyBar).where(DailyBar.instrument_id == signal.instrument_id,
                                                   DailyBar.trade_date == AT.date()))
            indicator = db.scalar(select(IndicatorSnapshot).where(IndicatorSnapshot.instrument_id == signal.instrument_id))
            expected, _ = SignalService._fund_quality(SimpleNamespace(amount=daily.amount, premium_rate=None), indicator)
            assert signal.evidence_json["fund_quality_score"] == expected
            assert signal.evidence_json["snapshot_inputs"]["research_input"]["type"] == "settled_daily_research"
            assert not signal.is_actionable
    exported = local.export_local_v2(settings, sequence=1, code_sha=SHA, universe=CODES, now=AT,
                                    private_research=True, settled_daily_result=proof)
    assert exported["manifest"]["input_observation"]["type"] == "settled_daily_research"


def test_legacy_closing_quote_proof_remains_fallback_without_daily_identity(settled_pipeline, monkeypatch):
    from dataclasses import replace
    settings, provider, _ = settled_pipeline
    fetch = provider.fetch_spot_quotes
    monkeypatch.setattr(provider, "fetch_spot_quotes", lambda codes: [
        replace(row, quote_time=AT.replace(hour=15, minute=35)) for row in fetch(codes)
    ])
    monkeypatch.setenv("GIT_COMMIT_SHA", "")  # Daily authority requires a fixed computation identity.
    results = local.compute_local(settings, CODES, private_research=True, closed_session_research=True)
    assert results[-1]["task_name"] == "refresh_decision_board"
    proof = next(row for row in results if row["task_name"] == "refresh_quotes")
    assert local.closed_session_result_accepted(proof)
    assert not local.settled_daily_result_accepted(proof)
    exported = local.export_local_v2(settings, sequence=1, code_sha=SHA, universe=CODES, now=AT,
                                    private_research=True, closed_session_result=proof)
    assert exported["manifest"]["input_observation"]["contract_version"] == local.CLOSED_SESSION_INPUT_VERSION


@pytest.mark.parametrize("adjust", ["qfq", "hfq"])
def test_settled_signal_quality_uses_the_qualified_single_daily_basis(settled_pipeline, monkeypatch, adjust):
    from dataclasses import replace
    settings, provider, engine = settled_pipeline
    fetch = provider.fetch_daily_bars
    monkeypatch.setattr(provider, "fetch_daily_bars", lambda code, start, end: [
        replace(row, adjust=adjust, amount=200_000_000) for row in fetch(code, start, end)
    ])
    results = local.compute_local(settings, CODES, private_research=True, closed_session_research=True)
    assert any(local.settled_daily_result_accepted(row) for row in results)
    assert results[-1]["task_name"] == "refresh_decision_board" and results[-1]["status"] == "succeeded"
    with Session(engine) as db:
        assert set(db.scalars(select(DailyBar.adjust).distinct())) == {adjust}
        signals = db.scalars(select(SignalSnapshot)).all()
        assert len(signals) == len(CODES)
        assert all(row.evidence_json["fund_quality_score"] == 85 for row in signals)
        assert all(not row.is_actionable for row in signals)


@pytest.mark.parametrize("has_history", [True, False])
def test_settled_background_returns_never_fall_back_to_quote(settled_pipeline, has_history):
    from app.utils.hashing import stable_hash
    settings, provider, engine = settled_pipeline
    with Session(engine) as db, db.begin():
        background = db.scalar(select(Instrument).where(Instrument.ts_code == CODES[1]))
        if has_history:
            for row in provider.fetch_daily_bars(CODES[1], AT.date() - timedelta(days=420), AT.date() - timedelta(days=1)):
                columns = {key: getattr(row, key) for key in (
                    "trade_date", "open", "high", "low", "close", "pre_close", "volume", "amount", "pct_change", "adjust", "source")}
                db.add(DailyBar(instrument_id=background.id, **columns, quality_hash=stable_hash(columns),
                                fetched_at=AT - timedelta(days=3)))
        db.add(QuoteSnapshot(instrument_id=background.id, quote_time=AT.replace(hour=16, minute=29),
            fetched_at=AT, price=9.9, pct_change=-12, amount=9, premium_rate=50, source="sina:hq_sinajs:v1",
            is_realtime=False, timestamp_verified=False, degraded_reason="quote source timestamp is stale",
            quality_hash="e" * 64))
    results = local.compute_local(settings, CODES[:1], private_research=True, closed_session_research=True)
    proof = next(row for row in results if local.settled_daily_result_accepted(row))
    assert proof.context.base["background_count"] == len(CODES)
    with Session(engine) as db:
        board = db.scalar(select(DecisionBoardSnapshot)).payload_json
        assert {row["ts_code"] for row in board["rows"]} == set(CODES)
        background = next(row for row in board["rows"] if row["ts_code"] == CODES[1])
        assert background["returns"]["basis"] == ("confirmed_daily_close" if has_history else "unavailable")
        assert background["returns"]["as_of_date"] == ("2026-10-23" if has_history else None)
        assert background["return_1d"] == (.001 if has_history else None)
        assert background["returns"]["target_trade_date"] == AT.date().isoformat()
        assert len(db.scalars(select(SignalSnapshot)).all()) == 1


@pytest.mark.parametrize("mutation", ["bar", "quote", "task", "scope", "code", "time", "json", "derived",
                                       "calendar", "future_bar", "source", "adjust", "clone", "board", "quality_hash", "open_session"])
def test_settled_daily_export_revalidates_input_identity(settled_pipeline, mutation, tmp_path, monkeypatch):
    settings, _, engine = settled_pipeline
    results = local.compute_local(settings, CODES, private_research=True, closed_session_research=True)
    proof = next(row for row in results if local.settled_daily_result_accepted(row))
    codes, code_sha, now = CODES, SHA, AT
    if mutation in {"bar", "quote", "task", "derived", "future_bar", "source", "adjust", "board", "quality_hash"}:
        with Session(engine) as db, db.begin():
            if mutation == "bar":
                db.scalar(select(DailyBar).order_by(DailyBar.id)).amount += 1
            elif mutation == "quote":
                db.scalar(select(QuoteSnapshot)).price += 1
            elif mutation == "task":
                db.scalar(select(TaskRun).where(TaskRun.task_name == "refresh_quotes")).status = "succeeded"
            elif mutation == "derived":
                db.scalar(select(IndicatorSnapshot)).input_hash = "0" * 64
            elif mutation == "future_bar":
                db.scalar(select(DailyBar).order_by(DailyBar.trade_date.desc())).trade_date = AT.date() + timedelta(days=1)
            elif mutation == "source":
                db.scalar(select(DailyBar)).source = "unqualified_source"
            elif mutation == "adjust":
                db.scalar(select(DailyBar)).adjust = "unknown"
            elif mutation == "quality_hash":
                db.scalar(select(QuoteSnapshot)).quality_hash = "wrong"
            else:
                board = db.scalar(select(DecisionBoardSnapshot))
                board.payload_json = {**board.payload_json, "target_trade_date": "2026-10-23"}
    elif mutation == "scope":
        codes = CODES[:1]
    elif mutation == "code":
        code_sha = "b" * 40
    elif mutation == "time":
        now = AT - timedelta(days=1)
    elif mutation == "open_session":
        now = (AT + timedelta(days=1)).replace(hour=10)
    elif mutation == "calendar":
        from app.services.trading_calendar_service import TradingCalendarService
        monkeypatch.setattr(TradingCalendarService, "decision", lambda self, day: SimpleNamespace(verified=False, is_trade_day=True))
    elif mutation == "clone":
        import shutil
        from pathlib import Path
        cloned = tmp_path / "clone.sqlite3"
        shutil.copyfile(Path(engine.url.database), cloned)
        settings = settings.model_copy(update={"database_url": f"sqlite:///{cloned}"})
    else:
        proof = dict(proof)
        assert not local.settled_daily_result_accepted(proof)
    with pytest.raises(ValueError):
        local.export_local_v2(settings, sequence=1, code_sha=code_sha, universe=codes, now=now,
                              private_research=True, settled_daily_result=proof)


def test_settled_daily_keeps_background_scope_with_subset_targets(settled_pipeline):
    settings, _, engine = settled_pipeline
    results = local.compute_local(settings, CODES[:1], private_research=True, closed_session_research=True)
    assert results[-1]["task_name"] == "refresh_decision_board"
    proof = next(row for row in results if local.settled_daily_result_accepted(row))
    assert proof.context.base["background_count"] == 2
    assert proof.context.base["target_codes"] == CODES[:1]
    with Session(engine) as db:
        payload = db.scalar(select(DecisionBoardSnapshot)).payload_json
        assert {row["ts_code"] for row in payload["rows"]} == set(CODES)
        assert len(db.scalars(select(SignalSnapshot)).all()) == 1


def test_settled_daily_does_not_evaluate_intraday_provisional(settled_pipeline, monkeypatch):
    from app.services.decision_board_service import DecisionBoardService
    settings, _, _ = settled_pipeline
    def forbidden(*args):
        raise AssertionError("closing research must not read provisional inputs")
    monkeypatch.setattr(DecisionBoardService, "_provisional_status", forbidden)
    results = local.compute_local(settings, CODES, private_research=True, closed_session_research=True)
    assert results[-1]["task_name"] == "refresh_decision_board"
    assert results[-1]["status"] == "succeeded"


def test_real_settled_pipeline_observer_persists_distinct_research_basis(settled_pipeline, tmp_path):
    from app.workspace.local_dispatch import dispatch_once
    from app.workspace.local_job_ledger import LocalJobLedger
    from app.workspace.local_stability import _delivery
    from app.workspace.shadow_bundle import digest
    from app.workspace.local_display_contract import verify_bundle_integrity
    from app.services.trading_calendar_service import TradingCalendarService
    from app.utils.hashing import stable_hash
    settings, _, _ = settled_pipeline
    identity = {"code_sha": SHA, "config_hash": stable_hash(settings.load_strategy()), "scope_hash": digest(sorted(CODES))}
    execution = {"execution_hash": "b" * 64, "config_file_hash": "c" * 64}
    def run(mode, **hooks):
        assert mode == "full"
        results = local.compute_local(settings, CODES, private_research=True, closed_session_research=True,
                                      on_task=hooks["on_task"])
        proof = next(item for item in results if local.settled_daily_result_accepted(item))
        assert local.settled_daily_control(dict(proof), scope_hash=identity["scope_hash"], run_id=proof["run_id"]) is None
        base = local.create_base_manifest(settings, CODES, code_sha=SHA, now=AT, execution_hash=execution["execution_hash"])
        lineage = local.build_execution_lineage(settings, CODES, results, base_manifest=base, mode="full", now=AT, **execution)
        bundle = local.export_local_v2(settings, sequence=1, code_sha=SHA, universe=CODES, now=AT,
            private_research=True, settled_daily_result=proof, execution_lineage=lineage)
        assert verify_bundle_integrity(bundle, now=AT)
        path = tmp_path / "bundle_1.json"
        hooks["on_export_intent"](bundle, path)
        hooks["on_export"](bundle, path)
        manifest = bundle["manifest"]
        # Synthetic transport only; compute, proof, ledger and validator are real.
        receipt = {"status": "accepted", "sequence": 1, "bundle_id": digest(manifest),
                   "manifest_hash": digest(manifest), "received_at": AT.isoformat()}
        hooks["on_receipt"](manifest, receipt)
        return 0
    root = tmp_path / "schedule"
    assert dispatch_once(root, identity, calendar=TradingCalendarService(settings), run_job=run,
                         replay=lambda **kwargs: None, now=lambda: AT, slots=("17:40",), execution=execution) == 0
    ledger = LocalJobLedger(root).summary()
    quote_job = next(job for job in ledger["jobs"] if job["job_name"] == "refresh_quotes")
    assert quote_job["status"] == "partial"
    assert quote_job["details"]["accepted_closed_session"] is False
    assert quote_job["details"]["accepted_settled_daily"] is True
    assert quote_job["details"]["coverage_complete"] is False
    report = _delivery(AT.date(), ledger, SHA, identity["config_hash"], identity["scope_hash"], {"17:40": 300})
    slot = next(row for row in report["slots"] if row["slot_id"].endswith("17:40"))
    assert slot["state"] == "PASS"
    assert slot["research_coverage_accepted"] is True and slot["coverage_complete"] is False
    assert slot["input_qualification"] == "settled_daily_research"
    assert slot["closed_research_jobs"] == 0 and slot["settled_daily_research_jobs"] == 1


def test_incomplete_settled_history_still_blocks_following_stages(settled_pipeline):
    settings, provider, _ = settled_pipeline
    provider.missing_bar = True
    results = local.compute_local(settings, CODES, private_research=True, closed_session_research=True)
    assert not any(r["task_name"] == "refresh_decision_board" for r in results)
    assert results[-1]["status"] != "succeeded"
