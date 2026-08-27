from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.providers.types import BarRecord, InstrumentRecord, NewsRecord, QuoteRecord


class ProviderError(RuntimeError):
    pass


class CapabilityUnavailable(ProviderError):
    pass


class MarketProvider(ABC):
    name = "base"

    @abstractmethod
    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        raise NotImplementedError

    @abstractmethod
    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        raise NotImplementedError

    @abstractmethod
    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        raise NotImplementedError

    def fetch_news(self, since_hours: int = 24) -> list[NewsRecord]:
        return []

    def is_trade_day(self, day: date) -> bool:
        return day.weekday() < 5
