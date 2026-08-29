from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any

from app.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class TradingDayDecision:
    day: date
    is_trade_day: bool
    verified: bool
    source: str
    reason: str | None = None

    @property
    def actionable(self) -> bool:
        return self.verified and self.is_trade_day


@lru_cache(maxsize=1)
def _xshg_calendar() -> Any:
    import exchange_calendars as xcals

    return xcals.get_calendar("XSHG")


class TradingCalendarService:
    """Single calendar authority for China-market task and action gates.

    XSHG is the primary local authority. Provider/weekday fallbacks are explicitly
    unverified and may support read-only research scheduling, but never actionable
    signals. This avoids treating Chinese public holidays as ordinary weekdays.
    """

    def __init__(self, settings: Settings | None = None, provider: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.provider = provider

    def decision(self, day: date) -> TradingDayDecision:
        try:
            calendar = _xshg_calendar()
            return TradingDayDecision(
                day=day,
                is_trade_day=bool(calendar.is_session(day.isoformat())),
                verified=True,
                source="exchange_calendars:XSHG",
            )
        except Exception as calendar_error:
            if self.provider is not None and callable(getattr(self.provider, "is_trade_day", None)):
                try:
                    provider_value = bool(self.provider.is_trade_day(day))
                    return TradingDayDecision(
                        day=day,
                        is_trade_day=provider_value,
                        verified=False,
                        source=f"provider-unverified:{getattr(self.provider, 'name', type(self.provider).__name__)}",
                        reason=f"XSHG unavailable: {type(calendar_error).__name__}",
                    )
                except Exception as provider_error:
                    reason = (
                        f"XSHG unavailable: {type(calendar_error).__name__}; "
                        f"provider unavailable: {type(provider_error).__name__}"
                    )
            else:
                reason = f"XSHG unavailable: {type(calendar_error).__name__}"
            return TradingDayDecision(
                day=day,
                is_trade_day=day.weekday() < 5,
                verified=False,
                source="weekday-fallback-unverified",
                reason=reason,
            )

    def actionable_day(self, day: date) -> bool:
        return self.decision(day).actionable
