from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo


class MarketPhase(StrEnum):
    PRE_OPEN = "pre_open"
    OPEN_AUCTION = "open_auction"
    MORNING = "morning"
    LUNCH = "lunch"
    AFTERNOON = "afternoon"
    CLOSE_AUCTION = "close_auction"
    AFTER_CLOSE = "after_close"
    CLOSED = "closed"


@dataclass(frozen=True)
class MarketClock:
    timezone: ZoneInfo = ZoneInfo("Asia/Shanghai")

    def now(self) -> datetime:
        return datetime.now(self.timezone)

    def phase(self, at: datetime | None = None, is_trade_day: bool = True) -> MarketPhase:
        at = at.astimezone(self.timezone) if at else self.now()
        if not is_trade_day:
            return MarketPhase.CLOSED
        current = at.time().replace(tzinfo=None)
        if current < time(9, 15):
            return MarketPhase.PRE_OPEN
        if current < time(9, 30):
            return MarketPhase.OPEN_AUCTION
        if current <= time(11, 30):
            return MarketPhase.MORNING
        if current < time(13, 0):
            return MarketPhase.LUNCH
        if current < time(14, 57):
            return MarketPhase.AFTERNOON
        if current <= time(15, 0):
            return MarketPhase.CLOSE_AUCTION
        if current < time(18, 0):
            return MarketPhase.AFTER_CLOSE
        return MarketPhase.CLOSED

    def price_session_open(self, at: datetime | None = None, is_trade_day: bool = True) -> bool:
        return self.phase(at, is_trade_day) in {
            MarketPhase.OPEN_AUCTION,
            MarketPhase.MORNING,
            MarketPhase.AFTERNOON,
            MarketPhase.CLOSE_AUCTION,
        }

    def signals_allowed(self, at: datetime | None = None, is_trade_day: bool = True) -> bool:
        return self.phase(at, is_trade_day) in {
            MarketPhase.MORNING,
            MarketPhase.AFTERNOON,
            MarketPhase.CLOSE_AUCTION,
            MarketPhase.AFTER_CLOSE,
        }

    @staticmethod
    def weekday_trade_day(day: date) -> bool:
        return day.weekday() < 5
