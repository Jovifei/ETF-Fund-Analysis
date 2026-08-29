from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, func, select

from app.models import DailyBar, Instrument
from app.providers.factory import build_provider
from app.services.market_service import MarketService


def test_refresh_daily_bars_backfills_when_lookback_exceeds_stored_history(bootstrapped, db_session):
    instrument = db_session.scalar(select(Instrument).where(Instrument.ts_code == "510300.SH"))
    assert instrument is not None

    cutoff = date.today() - timedelta(days=200)
    db_session.execute(
        delete(DailyBar).where(
            DailyBar.instrument_id == instrument.id,
            DailyBar.trade_date < cutoff,
        )
    )
    db_session.flush()

    count_before = db_session.scalar(
        select(func.count()).select_from(DailyBar).where(DailyBar.instrument_id == instrument.id)
    )
    assert count_before is not None and count_before < 160

    service = MarketService(build_provider())
    result = service.refresh_daily_bars(db_session, lookback_days=900, codes=["510300.SH"])
    db_session.flush()

    count_after = db_session.scalar(
        select(func.count()).select_from(DailyBar).where(DailyBar.instrument_id == instrument.id)
    )
    assert result["inserted"] > 0
    assert count_after is not None and count_after > count_before


def test_refresh_daily_bars_uses_short_overlap_when_history_covers_lookback(bootstrapped, db_session):
    instrument = db_session.scalar(select(Instrument).where(Instrument.ts_code == "510300.SH"))
    assert instrument is not None

    service = MarketService(build_provider())
    first = service.refresh_daily_bars(db_session, lookback_days=420, codes=["510300.SH"])
    db_session.flush()
    count_after_first = db_session.scalar(
        select(func.count()).select_from(DailyBar).where(DailyBar.instrument_id == instrument.id)
    )

    second = service.refresh_daily_bars(db_session, lookback_days=420, codes=["510300.SH"])
    db_session.flush()
    count_after_second = db_session.scalar(
        select(func.count()).select_from(DailyBar).where(DailyBar.instrument_id == instrument.id)
    )

    assert count_after_first is not None and count_after_first > 200
    assert second["inserted"] == 0
    assert count_after_second == count_after_first
