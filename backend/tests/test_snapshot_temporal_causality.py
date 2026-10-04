from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.models import (
    ForecastSnapshot,
    Holding,
    IndicatorSnapshot,
    Instrument,
    QuoteSnapshot,
    SignalSnapshot,
)
from app.services.dashboard_service import DashboardService
from app.services.etf_1430_service import ETF1430WorkbenchService
from app.services.holding_service import HoldingService
from app.services.kline_stabilization_service import KlineStabilizationService
from app.services.portfolio_optimization_service import PortfolioOptimizationService
from app.services.signal_grade_service import SignalGradeService
from app.services.signal_service import SignalService
from app.services.snapshot_contract import (
    SIGNAL_INPUT_CONTRACT_VERSION,
    quote_issues,
    signal_issues,
    snapshot_issues,
)
from app.utils.hashing import stable_hash
from app.utils.latest_snapshots import latest_forecast_map


def _runtime():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _instrument(db):
    inst = Instrument(
        ts_code="999882.SH",
        symbol="999882",
        name="temporal-contract",
        kind="ETF",
        enabled=True,
    )
    db.add(inst)
    db.flush()
    return inst


def _current_indicator(db, inst, *, day: date, generated_at: datetime):
    strategy = get_settings().load_strategy()
    row = IndicatorSnapshot(
        instrument_id=inst.id,
        as_of_date=day,
        version=strategy["indicator_version"],
        feature_schema_version=strategy["feature_schema_version"],
        config_hash=stable_hash(strategy),
        values_json={"close": 1.0, "rsi14": 55.0},
        technical_score=60.0,
        risk_score=40.0,
        trend_label="fixture",
        data_quality=90.0,
        input_hash="a" * 64,
        generated_at=generated_at,
    )
    db.add(row)
    db.flush()
    return row


def _current_forecast(db, inst, *, day: date, generated_at: datetime):
    strategy = get_settings().load_strategy()
    row = ForecastSnapshot(
        instrument_id=inst.id,
        as_of_date=day,
        horizon=1,
        model_version=strategy["forecast_version"],
        feature_schema_version=strategy["feature_schema_version"],
        config_hash=stable_hash(strategy),
        input_hash="b" * 64,
        p_up=0.55,
        expected_return=0.01,
        confidence=20.0,
        calibration_status="not_calibrated",
        generated_at=generated_at,
    )
    db.add(row)
    db.flush()
    return row


def _future_quote(db, inst, when):
    row = QuoteSnapshot(
        instrument_id=inst.id,
        quote_time=when,
        fetched_at=when,
        timestamp_verified=True,
        price=9.9,
        pct_change=1.0,
        source="fixture",
        is_realtime=True,
        quality_hash="c" * 64,
    )
    db.add(row)
    db.flush()
    return row


def test_future_indicator_forecast_and_signal_are_not_current_evidence():
    engine, db = _runtime()
    try:
        inst = _instrument(db)
        settings = get_settings()
        now = datetime.now(settings.timezone)
        future = now + timedelta(hours=2)
        indicator = _current_indicator(
            db, inst, day=(now + timedelta(days=1)).date(), generated_at=future
        )
        forecast = _current_forecast(
            db, inst, day=(now + timedelta(days=1)).date(), generated_at=future
        )
        assert "indicator_from_future" in snapshot_issues(
            indicator, settings, None, kind="indicator", at=now
        )
        assert "indicator_generated_in_future" in snapshot_issues(
            indicator, settings, None, kind="indicator", at=now
        )
        assert "forecast_from_future" in snapshot_issues(
            forecast, settings, None, kind="forecast", at=now
        )
        assert inst.id not in latest_forecast_map(
            db, [inst.id], settings=settings, at=now
        )
        assert inst.id not in SignalGradeService(settings)._latest_indicators(
            db, as_of=now
        )

        strategy = settings.load_strategy()
        snapshot_inputs = {
            "contract_version": SIGNAL_INPUT_CONTRACT_VERSION,
            "formal_forecast_horizons": [1, 3, 5, 10],
            "forecast_score_horizon_weights": {"1": 0.5, "5": 0.3},
            "quote_input_hash": None,
            "indicator": None,
            "forecasts": {},
        }
        signal = SignalSnapshot(
            instrument_id=inst.id,
            as_of_time=future,
            strategy_version=strategy["version"],
            indicator_version=strategy["indicator_version"],
            forecast_version=strategy["forecast_version"],
            state="观察",
            score=50,
            confidence=20,
            target_weight=0,
            first_step_target_weight=0,
            reasons_json=[],
            risks_json=[],
            evidence_json={"snapshot_inputs": snapshot_inputs},
            input_hash=stable_hash(
                {"snapshot_inputs": snapshot_inputs, "strategy": strategy}
            ),
            expires_at=future + timedelta(hours=1),
            is_actionable=False,
            data_quality=0,
        )
        db.add(signal)
        db.flush()
        assert "signal_from_future" in signal_issues(signal, settings, at=now)
    finally:
        db.close()
        engine.dispose()


