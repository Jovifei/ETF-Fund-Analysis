from __future__ import annotations

from datetime import UTC, date, datetime

from app.models import Instrument
from app.providers.base import MarketProvider, ProviderError
from app.providers.composite import CompositeProvider
from app.providers.types import BarRecord, InstrumentRecord, QuoteRecord
from app.services.market_service import MarketService
from sqlalchemy import select


class _Provider(MarketProvider):
    def __init__(
        self,
        name: str,
        *,
        quotes: dict[str, QuoteRecord] | None = None,
        instruments: dict[str, InstrumentRecord] | None = None,
        daily_bars: list[BarRecord] | None = None,
        quote_error: Exception | None = None,
    ) -> None:
        self.name = name
        self.quotes = {str(k).upper(): v for k, v in (quotes or {}).items()}
        self.instruments = {str(k).upper(): v for k, v in (instruments or {}).items()}
        self.daily_bars = list(daily_bars or [])
        self.quote_error = quote_error
        self.quote_calls: list[list[str]] = []
        self.instrument_calls: list[list[str] | None] = []
        self.daily_calls: list[tuple[str, date, date]] = []

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
        self.daily_calls.append((ts_code, start_date, end_date))
        return list(self.daily_bars)

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


def _bar(code: str, source: str, close: float = 4.10) -> BarRecord:
    return BarRecord(
        ts_code=code,
        trade_date=date(2026, 9, 17),
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        pre_close=close,
        volume=1000.0 if source != "akshare:sina:v101" else None,
        amount=close * 1000.0 if source != "akshare:sina:v101" else None,
        pct_change=0.0,
        adjust="none",
        source=source,
    )


def test_daily_price_only_primary_does_not_hide_documented_fallback() -> None:
    code = "510300.SH"
    primary = _Provider("akshare", daily_bars=[_bar(code, "akshare:sina:v101")])
    fallback = _Provider("tushare", daily_bars=[_bar(code, "tushare:fund_daily:v101")])
    provider = CompositeProvider([primary, fallback])

    rows = provider.fetch_daily_bars(code, date(2026, 9, 1), date(2026, 9, 17))

    assert [row.source for row in rows] == ["tushare:fund_daily:v101"]
    assert len(primary.daily_calls) == 1
    assert len(fallback.daily_calls) == 1
    assert [item.status for item in provider.last_trace] == ["quality_fallback", "fallback_used"]
    assert provider.last_trace[0].reason == "price_only_units_unverified"


def test_only_price_only_daily_candidate_remains_partial_in_audit() -> None:
    code = "510300.SH"
    primary = _Provider("akshare", daily_bars=[_bar(code, "akshare:sina:v101")])
    provider = CompositeProvider([primary])

    rows = provider.fetch_daily_bars(code, date(2026, 9, 1), date(2026, 9, 18))

    assert [row.source for row in rows] == ["akshare:sina:v101"]
    assert provider.last_trace[0].status == "partial"
    assert provider.last_trace[0].reason == "price_only_units_unverified"


def test_degraded_primary_quote_does_not_hide_verified_realtime_fallback() -> None:
    code = "510300.SH"
    degraded = QuoteRecord(
        ts_code=code,
        quote_time=datetime(2026, 9, 17, 6, 30, tzinfo=UTC),
        price=4.10,
        source="akshare:em:v101",
        is_realtime=False,
        degraded_reason="public_quote_not_qualified",
    )
    primary = _Provider("akshare", quotes={code: degraded})
    fallback = _Provider("tushare", quotes={code: _quote(code, "tushare:rt_etf_k:v101", 4.11)})
    provider = CompositeProvider([primary, fallback])

    rows = provider.fetch_spot_quotes([code])

    assert [row.source for row in rows] == ["tushare:rt_etf_k:v101"]
    assert primary.quote_calls == [[code]]
    assert fallback.quote_calls == [[code]]


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


def test_market_service_reports_requested_received_and_missing_codes(bootstrapped, db_session) -> None:
    instruments = db_session.scalars(
        select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code).limit(2)
    ).all()
    assert len(instruments) == 2
    first, second = instruments
    provider = _Provider(
        "partial",
        quotes={first.ts_code: _quote(first.ts_code, "akshare", 1.23)},
    )

    result = MarketService(provider, persist_provider_audits=False).refresh_quotes(
        db_session,
        codes=[first.ts_code, second.ts_code],
        run_id="coverage-audit-test",
    )

    assert result["requested"] == 2
    assert result["received"] == 1
    assert result["missing"] == 1
    assert result["missing_codes"] == [second.ts_code]
