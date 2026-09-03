from __future__ import annotations

from datetime import UTC, date, datetime

from app.providers.base import MarketProvider, ProviderError
from app.providers.composite import CompositeProvider
from app.providers.types import BarRecord, InstrumentRecord, QuoteRecord


class _Provider(MarketProvider):
    def __init__(
        self,
        name: str,
        *,
        quotes: dict[str, QuoteRecord] | None = None,
        instruments: dict[str, InstrumentRecord] | None = None,
        quote_error: Exception | None = None,
    ) -> None:
        self.name = name
        self.quotes = {str(k).upper(): v for k, v in (quotes or {}).items()}
        self.instruments = {str(k).upper(): v for k, v in (instruments or {}).items()}
        self.quote_error = quote_error
        self.quote_calls: list[list[str]] = []
        self.instrument_calls: list[list[str] | None] = []

    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        self.instrument_calls.append(list(codes) if codes is not None else None)
        if codes is None:
            return list(self.instruments.values())
        wanted = {str(code).upper() for code in codes}
        result: list[InstrumentRecord] = []
        for item in self.instruments.values():
            if item.ts_code.upper() in wanted or item.symbol.upper() in wanted:
                result.append(item)
        return result

    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        del ts_code, start_date, end_date
        return []

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        self.quote_calls.append(list(codes))
        if self.quote_error is not None:
            raise self.quote_error
        wanted = {str(code).upper() for code in codes}
        return [item for key, item in self.quotes.items() if key in wanted]


def _quote(code: str, source: str, price: float) -> QuoteRecord:
    return QuoteRecord(
        ts_code=code,
        quote_time=datetime(2026, 9, 3, 6, 30, tzinfo=UTC),
        price=price,
        source=source,
        is_realtime=True,
    )


def _instrument(code: str, symbol: str, name: str) -> InstrumentRecord:
    return InstrumentRecord(ts_code=code, symbol=symbol, name=name)


def test_quotes_fill_only_missing_codes_and_preserve_primary_priority() -> None:
    primary = _Provider(
        "primary",
        quotes={
            "510300.SH": _quote("510300.SH", "primary", 4.10),
            "510500.SH": _quote("510500.SH", "primary", 6.20),
        },
    )
    fallback = _Provider(
        "fallback",
        quotes={
            "510300.SH": _quote("510300.SH", "fallback", 99.0),
            "159915.SZ": _quote("159915.SZ", "fallback", 2.30),
        },
    )
    provider = CompositeProvider([primary, fallback])

    rows = provider.fetch_spot_quotes(["510300.SH", "510500.SH", "159915.SZ"])

    assert [row.ts_code for row in rows] == ["510300.SH", "510500.SH", "159915.SZ"]
    assert [row.source for row in rows] == ["primary", "primary", "fallback"]
    assert primary.quote_calls == [["510300.SH", "510500.SH", "159915.SZ"]]
    assert fallback.quote_calls == [["159915.SZ"]]
    assert [item.status for item in provider.last_trace] == ["partial", "fallback_used"]
    assert [item.record_count for item in provider.last_trace] == [2, 1]


def test_full_primary_quote_coverage_does_not_call_fallback() -> None:
    primary = _Provider(
        "primary",
        quotes={
            "510300.SH": _quote("510300.SH", "primary", 4.10),
            "159915.SZ": _quote("159915.SZ", "primary", 2.30),
        },
    )
    fallback = _Provider("fallback", quotes={"159915.SZ": _quote("159915.SZ", "fallback", 99.0)})
    provider = CompositeProvider([primary, fallback])

    rows = provider.fetch_spot_quotes(["510300.SH", "159915.SZ"])

    assert len(rows) == 2
    assert fallback.quote_calls == []
    assert [item.status for item in provider.last_trace] == ["ok"]


def test_primary_failure_can_be_filled_by_fallback_per_code() -> None:
    primary = _Provider("primary", quote_error=ProviderError("primary unavailable"))
    fallback = _Provider(
        "fallback",
        quotes={
            "510300.SH": _quote("510300.SH", "fallback", 4.10),
            "159915.SZ": _quote("159915.SZ", "fallback", 2.30),
        },
    )
    provider = CompositeProvider([primary, fallback])

    rows = provider.fetch_spot_quotes(["510300.SH", "159915.SZ"])

    assert [row.ts_code for row in rows] == ["510300.SH", "159915.SZ"]
    assert [item.status for item in provider.last_trace] == ["failed", "fallback_used"]


def test_partial_coverage_returns_known_rows_and_keeps_missing_explicit_in_trace() -> None:
    primary = _Provider("primary", quotes={"510300.SH": _quote("510300.SH", "primary", 4.10)})
    fallback = _Provider("fallback", quotes={})
    provider = CompositeProvider([primary, fallback])

    rows = provider.fetch_spot_quotes(["510300.SH", "159915.SZ"])

    assert [row.ts_code for row in rows] == ["510300.SH"]
    assert [item.status for item in provider.last_trace] == ["partial", "empty"]
    assert provider.last_trace[-1].reason == "missing=1"


def test_instrument_lookup_fills_missing_symbol_alias_without_overwriting_primary() -> None:
    primary = _Provider(
        "primary",
        instruments={"510300.SH": _instrument("510300.SH", "510300", "沪深300ETF")},
    )
    fallback = _Provider(
        "fallback",
        instruments={"159915.SZ": _instrument("159915.SZ", "159915", "创业板ETF")},
    )
    provider = CompositeProvider([primary, fallback])

    rows = provider.list_instruments(["510300", "159915"])

    assert [row.ts_code for row in rows] == ["510300.SH", "159915.SZ"]
    assert primary.instrument_calls == [["510300", "159915"]]
    assert fallback.instrument_calls == [["159915"]]