def test_future_quote_is_rejected_across_current_surfaces_and_never_used_for_holding_pnl():
    engine, db = _runtime()
    try:
        inst = _instrument(db)
        settings = get_settings()
        now = datetime.now(settings.timezone)
        quote = _future_quote(db, inst, now + timedelta(hours=1))
        assert "quote_from_future" in quote_issues(quote, settings, at=now)

        db.add(
            Holding(
                user_id=None,
                instrument_id=inst.id,
                shares=Decimal("100"),
                cost_price=Decimal("2.0"),
            )
        )
        db.flush()

        holding = HoldingService(settings).list(db)[0]
        assert holding["latest_price"] is None
        assert holding["market_value"] is None
        assert holding["pnl"] is None
        assert holding["pnl_pct"] is None
        assert holding["current_weight"] is None
        assert holding["pricing_complete"] is False
        assert "quote_from_future" in holding["quote_issues"]

        dashboard = DashboardService(settings).instrument_rows(db)[0]
        assert dashboard["quote"] is None
        assert "quote_from_future" in dashboard["snapshot_compatibility"]["quote"]

        assert inst.id not in SignalGradeService(settings)._latest_quotes(db, as_of=now)
        assert KlineStabilizationService(settings)._latest_quote(
            db, inst.id, at=now
        ) is None
        assert PortfolioOptimizationService(settings)._latest_quote(
            db, inst.id, at=now
        ) is None
    finally:
        db.close()
        engine.dispose()


def test_signal_refresh_does_not_wrap_future_snapshots_or_quote_as_current_inputs():
    engine, db = _runtime()
    try:
        inst = _instrument(db)
        settings = get_settings()
        now = datetime.now(settings.timezone)
        future = now + timedelta(hours=1)
        _future_quote(db, inst, future)
        _current_indicator(
            db, inst, day=(now + timedelta(days=1)).date(), generated_at=future
        )
        _current_forecast(
            db, inst, day=(now + timedelta(days=1)).date(), generated_at=future
        )

        result = SignalService(settings).refresh_all(
            db, run_id="future-snapshot-contract"
        )
        assert result["created"] == 1
        signal = db.scalar(
            select(SignalSnapshot)
            .where(SignalSnapshot.instrument_id == inst.id)
            .order_by(SignalSnapshot.id.desc())
            .limit(1)
        )
        assert signal is not None
        inputs = signal.evidence_json["snapshot_inputs"]
        assert inputs["quote_input_hash"] is None
        assert inputs["indicator"] is None
        assert inputs["forecasts"] == {}
        assert signal.is_actionable is False
        assert signal_issues(signal, settings, at=signal.as_of_time) == []
    finally:
        db.close()
        engine.dispose()


def test_1430_forecast_reader_rejects_future_current_version_snapshot():
    engine, db = _runtime()
    try:
        inst = _instrument(db)
        settings = get_settings()
        now = datetime.now(settings.timezone)
        _current_forecast(
            db, inst, day=(now + timedelta(days=1)).date(),
            generated_at=now + timedelta(hours=1),
        )
        assert ETF1430WorkbenchService(settings)._latest_forecasts(
            db, inst.id, at=now
        ) == {}
    finally:
        db.close()
        engine.dispose()
