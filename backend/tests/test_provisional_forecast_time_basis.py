from __future__ import annotations

import inspect
from datetime import datetime, time, timedelta

from sqlalchemy import func, select

from app.core.config import PROJECT_ROOT
from app.models import DailyBar, ForecastSnapshot, Instrument
from app.services.decision_board_service import DecisionBoardService
from app.services.etf_1430_service import ETF1430WorkbenchService
from app.services.kline_stabilization_service import KlineStabilizationService


FORECAST_PROVENANCE_FIELDS = {
    "source",
    "feature_basis",
    "as_of_date",
    "intraday_provisional_used",
}


def _assert_settled_daily_forecasts(items: list[dict]) -> None:
    assert items
    for item in items:
        assert FORECAST_PROVENANCE_FIELDS <= set(item)
        assert item["source"] == "persisted_forecast_snapshot"
        assert item["feature_basis"] == "settled_daily_bars"
        assert item["intraday_provisional_used"] is False
        assert item["as_of_date"]


def test_provisional_ohlcv_can_update_research_indicators_but_not_eod_neighbor_forecast(
    db_session, bootstrapped
) -> None:
    instrument = db_session.scalar(select(Instrument).where(Instrument.ts_code == "510300.SH"))
    assert instrument is not None
    stored = db_session.scalar(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.instrument_id == instrument.id, ForecastSnapshot.horizon == 1)
        .order_by(ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc())
        .limit(1)
    )
    assert stored is not None
    latest_bar_date = db_session.scalar(
        select(func.max(DailyBar.trade_date)).where(DailyBar.instrument_id == instrument.id)
    )
    assert latest_bar_date is not None
    observed_at = datetime.combine(
        latest_bar_date + timedelta(days=1),
        time(14, 30),
        tzinfo=DecisionBoardService().settings.timezone,
    )

    service = DecisionBoardService()
    service.record_provisional_input(
        db_session,
        ts_code=instrument.ts_code,
        observed_at=observed_at,
        source="time-basis-test",
        timestamp_verified=True,
        open_price=3.0,
        high_price=3.2,
        low_price=2.9,
        last_price=3.1,
        volume=1_000_000.0,
        amount=3_100_000.0,
        pct_change_percent_points=0.25,
    )
    payload = service.refresh(db_session, generated_at=observed_at + timedelta(minutes=5)).payload
    row = next(item for item in payload["rows"] if item["ts_code"] == instrument.ts_code)

    assert row["provisional"]["used_for_derived_values"] is True
    assert row["provisional"]["forecast_policy"] == "persisted_settled_daily_only"
    assert row["provisional"]["forecast_policy_reason"] == "no_time_matched_intraday_neighbor_history"
    assert "forecasts" not in row["provisional"]["derived"]

    forecast = row["forecasts"]["1"]
    _assert_settled_daily_forecasts([forecast])
    assert forecast["as_of_date"] == stored.as_of_date.isoformat()
    assert forecast["expected_return"] == stored.expected_return
    assert forecast["p_up"] == stored.p_up
    assert payload["indicator_status"]["intraday_forecast_policy"] == "disabled_until_time_matched_intraday_history"


def test_provisional_derivation_has_no_similarity_forecast_call() -> None:
    source = inspect.getsource(DecisionBoardService._derive_provisional)
    assert "similarity_forecast" not in source
    assert "build_feature_frame" not in source
    assert "feature_columns_for_horizon" not in source


def test_all_forecast_surfaces_expose_settled_daily_basis(db_session, bootstrapped) -> None:
    board = DecisionBoardService().refresh(db_session).payload
    board_forecasts = [
        forecast
        for row in board["rows"]
        for forecast in row["forecasts"].values()
        if forecast["source"] == "persisted_forecast_snapshot"
    ]
    _assert_settled_daily_forecasts(board_forecasts)

    etf_rows = ETF1430WorkbenchService().summary(db_session)["rows"]
    etf_forecasts = [
        forecast
        for row in etf_rows
        for forecast in row["forecasts"].values()
        if forecast["source"] == "persisted_forecast_snapshot"
    ]
    _assert_settled_daily_forecasts(etf_forecasts)

    kline_rows = KlineStabilizationService().summary(db_session)["rows"]
    kline_forecasts = [
        row["forecast"]
        for row in kline_rows
        if row["forecast"]["source"] == "persisted_forecast_snapshot"
    ]
    _assert_settled_daily_forecasts(kline_forecasts)


def test_unified_page_and_readme_explain_forecast_time_basis() -> None:
    source = (PROJECT_ROOT / "backend" / "app" / "static" / "decision_board_workbuddy.js").read_text(
        encoding="utf-8"
    )
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "日线基准至" in source
    assert "feature_basis==='settled_daily_bars'" in source
    assert "14:30 盘中 quote/OHLCV" in readme
    assert "禁止用当前 14:30 状态直接匹配历史收盘状态冒充盘中预测" in readme
