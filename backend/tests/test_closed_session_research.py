"""Only a verified new closing batch may continue non-realtime research."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.models import Instrument, QuoteSnapshot, TaskRun
from app.workspace import local_compute

TZ = ZoneInfo("Asia/Shanghai")
PARTIAL = {"run_id": "synthetic-run", "status": "partial", "requested": 2, "received": 2,
           "inserted": 2, "realtime": 0, "raw_realtime": 2, "degraded": 2,
           "missing": 0, "missing_codes": [], "coverage_complete": False}


@pytest.fixture
def closing_batch(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'closing.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for index, code in enumerate(("510300.SH", "512480.SH"), 1):
            inst = Instrument(ts_code=code, symbol=code[:6], name="synthetic")
            db.add(inst); db.flush()
            db.add(QuoteSnapshot(instrument_id=inst.id, quote_time=datetime(2026, 10, 15, 15, 35, tzinfo=TZ),
                fetched_at=datetime(2026, 10, 15, 16, 10, 5, tzinfo=TZ), price=1.2,
                source="sina:hq_sinajs:v1", is_realtime=False, timestamp_verified=False,
                degraded_reason="quote source timestamp is stale", quality_hash=str(index) * 64))
        db.flush()
        db.add(TaskRun(run_id="synthetic-run", task_name="refresh_quotes", status="partial",
            started_at=datetime(2026, 10, 15, 16, 10, tzinfo=TZ),
            finished_at=datetime(2026, 10, 15, 16, 10, 9, tzinfo=TZ), result_json=dict(PARTIAL)))
        db.flush()
        yield db
    engine.dispose()


def accept(db, **changes):
    kwargs = dict(universe=["510300.SH", "512480.SH"],
        result=dict(PARTIAL),
        after_id=0, started_at=datetime(2026, 10, 15, 16, 10, tzinfo=TZ),
        finished_at=datetime(2026, 10, 15, 16, 10, 10, tzinfo=TZ),
        private_research=True, enabled=True,
        calendar=SimpleNamespace(decision=lambda day: SimpleNamespace(verified=True, is_trade_day=True)))
    kwargs.update(changes)
    return local_compute._closed_session_quote_result(db,
        Settings(_env_file=None, market_provider="public_composite"), **kwargs)


def test_closing_batch_retains_partial_and_stale_flags_with_typed_evidence(closing_batch):
    result = accept(closing_batch)
    assert local_compute.closed_session_result_accepted(result)
    assert result["status"] == "partial" and result["realtime"] == 0
    assert result["closed_session_research"]["source_session"] == "2026-10-15"
    assert result["closed_session_research"]["mode"] == "closed_session_nonrealtime"
    assert not local_compute.closed_session_result_accepted(dict(result))
    row = closing_batch.query(QuoteSnapshot).first()
    assert row.is_realtime is False and row.timestamp_verified is False
    assert row.degraded_reason == "quote source timestamp is stale"


@pytest.mark.parametrize("change", [
    {"private_research": False}, {"enabled": False},
    {"started_at": datetime(2026, 10, 15, 14, 40, tzinfo=TZ), "finished_at": datetime(2026, 10, 15, 14, 40, 10, tzinfo=TZ)},
    {"started_at": datetime(2026, 10, 14, 23, 59, tzinfo=TZ)},
    {"calendar": SimpleNamespace(decision=lambda day: SimpleNamespace(verified=False, is_trade_day=True))},
    {"calendar": SimpleNamespace(decision=lambda day: SimpleNamespace(verified=True, is_trade_day=False))},
    {"after_id": 1},
])
def test_closed_scope_and_calendar_are_independent_hard_gates(closing_batch, change):
    assert not local_compute.closed_session_result_accepted(accept(closing_batch, **change))


@pytest.mark.parametrize("field,value", [
    ("quote_time", datetime(2026, 10, 14, 15, 30, tzinfo=TZ)),
    ("quote_time", datetime(2026, 10, 15, 14, 59, tzinfo=TZ)),
    ("quote_time", datetime(2026, 10, 15, 17, 0, tzinfo=TZ)),
    ("fetched_at", datetime(2026, 10, 15, 16, 10, 11, tzinfo=TZ)),
    ("fetched_at", datetime(2026, 10, 15, 16, 9, 59, tzinfo=TZ)),
    ("source", "mock"), ("price", 0), ("degraded_reason", "provider qualification missing"),
    ("timestamp_verified", True), ("is_realtime", True), ("quality_hash", "missing")
])
def test_invalid_or_non_stale_closing_rows_cannot_pass(closing_batch, field, value):
    setattr(closing_batch.query(QuoteSnapshot).first(), field, value)
    closing_batch.flush()
    assert not local_compute.closed_session_result_accepted(accept(closing_batch))


def test_duplicate_new_rows_cannot_be_silently_deduplicated(closing_batch):
    row = closing_batch.query(QuoteSnapshot).first()
    closing_batch.add(QuoteSnapshot(instrument_id=row.instrument_id, quote_time=row.quote_time,
        fetched_at=row.fetched_at, price=1.2, source=row.source, is_realtime=False,
        timestamp_verified=False, degraded_reason=row.degraded_reason, quality_hash="c" * 64))
    closing_batch.flush()
    assert not local_compute.closed_session_result_accepted(accept(closing_batch))


def test_sqlite_naive_times_follow_existing_settings_timezone_contract(closing_batch):
    closing_batch.expire_all()
    assert closing_batch.query(QuoteSnapshot).first().quote_time.tzinfo is None
    assert local_compute.closed_session_result_accepted(accept(closing_batch))


@pytest.mark.parametrize("field,value", [("status", "succeeded"), ("received", 1), ("missing", 1),
                                        ("missing_codes", ["512480.SH"]), ("run_id", "other-run")])
def test_task_counts_and_real_task_identity_cannot_be_fabricated(closing_batch, field, value):
    result = {**PARTIAL, field: value}
    assert not local_compute.closed_session_result_accepted(accept(closing_batch, result=result))


def test_cli_does_not_trust_external_json_accepted_fields(tmp_path, monkeypatch, closing_batch):
    import importlib.util
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_local_compute.py"
    spec = importlib.util.spec_from_file_location("closed_quote_cli", path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    (tmp_path / ".local-live").touch()
    database = tmp_path / "research.sqlite3"; database.touch()
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"universe": ["510300.SH", "512480.SH"]}))
    forged = dict(accept(closing_batch)); forged.update(task_name="refresh_quotes", required=True)
    monkeypatch.setattr(cli, "get_current_git_sha", lambda: "b" * 40)
    monkeypatch.setattr(cli, "compute_local", lambda *args, **kwargs: [forged])
    monkeypatch.setattr(cli, "export_local_v2", lambda *args, **kwargs: pytest.fail("JSON cannot open closed-session gate"))
    args = SimpleNamespace(root=str(tmp_path), db=str(database), config=str(config), profile="live",
        provider="public_composite", expected_sha="b" * 40, private_research=True,
        closed_session_research=True, no_upload=True, skip_trade_day_check=True, board_only=False)
    assert cli.cmd_run(args) == 1


def _prepare_export_db(closing_batch):
    from app.models import DailyBar
    from app.services.decision_board_service import DecisionBoardService
    settings = Settings(_env_file=None, database_url=str(closing_batch.get_bind().url), market_provider="public_composite")
    for inst in closing_batch.query(Instrument):
        for days_back in range(25, -1, -1):
            day = datetime(2026, 10, 15, tzinfo=TZ).date() - timedelta(days=days_back)
            if day.weekday() < 5:
                closing_batch.add(DailyBar(instrument_id=inst.id, trade_date=day, adjust="none",
                    open=1.2, high=1.3, low=1.1, close=1.2, volume=1000, amount=1200,
                    source="tencent:stock_zh_a_hist_tx:v101", quality_hash="d" * 64))
    closing_batch.flush()
    DecisionBoardService(settings).refresh(closing_batch, generated_at=datetime(2026, 10, 15, 16, 11, tzinfo=TZ))
    closing_batch.commit()
    return settings


def test_validated_evidence_is_public_and_hash_bound_in_export(closing_batch):
    from app.workspace.local_display_contract import verify_bundle_integrity
    settings = _prepare_export_db(closing_batch)
    result = accept(closing_batch)
    bundle = local_compute.export_local_v2(settings, sequence=2, code_sha="b" * 40,
        universe=["510300.SH", "512480.SH"], private_research=True, closed_session_result=result,
        now=datetime(2026, 10, 15, 16, 12, tzinfo=TZ))
    assert bundle["manifest"]["input_observation"] == result["closed_session_research"]
    assert bundle["manifest"]["input_observation"]["is_realtime"] is False
    assert bundle["manifest"]["source_qualification"] == "UNKNOWN"
    assert verify_bundle_integrity(bundle)


def test_export_rejects_proof_transplant_to_another_database(closing_batch, tmp_path):
    import sqlite3
    _prepare_export_db(closing_batch)
    proof = accept(closing_batch)
    other = tmp_path / "other.sqlite3"
    with sqlite3.connect(closing_batch.get_bind().url.database) as source, sqlite3.connect(other) as target:
        source.backup(target)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{other.as_posix()}", market_provider="public_composite")
    with pytest.raises(ValueError, match="closed-session evidence"):
        local_compute.export_local_v2(settings, sequence=2, code_sha="b" * 40,
            universe=["510300.SH", "512480.SH"], private_research=True, closed_session_result=proof,
            now=datetime(2026, 10, 15, 16, 12, tzinfo=TZ))


@pytest.mark.parametrize("case", ["scope", "session", "captured_price", "task_status"])
def test_revalidation_rejects_changed_scope_session_or_captured_input(closing_batch, case):
    proof = accept(closing_batch)
    universe = ["510300.SH", "512480.SH"]
    now = datetime(2026, 10, 15, 16, 12, tzinfo=TZ)
    if case == "scope": universe = ["510300.SH"]
    elif case == "session": now += timedelta(days=1)
    elif case == "captured_price": closing_batch.query(QuoteSnapshot).first().price = 9.9
    else: closing_batch.query(TaskRun).first().status = "succeeded"
    closing_batch.flush()
    with pytest.raises(ValueError, match="closed-session evidence"):
        local_compute._revalidate_closed_session_capture(closing_batch,
            Settings(_env_file=None, market_provider="public_composite"), proof, universe, now)


def test_new_engine_on_same_sqlite_file_revalidates(closing_batch):
    proof = accept(closing_batch)
    closing_batch.commit()
    engine = create_engine(str(closing_batch.get_bind().url))
    try:
        with Session(engine) as db:
            captured = local_compute._revalidate_closed_session_capture(db,
                Settings(_env_file=None, market_provider="public_composite"), proof,
                ["510300.SH", "512480.SH"], datetime(2026, 10, 15, 16, 12, tzinfo=TZ))
            assert set(captured) == {"510300.SH", "512480.SH"}
    finally:
        engine.dispose()


def test_actual_quote_time_selector_must_choose_captured_batch(closing_batch):
    from sqlalchemy import update
    closing_batch.execute(update(QuoteSnapshot).values(id=QuoteSnapshot.id + 100))
    closing_batch.expunge_all()
    inst = closing_batch.query(Instrument).filter_by(ts_code="510300.SH").one()
    closing_batch.add(QuoteSnapshot(id=1, instrument_id=inst.id,
        quote_time=datetime(2026, 10, 15, 15, 50, tzinfo=TZ),
        fetched_at=datetime(2026, 10, 15, 16, 5, tzinfo=TZ), price=1.3,
        source="sina:hq_sinajs:v1", is_realtime=False, timestamp_verified=False,
        degraded_reason="quote source timestamp is stale", quality_hash="e" * 64))
    closing_batch.flush()
    proof = accept(closing_batch, after_id=100)
    assert local_compute.closed_session_result_accepted(proof)
    with pytest.raises(ValueError, match="closed-session evidence"):
        local_compute._revalidate_closed_session_capture(closing_batch,
            Settings(_env_file=None, market_provider="public_composite"), proof,
            ["510300.SH", "512480.SH"], datetime(2026, 10, 15, 16, 12, tzinfo=TZ))


def _move_capture_to_early_next_day(db):
    from app.services.market_service import MarketService
    start = datetime(2026, 10, 16, 0, 10, tzinfo=TZ)
    for quote in db.query(QuoteSnapshot):
        quote.fetched_at = start + timedelta(seconds=5)
        verified, reason = MarketService._qualify_quote_timestamp(SimpleNamespace(
            quote_time=quote.quote_time, is_realtime=True, source=quote.source, degraded_reason=None), quote.fetched_at)
        quote.timestamp_verified, quote.is_realtime, quote.degraded_reason = verified, verified, reason
        assert reason == "quote source date is not today"
    run = db.query(TaskRun).one()
    run.started_at, run.finished_at = start, start + timedelta(seconds=9)
    db.flush()
    return start


def test_before_open_accepts_verified_previous_session_with_current_fetch(closing_batch):
    start = _move_capture_to_early_next_day(closing_batch)
    result = accept(closing_batch, started_at=start, finished_at=start + timedelta(seconds=10))
    assert local_compute.closed_session_result_accepted(result)
    assert result["closed_session_research"]["source_session"] == "2026-10-15"
    assert local_compute._revalidate_closed_session_capture(closing_batch,
        Settings(_env_file=None, market_provider="public_composite"), result,
        ["510300.SH", "512480.SH"], start + timedelta(minutes=1))
    with pytest.raises(ValueError, match="closed-session evidence"):
        local_compute._revalidate_closed_session_capture(closing_batch,
            Settings(_env_file=None, market_provider="public_composite"), result,
            ["510300.SH", "512480.SH"], start.replace(hour=9, minute=0))


def test_previous_session_requires_every_calendar_decision_verified(closing_batch):
    start = _move_capture_to_early_next_day(closing_batch)
    calendar = SimpleNamespace(decision=lambda day: SimpleNamespace(verified=day.day != 15, is_trade_day=True))
    result = accept(closing_batch, started_at=start, finished_at=start + timedelta(seconds=10), calendar=calendar)
    assert not local_compute.closed_session_result_accepted(result)


def test_post_midnight_export_can_keep_previous_captured_session(closing_batch):
    proof = accept(closing_batch)
    assert local_compute._revalidate_closed_session_capture(closing_batch,
        Settings(_env_file=None, market_provider="public_composite"), proof,
        ["510300.SH", "512480.SH"], datetime(2026, 10, 16, 0, 5, tzinfo=TZ))


def test_reason_mapping_is_phase_specific_not_an_allowlist_pair(closing_batch):
    quote = closing_batch.query(QuoteSnapshot).first()
    quote.degraded_reason = "quote source date is not today"
    closing_batch.flush()
    assert not local_compute.closed_session_result_accepted(accept(closing_batch))
    start = _move_capture_to_early_next_day(closing_batch)
    quote.degraded_reason = "quote source timestamp is stale"
    closing_batch.flush()
    assert not local_compute.closed_session_result_accepted(accept(closing_batch,
        started_at=start, finished_at=start + timedelta(seconds=10)))


def test_before_open_still_rejects_a_session_older_than_verified_target(closing_batch):
    start = _move_capture_to_early_next_day(closing_batch)
    closing_batch.query(QuoteSnapshot).first().quote_time = datetime(2026, 10, 14, 15, 35, tzinfo=TZ)
    closing_batch.flush()
    assert not local_compute.closed_session_result_accepted(accept(closing_batch,
        started_at=start, finished_at=start + timedelta(seconds=10)))


def test_real_task_and_market_quote_ingestion_produce_accepted_previous_session_material(closing_batch, monkeypatch):
    from app.providers.types import QuoteRecord
    from app.services import market_service, task_service
    from app.services.execution_policy import TaskExecutionPolicy
    now = datetime(2026, 10, 16, 0, 10, 5, tzinfo=TZ)
    class FrozenMeta(type):
        def __instancecheck__(cls, value): return isinstance(value, datetime)
    class FrozenDatetime(datetime, metaclass=FrozenMeta):
        @classmethod
        def now(cls, tz=None): return now.astimezone(tz) if tz else now.replace(tzinfo=None)
    class FakePublicSina:
        name = "sina"
        def fetch_spot_quotes(self, codes):
            return [QuoteRecord(ts_code=code, quote_time=datetime(2026, 10, 15, 15, 35, tzinfo=TZ),
                price=1.2, source="sina:hq_sinajs:v1", is_realtime=True) for code in codes]
    monkeypatch.setattr(market_service, "datetime", FrozenDatetime)
    monkeypatch.setattr(task_service, "datetime", FrozenDatetime)
    closing_batch.commit()
    before = max(row.id for row in closing_batch.query(QuoteSnapshot))
    settings = Settings(_env_file=None, database_url=str(closing_batch.get_bind().url), market_provider="public_composite")
    service = task_service.TaskService(settings, provider=FakePublicSina(),
        execution_policy=TaskExecutionPolicy(resolve_runtime_provider=False))
    try:
        result = service.run(closing_batch, "refresh_quotes", codes=["510300.SH", "512480.SH"])
        assert result["status"] == "partial" and result["raw_realtime"] == 2 and result["realtime"] == 0
        proof = local_compute._closed_session_quote_result(closing_batch, settings,
            universe=["510300.SH", "512480.SH"], result=result, after_id=before,
            started_at=now - timedelta(seconds=5), finished_at=now + timedelta(seconds=5),
            private_research=True, enabled=True)
        assert local_compute.closed_session_result_accepted(proof)
        assert proof["closed_session_research"]["source_session"] == "2026-10-15"
        assert closing_batch.query(TaskRun).filter_by(run_id=result["run_id"]).one().status == "partial"
        assert all(row.degraded_reason == "quote source date is not today" and row.is_realtime is False
                   for row in closing_batch.query(QuoteSnapshot).filter(QuoteSnapshot.id > before))
    finally:
        service.close()
