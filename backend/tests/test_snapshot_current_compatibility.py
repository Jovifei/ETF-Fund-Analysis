from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.models import (
    ForecastSnapshot,
    IndicatorSnapshot,
    Instrument,
    SignalSnapshot,
)
from app.services.dashboard_service import DashboardService
from app.services.kline_stabilization_service import KlineStabilizationService
from app.services.portfolio_optimization_service import PortfolioOptimizationService
from app.services.preflight_service import PreflightService
from app.services.signal_grade_service import SignalGradeService
from app.services.signal_service import SignalService
from app.services.snapshot_contract import (
    SIGNAL_INPUT_CONTRACT_VERSION,
    current_signal,
    signal_issues,
    snapshot_issues,
)
from app.utils.hashing import stable_hash
from app.utils.latest_snapshots import latest_forecast_map, latest_signal_map


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _instrument(db):
    inst = Instrument(
        ts_code="999881.SH",
        symbol="999881",
        name="snapshot-contract",
        kind="ETF",
        enabled=True,
    )
    db.add(inst)
    db.flush()
    return inst


def _indicator(db, inst, day, *, current: bool, marker: str):
    strategy = get_settings().load_strategy()
    row = IndicatorSnapshot(
        instrument_id=inst.id,
        as_of_date=day,
        version=strategy["indicator_version"] if current else "old-indicator",
        feature_schema_version=strategy["feature_schema_version"] if current else "old-schema",
        config_hash=stable_hash(strategy) if current else "0" * 64,
        values_json={"close": 1.0, "rsi14": 55.0, "return_5d": 0.01},
        technical_score=60.0,
        risk_score=40.0,
        trend_label=marker,
        data_quality=90.0,
        input_hash=(marker[0] * 64),
    )
    db.add(row)
    db.flush()
    return row


def _forecast(db, inst, day, *, current: bool, marker: str, horizon: int = 1):
    strategy = get_settings().load_strategy()
    row = ForecastSnapshot(
        instrument_id=inst.id,
        as_of_date=day,
        horizon=horizon,
        model_version=strategy["forecast_version"] if current else "old-forecast",
        feature_schema_version=strategy["feature_schema_version"] if current else "old-schema",
        config_hash=stable_hash(strategy) if current else "1" * 64,
        input_hash=(marker[0] * 64),
        p_up=0.55,
        expected_return=0.01,
        confidence=20.0,
        calibration_status="not_calibrated",
    )
    db.add(row)
    db.flush()
    return row


def _signal(db, inst, when, *, current: bool, expires: datetime | None = None):
    settings = get_settings()
    strategy = settings.load_strategy()
    snapshot_inputs = {
        "contract_version": SIGNAL_INPUT_CONTRACT_VERSION,
        "formal_forecast_horizons": [int(v) for v in strategy["forecast"]["horizons"]],
        "forecast_score_horizon_weights": {"1": 0.5, "5": 0.3},
        "quote_input_hash": None,
        "indicator": None,
        "forecasts": {},
    }
    row = SignalSnapshot(
        instrument_id=inst.id,
        as_of_time=when,
        strategy_version=strategy["version"] if current else "old-signal",
        indicator_version=strategy["indicator_version"] if current else "old-indicator",
        forecast_version=strategy["forecast_version"] if current else "old-forecast",
        state="观察",
        score=50.0,
        confidence=20.0,
        target_weight=0.0,
        first_step_target_weight=0.0,
        reasons_json=[],
        risks_json=[],
        evidence_json={"snapshot_inputs": snapshot_inputs} if current else {},
        input_hash=(
            stable_hash({"snapshot_inputs": snapshot_inputs, "strategy": strategy})
            if current
            else "2" * 64
        ),
        expires_at=expires or when + timedelta(hours=2),
        is_actionable=False,
        data_quality=0.0,
    )
    db.add(row)
    db.flush()
    return row


def test_latest_current_contract_never_falls_back_to_older_compatible_snapshot():
    engine, db = _db()
    try:
        inst = _instrument(db)
        old_day = date(2026, 9, 1)
        new_day = date(2026, 9, 2)
        compatible = _forecast(db, inst, old_day, current=True, marker="a")
        incompatible = _forecast(db, inst, new_day, current=False, marker="b")

        raw = latest_forecast_map(db, [inst.id])
        assert raw[inst.id][1].id == incompatible.id
        current = latest_forecast_map(db, [inst.id], settings=get_settings())
        assert inst.id not in current
        assert "forecast_version_mismatch" in snapshot_issues(
            incompatible, get_settings(), None, kind="forecast"
        )
        assert compatible.id != incompatible.id
    finally:
        db.close()
        engine.dispose()


