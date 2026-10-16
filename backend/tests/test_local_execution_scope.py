"""Target writes must not shrink cross-instrument research context."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.models import DailyBar, ForecastSnapshot, IndicatorSnapshot, Instrument, SignalSnapshot
from app.services.forecast_service import ForecastResult, ForecastService
from app.services.indicator_service import IndicatorService
from app.services.signal_service import CandidateSignal
from app.services.signal_v05_service import SignalV05Service
from app.utils.indicators import IndicatorResult

TARGET_DAY = date(2026, 10, 15)


@pytest.fixture
def pool(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr("app.services.settlement.settled_session", lambda *a, **k: TARGET_DAY)
    monkeypatch.setattr("app.providers.data_contract.history_issues", lambda *a, **k: {})
    monkeypatch.setattr("app.providers.corporate_action_contract.research_history_rows", lambda rows, code: rows)
    with Session(engine) as db:
        instruments = [Instrument(ts_code=f"{510000+i:06}.SH", symbol=str(510000+i), name="synthetic", enabled=True)
                       for i in range(52)]
        db.add_all(instruments); db.flush()
        yield db, instruments, [item.ts_code for item in instruments[:34]]
    engine.dispose()


def seed_history(db, instruments, *, outside_mode="stale"):
    for index, instrument in enumerate(instruments):
        if outside_mode == "missing" and index >= 34:
            continue
        end = TARGET_DAY if index < 34 or outside_mode == "fresh" else TARGET_DAY - timedelta(days=2)
        for offset in range(30):
            price = 1 + index / 100 + offset / 1000
            db.add(DailyBar(instrument_id=instrument.id, trade_date=end - timedelta(days=29-offset),
                open=price, high=price, low=price, close=price, volume=1000, amount=1000*price,
                adjust="qfq", source="synthetic", quality_hash=f"{index*100+offset:064x}"))
    db.flush()


def payloads(db, model):
    fields = (("values_json", "technical_score", "risk_score", "input_hash") if model is IndicatorSnapshot
              else ("p_up", "expected_return", "q10", "q50", "q90", "input_hash"))
    return {(row.instrument_id, getattr(row, "horizon", None)): tuple(getattr(row, field) for field in fields)
            for row in db.scalars(select(model)).all()}


@pytest.mark.parametrize("outside_mode", ["stale", "missing", "fresh"])
@pytest.mark.parametrize("kind", ["indicators", "forecasts"])
def test_target34_coverage_and_global_numeric_parity(pool, monkeypatch, kind, outside_mode):
    db, instruments, codes = pool
    seed_history(db, instruments, outside_mode=outside_mode)
    settings = Settings(_env_file=None, market_provider="public_composite")
    if kind == "indicators":
        def calculate(frame, cfg):
            value = float(frame.iloc[-1]["close"])
            return IndicatorResult(frame, {f"return_{n}d": value for n in (20, 60, 120)}, 60, 20, "synthetic", 100)
        monkeypatch.setattr("app.services.indicator_service.calculate_indicators", calculate)
        service, model = IndicatorService(settings), IndicatorSnapshot
    else:
        def build(raw, cfg):
            rich = raw.copy()
            for n in (20, 60, 120): rich[f"return_{n}d"] = rich["close"]
            return SimpleNamespace(frame=rich)
        monkeypatch.setattr("app.services.forecast_service.build_feature_frame", build)
        def predict(frame, horizon, **kwargs):
            value = float(frame.iloc[-1]["rps20"]) / 100
            return ForecastResult(horizon, value, value, value, value, value, 20, 20, 0.1, {})
        monkeypatch.setattr("app.services.forecast_service.similarity_forecast", predict)
        service, model = ForecastService(settings), ForecastSnapshot
        service.strategy["forecast"]["min_history"] = 30
        service.strategy["forecast"]["horizons"] = [1]
    global_result = service.refresh_all(db)
    before = payloads(db, model)
    # Detect even an equal-sized outside update, not just extra inserted rows.
    for row in db.scalars(select(model).where(model.instrument_id.in_([item.id for item in instruments[34:]]))):
        row.input_hash = "outside-sentinel"
    db.flush()
    outside_before = {key: value for key, value in payloads(db, model).items() if key[0] > 34}
    result = service.refresh_all(db, codes=codes)
    after = payloads(db, model)
    assert result["requested"] == result["completed"] == 34
    assert result["status"] == "succeeded" and result["stale_count"] == 0 and result["failures"] == []
    assert {key: value for key, value in after.items() if key[0] <= 34} == {
        key: value for key, value in before.items() if key[0] <= 34}
    assert {key: value for key, value in after.items() if key[0] > 34} == outside_before
    assert len(instruments) == 52 and all(item.enabled for item in instruments)
    assert global_result["requested"] == 52
    assert (global_result["status"] == "succeeded") is (outside_mode == "fresh")
    assert result["execution_scope"]["background_count"] == 52
    assert result["execution_scope"]["target_codes"] == codes


@pytest.mark.parametrize("kind", ["indicators", "forecasts"])
def test_missing_required_target_stays_incomplete(pool, kind):
    db, _, codes = pool
    service = (IndicatorService if kind == "indicators" else ForecastService)(
        Settings(_env_file=None, market_provider="public_composite"))
    result = service.refresh_all(db, codes=codes)
    assert result["requested"] == 34 and result["completed"] == 0
    assert result["status"] == "failed" and len(result["failures"]) == 34


def test_signals_keep_all_candidates_and_portfolio_context_but_write_only_target(pool, monkeypatch):
    db, instruments, codes = pool
    service = SignalV05Service(Settings(_env_file=None, market_provider="mock"))
    seen = []
    def regime(all_instruments, indicators):
        seen.append(len(all_instruments))
        return "synthetic", 0.6, {"background_count": len(all_instruments)}
    monkeypatch.setattr(service, "_market_regime", regime)
    monkeypatch.setattr(service, "_apply_state_hysteresis", lambda *a: None)
    def candidate(db, instrument, quote, indicator, forecasts, holding, weight, now):
        return CandidateSignal(instrument, None, None, {}, None, 0, 75, 30, 100,
                               [], [], 50, 50, 0.14)
    monkeypatch.setattr(service, "_build_candidate", candidate)
    service.refresh_all(db)
    def values():
        return [(row.instrument_id, row.target_weight, row.first_step_target_weight, row.input_hash, row.evidence_json)
                for row in db.scalars(select(SignalSnapshot).order_by(SignalSnapshot.id)).all()]
    before = values()
    result = service.refresh_all(db, codes=codes)
    after = values()
    assert seen == [52, 52]
    assert after[:52] == before and len(after) == 86
    assert after[52:] == before[:34]
    assert result["created"] == result["requested"] == result["completed"] == 34


@pytest.mark.parametrize("service_cls", [IndicatorService, ForecastService, SignalV05Service])
@pytest.mark.parametrize("codes", [[], ["UNKNOWN.SH"], ["510000.SH", "510000.SH"]])
def test_invalid_explicit_target_does_not_mean_all(pool, service_cls, codes):
    db, _, _ = pool
    with pytest.raises(ValueError, match="execution_scope"):
        service_cls(Settings(_env_file=None, market_provider="mock")).refresh_all(db, codes=codes)


@pytest.mark.parametrize("task_name,attribute", [("refresh_indicators", "indicators"),
    ("refresh_forecasts", "forecasts"), ("refresh_signals", "signals")])
def test_task_forwards_scope_only_when_requested(task_name, attribute):
    from app.services.task_service import TaskService
    service = TaskService.__new__(TaskService)
    calls = []
    setattr(service, attribute, SimpleNamespace(refresh_all=lambda db, **kw: calls.append(kw) or {}))
    service._bind_runtime_provider = lambda db: None
    service._execute(None, task_name, "test")
    service._execute(None, task_name, "test", codes=["510300.SH"])
    assert calls == [{"run_id": "test"}, {"run_id": "test", "codes": ["510300.SH"]}]


@pytest.mark.parametrize("task_name", ["bootstrap", "full_pipeline"])
@pytest.mark.parametrize("codes", [[], ["510300.SH"]])
def test_composite_scoped_request_rejected_before_provider_or_database_access(task_name, codes):
    from app.services.task_service import TaskService
    service = TaskService.__new__(TaskService)  # No settings/provider/DB available to accidentally access.
    with pytest.raises(ValueError, match="execution_scope_composite_task_unsupported"):
        service.run(None, task_name, codes=codes)


def test_local_producer_limits_target_tasks_without_shrinking_global_optional_context(monkeypatch, tmp_path):
    from app.workspace.local_compute import compute_local
    calls = {}
    class StubTasks:
        def __init__(self, *a, **kw): pass
        def run(self, db, task, **kwargs):
            calls[task] = kwargs
            return {"status": "succeeded"}
        def close(self): pass
    monkeypatch.setattr("app.services.task_service.TaskService", StubTasks)
    engine = create_engine(f"sqlite:///{(tmp_path / 'research.sqlite3').as_posix()}")
    try:
        Base.metadata.create_all(engine)
        compute_local(Settings(_env_file=None, database_url=str(engine.url), market_provider="mock"), ["510300.SH"])
    finally:
        engine.dispose()
    for task in ("refresh_market_context", "refresh_sector_snapshots"):
        assert "codes" not in calls[task]
    for task in ("refresh_bars", "refresh_quotes", "refresh_indicators", "refresh_forecasts", "refresh_signals",
                 "refresh_decision_board"):
        assert calls[task]["codes"] == ["510300.SH"]


def test_board_captures_target_only_and_keeps_full_payload_background(pool, monkeypatch):
    from app.services.decision_board_service import DecisionBoardService
    db, instruments, codes = pool
    service = DecisionBoardService(Settings(_env_file=None, market_provider="mock"))
    captured = []
    monkeypatch.setattr(service.support_resistance, "capture_for_instruments",
        lambda db, targets, **kw: captured.extend(item.ts_code for item in targets))
    all_codes = [item.ts_code for item in instruments]
    monkeypatch.setattr(service, "_build_payload", lambda db, now: {
        "snapshot_id": "synthetic-scoped-board", "freshness": "degraded",
        "rows": [{"ts_code": code} for code in all_codes], "sector_timing": {"background_count": 52}})
    monkeypatch.setattr(service, "_prune_snapshot_dates", lambda db: None)
    built = service.refresh(db, codes=codes)
    assert captured == codes
    assert [row["ts_code"] for row in built.payload["rows"]] == all_codes
    assert built.payload["sector_timing"]["background_count"] == 52
    assert built.payload["execution_scope"]["target_count"] == 34


def test_scoped_completion_does_not_certify_global_pool(pool):
    from app.services.execution_scope import scope_metadata
    from app.services.settlement import output_scope_hash, stamp_output_completion
    db, instruments, codes = pool
    settings = Settings(_env_file=None, market_provider="mock")
    now = datetime.now(settings.timezone)
    result = {"status": "succeeded", "created": 34, **scope_metadata(instruments, codes)}
    stamped = stamp_output_completion(db, settings, "refresh_signals", result, now, codes=codes)
    assert stamped["coverage_complete"] is True
    assert stamped["output_scope_hash"] != output_scope_hash(db, settings)
    ordinary = stamp_output_completion(db, settings, "refresh_signals", {"status": "succeeded", "created": 52}, now)
    assert ordinary["output_scope_hash"] == output_scope_hash(db, settings)
    for changed in ({"status": "succeeded", "created": 34},
                    {**result, "execution_scope": {**result["execution_scope"], "background_count": 34}},
                    {**result, "execution_scope": {**result["execution_scope"], "version": "unknown"}}):
        with pytest.raises(ValueError, match="execution_scope"):
            stamp_output_completion(db, settings, "refresh_signals", changed, now, codes=codes)
    with pytest.raises(ValueError, match="execution_scope"):
        stamp_output_completion(db, settings, "refresh_signals", result, now, codes=[instruments[-1].ts_code])
    with pytest.raises(ValueError, match="execution_scope"):
        stamp_output_completion(db, settings, "refresh_signals", result, now)
