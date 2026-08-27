from __future__ import annotations

from datetime import date, datetime, timezone

from app.providers.base import MarketProvider
from app.providers.composite import CompositeProvider
from app.providers.types import BarRecord, InstrumentRecord, NewsRecord, QuoteRecord


class DummyProvider(MarketProvider):
    def __init__(self, name: str, rows: list[NewsRecord]):
        self.name = name
        self.rows = rows

    def list_instruments(self, codes=None) -> list[InstrumentRecord]:
        return []

    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        return []

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        return []

    def fetch_news(self, since_hours: int = 24) -> list[NewsRecord]:
        return self.rows


def test_composite_news_aggregates_and_deduplicates():
    now = datetime.now(timezone.utc)
    common = NewsRecord(
        source="rss:test",
        source_id="same",
        title="同一条新闻",
        summary=None,
        url="https://example.com/a",
        published_at=now,
    )
    extra = NewsRecord(
        source="tushare:news",
        source_id="extra",
        title="另一条新闻",
        summary=None,
        url="https://example.com/b",
        published_at=now,
    )
    provider = CompositeProvider(
        [DummyProvider("first", [common]), DummyProvider("second", [common, extra])]
    )
    result = provider.fetch_news(24)
    assert len(result) == 2
    assert len(provider.last_trace) == 2
    assert {row.status for row in provider.last_trace} == {"ok"}
