"""Offline explicit Mock ingestion date, independent temporary SQLite only."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from app.core.config import Settings
from app.db.base import Base
from app.models import DailyBar, Instrument
from app.providers.mock import MockProvider
from app.services.market_service import MarketService
from app.services.trading_calendar_service import TradingCalendarService, TradingDayDecision
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

FRIDAY = date(2026, 10, 9)

@pytest.fixture
def isolated_market(tmp_path, monkeypatch):
    import app.services.market_service as module
    class Sunday(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 11, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(tz)
    monkeypatch.setattr(module, "datetime", Sunday)
    settings = Settings(_env_file=None, app_env="test", market_provider="mock", database_url="sqlite://")
    engine = create_engine("sqlite:///" + (tmp_path / "mock-date.sqlite3").as_posix())
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Instrument(ts_code="510300.SH", symbol="510300", name="fixture", kind="ETF", enabled=True))
        db.commit()
        yield MarketService(MockProvider(), settings), db
    engine.dispose()

def test_sunday_default_stays_failed_but_explicit_settled_date_is_complete(isolated_market):
    service, db = isolated_market
    original = service.refresh_daily_bars(db, lookback_days=120)
    assert original["status"] == "failed"
    assert original["target_trade_date"] == "2026-10-11"
    result = service.refresh_daily_bars(db, lookback_days=120, mock_settled_date=FRIDAY)
    assert result["status"] == "succeeded"
    assert result["target_trade_date"] == FRIDAY.isoformat()
    assert result["coverage"][0]["complete"] is True
    assert db.scalar(select(DailyBar.trade_date).order_by(DailyBar.trade_date.desc()).limit(1)) == FRIDAY

@pytest.mark.parametrize("day", [date(2026, 10, 12), date(2026, 10, 11), "2026-10-09"])
def test_future_non_session_and_non_date_overrides_rejected(isolated_market, day):
    service, db = isolated_market
    with pytest.raises(ValueError, match="mock_settled_date"):
        service.refresh_daily_bars(db, mock_settled_date=day)

def test_unverified_calendar_override_rejected(isolated_market, monkeypatch):
    service, db = isolated_market
    monkeypatch.setattr(TradingCalendarService, "decision", lambda _self, day: TradingDayDecision(day, True, False, "fallback"))
    with pytest.raises(ValueError, match="mock_settled_date"):
        service.refresh_daily_bars(db, mock_settled_date=FRIDAY)

def test_real_provider_override_rejected_before_any_fetch(isolated_market):
    service, db = isolated_market
    service.settings = service.settings.model_copy(update={"market_provider": "composite"})
    with pytest.raises(ValueError, match="mock_settled_date"):
        service.refresh_daily_bars(db, mock_settled_date=FRIDAY)

def test_refresh_task_forwards_only_explicit_mock_override():
    from types import SimpleNamespace

    from app.services.task_service import TaskService
    calls = []
    service = SimpleNamespace(
        _bind_runtime_provider=lambda *_args: None,
        _ensure_instruments=lambda *_args: None,
        market=SimpleNamespace(refresh_daily_bars=lambda *_args, **kwargs: calls.append(kwargs) or {"status": "succeeded"}),
    )
    TaskService._execute(service, None, "refresh_bars", "fixture-run", mock_settled_date=FRIDAY)
    assert calls[-1]["mock_settled_date"] == FRIDAY
    TaskService._execute(service, None, "refresh_bars", "fixture-run")
    assert "mock_settled_date" not in calls[-1]