def test_latest_signal_contract_rejects_stale_version_and_expired_rows_without_fallback():
    engine, db = _db()
    try:
        inst = _instrument(db)
        tz = ZoneInfo("Asia/Shanghai")
        now = datetime(2026, 10, 4, 14, 0, tzinfo=tz)
        compatible = _signal(db, inst, now - timedelta(minutes=20), current=True, expires=now + timedelta(minutes=20))
        incompatible = _signal(db, inst, now - timedelta(minutes=5), current=False, expires=now + timedelta(hours=1))

        raw = latest_signal_map(db, [inst.id])
        assert raw[inst.id].id == incompatible.id
        current = latest_signal_map(db, [inst.id], settings=get_settings(), at=now)
        assert inst.id not in current
        assert current_signal(compatible, get_settings(), at=now) is compatible

        expired = _signal(db, inst, now + timedelta(minutes=1), current=True, expires=now)
        assert "signal_expired" in signal_issues(expired, get_settings(), at=now)
    finally:
        db.close()
        engine.dispose()


def test_current_surfaces_reject_latest_incompatible_indicator_instead_of_using_older_current():
    engine, db = _db()
    try:
        inst = _instrument(db)
        compatible = _indicator(db, inst, date(2026, 9, 1), current=True, marker="c")
        incompatible = _indicator(db, inst, date(2026, 9, 2), current=False, marker="d")
        assert compatible.id != incompatible.id

        rows = DashboardService().instrument_rows(db)
        row = next(item for item in rows if item["ts_code"] == inst.ts_code)
        assert row["indicator"] is None
        assert "indicator_version_mismatch" in row["snapshot_compatibility"]["indicator"]

        assert inst.id not in SignalGradeService()._latest_indicators(db)

        values, previous, issues = KlineStabilizationService()._latest_indicator_values(db, inst.id)
        assert values == {} and previous == {}
        assert "indicator_version_mismatch" in issues

        frame, issue_map = PortfolioOptimizationService()._build_snapshot_frame(db, [inst])
        assert inst.id not in frame
        assert "indicator_version_mismatch" in issue_map[inst.id]
    finally:
        db.close()
        engine.dispose()


def test_signal_refresh_does_not_relabel_incompatible_inputs_as_current_provenance():
    engine, db = _db()
    try:
        inst = _instrument(db)
        today = datetime.now(get_settings().timezone).date()
        _indicator(db, inst, today - timedelta(days=1), current=True, marker="e")
        _indicator(db, inst, today, current=False, marker="f")
        _forecast(db, inst, today - timedelta(days=1), current=True, marker="g", horizon=1)
        _forecast(db, inst, today, current=False, marker="h", horizon=1)

        result = SignalService().refresh_all(db, run_id="snapshot-contract-refresh")
        assert result["created"] == 1
        row = db.scalar(
            select(SignalSnapshot)
            .where(SignalSnapshot.instrument_id == inst.id)
            .order_by(SignalSnapshot.id.desc())
            .limit(1)
        )
        assert row is not None
        inputs = row.evidence_json["snapshot_inputs"]
        assert inputs["indicator"] is None
        assert inputs["forecasts"] == {}
        assert inputs["formal_forecast_horizons"] == [1, 3, 5, 10]
        assert inputs["forecast_score_horizon_weights"] == {"1": 0.5, "5": 0.3}
        assert signal_issues(row, get_settings(), at=row.as_of_time) == []
        assert row.is_actionable is False
    finally:
        db.close()
        engine.dispose()


def test_preflight_formal_forecast_contract_is_1_3_5_10_not_research_outlook_20():
    engine, db = _db()
    try:
        inst = _instrument(db)
        result = PreflightService().check_instrument(
            db,
            inst,
            at=datetime.now(get_settings().timezone),
        )
        missing = set(result.missing_optional)
        assert {"1日预测", "3日预测", "5日预测", "10日预测"}.issubset(missing)
        assert "20日预测" not in missing
    finally:
        db.close()
        engine.dispose()
