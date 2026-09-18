"""Realtime quotes without a verifiable source timestamp are not operational-grade."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.market_service import MarketService
from app.workspace.refresh_policy import session_quote_window_open

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _item(**kwargs):
    payload = dict(
        source="tushare:rt_etf_k:v101",
        quote_time=datetime(2026, 8, 31, 14, 30, tzinfo=SHANGHAI),
        is_realtime=True,
        degraded_reason=None,
    )
    payload.update(kwargs)
    return SimpleNamespace(**payload)


def test_missing_source_timestamp_is_visible_not_operational():
    fetched = datetime(2026, 8, 31, 14, 31, tzinfo=SHANGHAI)
    verified, reason = MarketService._qualify_quote_timestamp(_item(quote_time=None), fetched)
    assert verified is False
    assert reason == "quote source timestamp missing"
    grade = MarketService.quote_operational_grade(verified, reason)
    assert grade["operational_grade"] is False
    assert grade["visible"] is True
    assert grade["production_qualified"] is False


def test_stale_source_timestamp_is_visible_not_operational():
    fetched = datetime(2026, 8, 31, 14, 55, tzinfo=SHANGHAI)
    stamp = fetched - timedelta(minutes=21)
    verified, reason = MarketService._qualify_quote_timestamp(_item(quote_time=stamp), fetched)
    assert verified is False
    assert reason == "quote source timestamp is stale"
    grade = MarketService.quote_operational_grade(verified, reason)
    assert grade["operational_grade"] is False
    assert grade["visible"] is True


def test_future_source_timestamp_is_not_operational():
    fetched = datetime(2026, 8, 31, 14, 30, tzinfo=SHANGHAI)
    stamp = fetched + timedelta(minutes=30)
    verified, reason = MarketService._qualify_quote_timestamp(_item(quote_time=stamp), fetched)
    assert verified is False
    assert reason == "quote source timestamp is in the future"
    assert MarketService.quote_operational_grade(verified, reason)["operational_grade"] is False


def test_tushare_realtime_inside_window_is_timestamp_verified_not_production_qualified():
    fetched = datetime(2026, 8, 31, 14, 32, tzinfo=SHANGHAI)
    stamp = datetime(2026, 8, 31, 14, 30, tzinfo=SHANGHAI)
    verified, reason = MarketService._qualify_quote_timestamp(_item(quote_time=stamp), fetched)
    assert verified is True
    assert reason is None
    grade = MarketService.quote_operational_grade(verified, reason)
    assert grade["operational_grade"] is True
    assert grade["production_qualified"] is False
    assert grade["visible"] is True


def test_em_quote_with_a_clock_is_still_not_provider_timestamp_qualified():
    fetched = datetime(2026, 8, 31, 14, 32, tzinfo=SHANGHAI)
    item = _item(source="akshare:em:v101", quote_time=fetched, is_realtime=False)
    verified, reason = MarketService._qualify_quote_timestamp(item, fetched)
    assert verified is False
    assert "provider qualification" in reason or "non-realtime" in reason
    assert MarketService.quote_operational_grade(verified, reason)["operational_grade"] is False


def test_scheduler_has_no_quote_session_on_non_trade_days():
    weekend = datetime(2026, 8, 30, 14, 30, tzinfo=SHANGHAI)
    assert session_quote_window_open(weekend, is_trade_day=False) is False
    lunch = datetime(2026, 8, 31, 12, 0, tzinfo=SHANGHAI)
    assert session_quote_window_open(lunch, is_trade_day=True) is False
