from datetime import date

from app.services.trading_calendar_service import TradingCalendarService


def test_xshg_calendar_verifies_session_and_holiday():
    service = TradingCalendarService()
    session = service.decision(date(2024, 1, 2))
    holiday = service.decision(date(2024, 1, 1))
    assert session.verified is True
    assert session.is_trade_day is True
    assert session.actionable is True
    assert holiday.verified is True
    assert holiday.is_trade_day is False
    assert holiday.actionable is False
    assert session.source == "exchange_calendars:XSHG"
