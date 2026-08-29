from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from app.market_context.contracts import MarketContextItem, MarketContextObservation

__all__ = [
    "InstrumentRecord",
    "BarRecord",
    "QuoteRecord",
    "NewsRecord",
    "MarketContextItem",
    "MarketContextObservation",
]


@dataclass(slots=True)
class InstrumentRecord:
    ts_code: str
    symbol: str
    name: str
    kind: str = "ETF"
    exchange: str | None = None
    theme_l1: str | None = None
    theme_l2: str | None = None
    benchmark: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BarRecord:
    ts_code: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    pre_close: float | None = None
    volume: float | None = None
    amount: float | None = None
    pct_change: float | None = None
    adjust: str = "none"
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuoteRecord:
    ts_code: str
    quote_time: datetime
    price: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    pre_close: float | None = None
    pct_change: float | None = None
    volume: float | None = None
    amount: float | None = None
    premium_rate: float | None = None
    source: str = "unknown"
    is_realtime: bool = False
    degraded_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NewsRecord:
    source: str
    source_id: str
    title: str
    published_at: datetime
    summary: str | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
