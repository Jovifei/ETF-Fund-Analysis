from __future__ import annotations

from datetime import date

import httpx
import pytest
from app.core.config import Settings
from app.providers import FTShareProvider as ExportedFTShareProvider
from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.composite import CompositeProvider
from app.providers.factory import build_provider
from app.providers.ftshare import FTShareProvider

BASE = "https://market.ft.tech/gateway"


def test_ftshare_provider_is_publicly_exported():
    assert ExportedFTShareProvider is FTShareProvider


def test_provider_accepts_http_client_injection_alias():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])))
    provider = FTShareProvider(Settings(_env_file=None, ftshare_enabled=True), http_client=client)
    provider.close()
    assert not client.is_closed
    client.close()


def test_provider_rejects_non_allowlisted_endpoint():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = FTShareProvider(Settings(_env_file=None, ftshare_enabled=True), client=client)
    with pytest.raises(ProviderError):
        provider._get("/api/v1/market/data/not-allowlisted", params={}, tool="x", operation="x", key="data")
    assert calls == []
    client.close()


def _provider(handler, **updates):
    settings = Settings(_env_file=None, ftshare_enabled=True, **updates)
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE)
    return FTShareProvider(settings, client=client)


def _envelope(payload, *, tool, operation, pagination=None, warnings=None):
    return {
        "data": payload,
        "metadata": {"source": "market.ft.tech", "tool": tool, "operation": operation},
        "pagination": pagination or {"page": 1, "pages": 1, "truncated": False},
        "warnings": warnings or [],
    }


def _native_envelope(payload, key, *, source="ftshare", tool="etf-ohlcs", operation="fetch_daily_bars"):
    return {
        key: payload,
        "metadata": {"source": source, "tool": tool, "operation": operation},
    }


def test_settings_are_disabled_by_default_and_bounded():
    settings = Settings(_env_file=None)
    assert settings.ftshare_enabled is False
    assert settings.ftshare_base_url == BASE
    assert settings.ftshare_timeout_seconds == 20
    assert settings.ftshare_max_pages > 0
    assert settings.ftshare_max_rows > 0
    assert settings.ftshare_max_date_span_days > 0


def test_list_instruments_normalizes_exchanges_and_filters_non_etf():
    def handler(request):
        assert request.url.path == "/gateway/api/v1/market/data/etf-description-all"
        return httpx.Response(
            200,
            json=_envelope(
                [
                    {"symbol": "510050.XSHG", "name": "沪深300ETF", "asset_class": "stock"},
                    {"symbol": "159915.XSHE", "name": "创业板ETF", "asset_class": "stock"},
                    {"symbol": "920036.XBSE", "name": "北证ETF", "asset_class": "stock"},
                    {"symbol": "000001.XSHG", "name": "非ETF", "kind": "STOCK"},
                ],
                tool="etf-description-all",
                operation="list_instruments",
            ),
        )

    provider = _provider(handler)
    rows = provider.list_instruments(["510050.SH", "159915.SZ", "920036.BJ"])
    assert [row.ts_code for row in rows] == ["510050.SH", "159915.SZ", "920036.BJ"]
    assert all(row.kind == "ETF" for row in rows)
    provider.close()


def test_daily_bars_maps_dates_units_and_source():
    def handler(request):
        assert request.url.path.endswith("/daec/history/ohlcs")
        assert dict(request.url.params) == {
            "symbol": "510050.XSHG",
            "since": "20260801",
            "until": "20260803",
            "interval": "Day",
            "adjust": "None",
        }
        return httpx.Response(
            200,
            json=_envelope(
                [
                    {
                        "open": "2.8",
                        "high": "2.9",
                        "low": "2.7",
                        "close": "2.85",
                        "volume": 10,
                        "turnover": "28.5",
                        "symbol": "510050.XSHG",
                        "trade_date": "2026-08-03",
                        "open_ts_ms": "2026-08-03T09:30:00",
                        "close_ts_ms": "2026-08-03T15:00:00",
                    }
                ],
                tool="etf-ohlcs",
                operation="fetch_daily_bars",
            ),
        )

    row = _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 1), date(2026, 8, 3))[0]
    assert row.ts_code == "510050.SH"
    assert row.trade_date == date(2026, 8, 3)
    assert row.volume == 10 and row.amount == 28.5
    assert row.pct_change is None
    assert row.source == "ftshare:fetch_daily_bars"
    assert row.adjust == "none"


def test_daily_bars_accepts_exact_pinned_skill_row_without_code_or_trade_date():
    def handler(request):
        assert request.url.path.endswith("/daec/history/ohlcs")
        return httpx.Response(
            200,
            json=_native_envelope(
                [{
                    "open": "2.8", "high": "2.9", "low": "2.7", "close": "2.85",
                    "volume": 10, "turnover": "28.5",
                    "open_ts_ms": "2026-08-03T09:30:00",
                    "close_ts_ms": "2026-08-03T15:00:00",
                }],
                "ohlcs",
            ),
        )

    row = _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 3), date(2026, 8, 3))[0]
    assert row.ts_code == "510050.SH"
    assert row.trade_date == date(2026, 8, 3)


def test_spot_quotes_accept_exact_pinned_skill_row_without_code_for_single_request():
    def handler(request):
        assert request.url.params["symbol"] == "510050.XSHG"
        return httpx.Response(
            200,
            json=_native_envelope(
                [{"price": 2.85, "volume": 3, "turnover": 8.55, "ts_ms": "2026-08-30T10:00:00"}],
                "prices",
                tool="etf-prices",
                operation="fetch_spot_quotes",
            ),
        )

    quote = _provider(handler).fetch_spot_quotes(["510050.SH"])[0]
    assert quote.ts_code == "510050.SH"
    assert quote.price == 2.85


def test_spot_batch_uses_one_request_per_code_without_positional_mapping():
    requested: list[str] = []

    def handler(request):
        symbol = request.url.params["symbol"]
        requested.append(symbol)
        price = 2.85 if symbol == "510050.XSHG" else 1.25
        return httpx.Response(
            200,
            json=_native_envelope(
                [{"price": price, "volume": 3, "turnover": 8.55, "ts_ms": "2026-08-30T10:00:00"}],
                "prices",
                tool="etf-prices",
                operation="fetch_spot_quotes",
            ),
        )

    rows = _provider(handler).fetch_spot_quotes(["510050.SH", "159915.SZ"])
    assert requested == ["510050.XSHG", "159915.XSHE"]
    assert [row.ts_code for row in rows] == ["510050.SH", "159915.SZ"]


def test_daily_requests_explicit_unadjusted_data_and_rejects_contradictory_metadata():
    def handler(request):
        assert request.url.params["adjust"] == "None"
        return httpx.Response(200, json={
            "data": [{"symbol": "510050.XSHG", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-03", "open_ts_ms": "2026-08-03T09:30:00", "close_ts_ms": "2026-08-03T15:00:00"}],
            "metadata": {"source": "ftshare", "tool": "etf-ohlcs", "operation": "fetch_daily_bars", "adjustment": "Forward"},
        })

    with pytest.raises(ProviderError):
        _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 3), date(2026, 8, 3))


def test_response_byte_limit_stops_stream_and_closes_it():
    closed = []

    class Body(httpx.SyncByteStream):
        def __iter__(self):
            yield b"{" + b"x" * 1300

        def close(self):
            closed.append(True)

    def handler(_request):
        return httpx.Response(200, stream=Body())

    provider = _provider(handler, ftshare_max_response_bytes=1024)
    with pytest.raises(CapabilityUnavailable):
        provider.list_instruments()
    assert closed == [True]


def test_composite_close_is_idempotent_and_market_provider_close_is_noop():
    class Closable:
        name = "closable"

        def __init__(self):
            self.calls = 0

        def close(self):
            self.calls += 1

    first, second = Closable(), Closable()
    composite = CompositeProvider([first, second])
    composite.close()
    composite.close()
    assert first.calls == second.calls == 1


def test_composite_close_attempts_all_children_and_sanitizes_failures():
    class Failing:
        name = "failing"

        def __init__(self):
            self.calls = 0

        def close(self):
            self.calls += 1
            raise RuntimeError("secret close detail")

    first, second = Failing(), Failing()
    composite = CompositeProvider([first, second])
    with pytest.raises(ProviderError) as raised:
        composite.close()
    assert "secret close detail" not in str(raised.value)
    assert first.calls == second.calls == 1
    composite.close()
    assert first.calls == second.calls == 1


def test_task_service_closes_only_owned_provider(db_session):
    from app.services.task_service import TaskService

    class Closable:
        name = "injected"

        def __init__(self):
            self.calls = 0

        def close(self):
            self.calls += 1

    injected = Closable()
    service = TaskService(Settings(_env_file=None, market_provider="mock"), provider=injected)
    service.close()
    assert injected.calls == 0


def test_factory_aggregate_errors_never_include_provider_exception_text(monkeypatch):
    def fail(_settings):
        raise RuntimeError("secret upstream query")

    monkeypatch.setattr("app.providers.factory.TushareProvider", fail)
    monkeypatch.setattr("app.providers.factory.AKShareProvider", fail)
    monkeypatch.setattr("app.providers.factory.FTShareProvider", fail)
    with pytest.raises(ProviderError) as raised:
        build_provider(Settings(_env_file=None, market_provider="composite", ftshare_enabled=True, ftshare_qualification="qualified"))
    assert "secret upstream query" not in str(raised.value)


def test_spot_quotes_are_explicitly_non_realtime():
    def handler(request):
        assert request.url.path.endswith("/daec/history/prices")
        assert dict(request.url.params) == {"symbol": "510050.XSHG", "range": "Today"}
        return httpx.Response(
            200,
            json=_envelope(
                [{"symbol": "510050.XSHG", "price": 2.85, "volume": 3, "turnover": 8.55, "ts_ms": "2026-08-30T10:00:00+08:00"}],
                tool="etf-prices",
                operation="fetch_spot_quotes",
            ),
        )

    quote = _provider(handler).fetch_spot_quotes(["510050.SH"])[0]
    assert quote.ts_code == "510050.SH"
    assert quote.price == 2.85
    assert quote.is_realtime is False
    assert quote.degraded_reason
    assert quote.source == "ftshare:fetch_spot_quotes"


def test_spot_quotes_validate_optional_ohlc_and_percent_units():
    def handler(_request):
        return httpx.Response(
            200,
            json=_envelope(
                [{"symbol": "510050.XSHG", "price": 2.85, "open": 2.9, "high": 2.8, "low": 2.7, "volume": 1, "turnover": 1, "pct_change": 1.0, "ts_ms": "2026-08-30T10:00:00+08:00"}],
                tool="etf-prices",
                operation="fetch_spot_quotes",
            ),
        )

    with pytest.raises(ProviderError):
        _provider(handler).fetch_spot_quotes(["510050.SH"])


@pytest.mark.parametrize(
    "payload",
    [
        {"error": {"code": "UPSTREAM_REJECTED", "message": "do not leak this"}},
        {"data": [], "metadata": {"source": "market.ft.tech", "tool": "etf-ohlcs", "operation": "fetch_daily_bars"}},
    ],
)
def test_upstream_rejection_and_empty_data_fail_closed_without_leaking(payload):
    def handler(_request):
        return httpx.Response(403 if "error" in payload else 200, json=payload)

    provider = _provider(handler)
    with pytest.raises(CapabilityUnavailable) as raised:
        provider.fetch_daily_bars("510050.SH", date(2026, 8, 1), date(2026, 8, 3))
    assert "do not leak" not in str(raised.value)
    assert "market.ft.tech" not in str(raised.value)


def test_structured_upstream_rejection_is_mapped_even_on_success_http_status():
    def handler(_request):
        return httpx.Response(200, json={"error": {"code": "UPSTREAM_REJECTED", "message": "private detail"}})

    with pytest.raises(CapabilityUnavailable) as raised:
        _provider(handler).list_instruments()
    assert "private detail" not in str(raised.value)


@pytest.mark.parametrize(
    "row",
    [
        {"open": 2, "high": 1, "low": 1, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-03"},
        {"open": "NaN", "high": 2, "low": 1, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-03"},
        {"open": 2, "high": 2, "low": 1, "close": 2, "volume": -1, "turnover": 1, "trade_date": "2026-08-03"},
        {"open": 2, "high": 2, "low": 1, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2027-08-03"},
    ],
)
def test_invalid_daily_rows_are_rejected(row):
    def handler(_request):
        return httpx.Response(200, json=_envelope([row], tool="etf-ohlcs", operation="fetch_daily_bars"))

    with pytest.raises(ProviderError):
        _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 1), date(2026, 8, 3))


def test_truncated_or_oversize_responses_are_rejected():
    def handler(_request):
        return httpx.Response(
            200,
            json=_envelope(
                [{"symbol": "510050.XSHG", "name": "x", "asset_class": "stock"}],
                tool="etf-description-all",
                operation="list_instruments",
                pagination={"page": 1, "pages": 2, "truncated": True},
            ),
        )

    with pytest.raises(CapabilityUnavailable):
        _provider(handler).list_instruments()


def test_native_wrapper_metadata_is_checked_when_present():
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "ohlcs": [{"symbol": "510050.XSHG", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-03"}],
                "metadata": {"source": "untrusted.example", "tool": "etf-ohlcs", "operation": "fetch_daily_bars"},
            },
        )

    with pytest.raises(ProviderError):
        _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 1), date(2026, 8, 3))


def test_timeout_is_sanitized():
    def handler(_request):
        raise httpx.ReadTimeout("secret host details")

    with pytest.raises(CapabilityUnavailable) as raised:
        _provider(handler).fetch_spot_quotes(["510050.SH"])
    assert "secret host details" not in str(raised.value)


def test_unexpected_transport_exception_is_sanitized(caplog):
    def handler(_request):
        raise RuntimeError("secret transport query and host")

    with pytest.raises(ProviderError) as raised:
        _provider(handler).list_instruments()
    assert "secret transport query and host" not in str(raised.value)
    assert "secret transport query and host" not in caplog.text


def test_malformed_timestamp_is_sanitized():
    def handler(_request):
        return httpx.Response(
            200,
            json=_envelope(
                [{"symbol": "510050.XSHG", "price": 2.85, "volume": 1, "turnover": 1, "ts_ms": 999999999999999999999}],
                tool="etf-prices",
                operation="fetch_spot_quotes",
            ),
        )

    with pytest.raises(ProviderError):
        _provider(handler).fetch_spot_quotes(["510050.SH"])


def test_factory_explicit_ftshare_requires_enabled_and_composites_order(monkeypatch):
    class Fake:
        name = "fake"

        def __init__(self, settings):
            self.settings = settings

    monkeypatch.setattr("app.providers.factory.AKShareProvider", type("AK", (Fake,), {"name": "akshare"}))
    monkeypatch.setattr("app.providers.factory.TushareProvider", type("TS", (Fake,), {"name": "tushare"}))
    monkeypatch.setattr("app.providers.factory.FTShareProvider", type("FT", (Fake,), {"name": "ftshare"}))
    with pytest.raises(CapabilityUnavailable):
        build_provider(Settings(_env_file=None, market_provider="ftshare", ftshare_enabled=False))
    with pytest.raises(CapabilityUnavailable):
        build_provider(Settings(_env_file=None, market_provider="ftshare", ftshare_enabled=True, ftshare_qualification="unverified"))
    unqualified = build_provider(Settings(_env_file=None, market_provider="public_composite", ftshare_enabled=True, ftshare_qualification="rejected"))
    assert [item.name for item in unqualified.providers] == ["akshare"]
    provider = build_provider(Settings(_env_file=None, market_provider="public_composite", ftshare_enabled=True, ftshare_qualification="qualified"))
    assert [item.name for item in provider.providers] == ["akshare", "ftshare"]
    provider = build_provider(Settings(_env_file=None, market_provider="composite", ftshare_enabled=True, ftshare_qualification="qualified"))
    assert [item.name for item in provider.providers] == ["tushare", "akshare", "ftshare"]


def test_public_composite_uses_tushare_only_after_akshare_when_token_is_available(monkeypatch):
    class Fake:
        def __init__(self, settings):
            self.settings = settings

    monkeypatch.setattr("app.providers.factory.AKShareProvider", type("AK", (Fake,), {"name": "akshare"}))
    monkeypatch.setattr("app.providers.factory.TushareProvider", type("TS", (Fake,), {"name": "tushare"}))
    monkeypatch.setattr("app.providers.factory.FTShareProvider", type("FT", (Fake,), {"name": "ftshare"}))

    provider = build_provider(
        Settings(
            _env_file=None,
            market_provider="public_composite",
            tushare_token="unit-test-token-123456",
            ftshare_enabled=True,
            ftshare_qualification="qualified",
        )
    )

    assert [item.name for item in provider.providers] == ["akshare", "tushare", "ftshare"]


def test_new_factory_chains_never_add_mock_even_when_legacy_flag_is_true(monkeypatch):
    class Fake:
        def __init__(self, settings):
            self.settings = settings

    monkeypatch.setattr("app.providers.factory.AKShareProvider", type("AK", (Fake,), {"name": "akshare"}))
    monkeypatch.setattr("app.providers.factory.TushareProvider", type("TS", (Fake,), {"name": "tushare"}))
    monkeypatch.setattr("app.providers.factory.FTShareProvider", type("FT", (Fake,), {"name": "ftshare"}))
    for mode, expected in (("public_composite", ["akshare", "ftshare"]), ("composite", ["tushare", "akshare", "ftshare"])):
        provider = build_provider(Settings(_env_file=None, market_provider=mode, ftshare_enabled=True, ftshare_qualification="qualified", allow_mock_fallback=True))
        assert [item.name for item in provider.providers] == expected


@pytest.mark.parametrize("source", ["market.ft.tech.evil", "ftshare-http", "https://market.ft.tech"])
def test_metadata_source_requires_exact_allowlist(source):
    def handler(_request):
        return httpx.Response(200, json=_envelope(
            [{"symbol": "510050.XSHG", "name": "x", "asset_class": "stock"}],
            tool="etf-description-all", operation="list_instruments",
        ) | {"metadata": {"source": source, "tool": "etf-description-all", "operation": "list_instruments"}})

    with pytest.raises(ProviderError):
        _provider(handler).list_instruments()


def test_native_wrapper_without_exact_metadata_is_rejected():
    def handler(_request):
        return httpx.Response(200, json={"ohlcs": [{"symbol": "510050.XSHG", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-03"}]})

    with pytest.raises(ProviderError):
        _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 1), date(2026, 8, 3))


@pytest.mark.parametrize("row", [
    {"symbol": "159915.XSHE", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-03", "open_ts_ms": "2026-08-03T09:30:00", "close_ts_ms": "2026-08-03T15:00:00"},
    {"symbol": "510050.XSHG", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-02", "open_ts_ms": "2026-08-03T09:30:00", "close_ts_ms": "2026-08-03T15:00:00"},
])
def test_daily_optional_symbol_and_date_must_match_requested_boundaries(row):
    def handler(_request):
        return httpx.Response(200, json=_envelope([row], tool="etf-ohlcs", operation="fetch_daily_bars"))

    with pytest.raises(ProviderError):
        _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 1), date(2026, 8, 3))


def test_spot_row_foreign_symbol_is_rejected():
    def handler(_request):
        return httpx.Response(200, json=_envelope(
            [{"symbol": "159915.XSHE", "price": 2.85, "volume": 1, "turnover": 1, "ts_ms": "2026-08-30T10:00:00+08:00"}],
            tool="etf-prices", operation="fetch_spot_quotes",
        ))

    with pytest.raises(ProviderError):
        _provider(handler).fetch_spot_quotes(["510050.SH"])


def test_future_source_timestamp_is_rejected_even_when_trade_date_is_current():
    def handler(_request):
        return httpx.Response(200, json=_envelope(
            [{"symbol": "510050.XSHG", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-30", "open_ts_ms": "2027-08-30T09:30:00", "close_ts_ms": "2027-08-30T15:00:00"}],
            tool="etf-ohlcs", operation="fetch_daily_bars",
        ))

    with pytest.raises(ProviderError):
        _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 30), date(2026, 8, 30))


@pytest.mark.parametrize("row", [
    {"symbol": "510050.XSHG", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-03", "close_ts_ms": "2026-08-03T15:00:00"},
    {"symbol": "510050.XSHG", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-03", "open_ts_ms": "2026-08-03T15:00:00", "close_ts_ms": "2026-08-03T09:30:00"},
    {"symbol": "510050.XSHG", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-03", "open_ts_ms": 1785720600000.0, "close_ts_ms": 1785740400000},
    {"symbol": "510050.XSHG", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1, "turnover": 1, "trade_date": "2026-08-03", "open_ts_ms": True, "close_ts_ms": 1785740400000},
])
def test_daily_requires_bounded_integer_millis_and_ordered_same_day_timestamps(row):
    def handler(_request):
        return httpx.Response(200, json=_envelope([row], tool="etf-ohlcs", operation="fetch_daily_bars"))

    with pytest.raises(ProviderError):
        _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 3), date(2026, 8, 3))


@pytest.mark.parametrize("pagination", [
    {"page": True, "pages": 1}, {"page": 0, "pages": 1}, {"page": 1.5, "pages": 2},
    {"page": 2, "pages": 1}, {"page": 1, "pages": -1},
])
def test_pagination_fields_are_strict_positive_integers(pagination):
    def handler(_request):
        return httpx.Response(200, json=_envelope(
            [{"symbol": "510050.XSHG", "name": "x", "asset_class": "stock"}],
            tool="etf-description-all", operation="list_instruments", pagination=pagination,
        ))

    with pytest.raises(ProviderError):
        _provider(handler).list_instruments()


def test_pagination_page_is_bounded_without_total_pages():
    def handler(_request):
        return httpx.Response(200, json=_envelope(
            [{"symbol": "510050.XSHG", "name": "x", "asset_class": "stock"}],
            tool="etf-description-all", operation="list_instruments",
            pagination={"page": 11},
        ))

    with pytest.raises(CapabilityUnavailable):
        _provider(handler).list_instruments()


@pytest.mark.parametrize("volume", [True, 1.5, "1.5", "1.0"])
def test_daily_volume_requires_integer_shares(volume):
    def handler(_request):
        return httpx.Response(200, json=_envelope([{
            "symbol": "510050.XSHG", "open": 2, "high": 2, "low": 2, "close": 2,
            "volume": volume, "turnover": 1, "trade_date": "2026-08-03",
            "open_ts_ms": "2026-08-03T09:30:00", "close_ts_ms": "2026-08-03T15:00:00",
        }], tool="etf-ohlcs", operation="fetch_daily_bars"))

    with pytest.raises(ProviderError):
        _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 3), date(2026, 8, 3))


@pytest.mark.parametrize("price", [0, -0.1, "0"])
def test_daily_prices_must_be_strictly_positive(price):
    def handler(_request):
        return httpx.Response(200, json=_envelope([{
            "symbol": "510050.XSHG", "open": price, "high": 2, "low": 1, "close": 2,
            "volume": 1, "turnover": 1, "trade_date": "2026-08-03",
            "open_ts_ms": "2026-08-03T09:30:00", "close_ts_ms": "2026-08-03T15:00:00",
        }], tool="etf-ohlcs", operation="fetch_daily_bars"))

    with pytest.raises(ProviderError):
        _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 3), date(2026, 8, 3))


def test_derived_pct_is_bounded_and_does_not_trust_upstream_units():
    def handler(_request):
        return httpx.Response(200, json=_envelope([{
            "symbol": "510050.XSHG", "open": 2, "high": 2, "low": 2, "close": 2,
            "volume": 1, "turnover": 1, "trade_date": "2026-08-03",
            "open_ts_ms": "2026-08-03T09:30:00", "close_ts_ms": "2026-08-03T15:00:00", "pct_change": 999,
        }, {
            "symbol": "510050.XSHG", "open": 3, "high": 3, "low": 3, "close": 3,
            "volume": 1, "turnover": 1, "trade_date": "2026-08-04",
            "open_ts_ms": "2026-08-04T09:30:00", "close_ts_ms": "2026-08-04T15:00:00", "pct_change": -999,
        }], tool="etf-ohlcs", operation="fetch_daily_bars"))

    rows = _provider(handler).fetch_daily_bars("510050.SH", date(2026, 8, 3), date(2026, 8, 4))
    assert rows[0].pct_change is None
    assert rows[1].pct_change == 50


def test_quote_price_zero_and_nonfinite_pct_are_rejected():
    def handler(_request):
        return httpx.Response(200, json=_envelope([{
            "symbol": "510050.XSHG", "price": 0, "pre_close": 2, "volume": 1,
            "turnover": 1, "ts_ms": "2026-08-30T10:00:00+08:00", "pct_change": "NaN",
        }], tool="etf-prices", operation="fetch_spot_quotes"))

    with pytest.raises(ProviderError):
        _provider(handler).fetch_spot_quotes(["510050.SH"])


@pytest.mark.parametrize("base_url", ["http://market.ft.tech/gateway", "https://evil.test/gateway", "https://user:pass@market.ft.tech/gateway", "https://market.ft.tech/not-gateway", "https://market.ft.tech/gateway?x=1"])
def test_base_url_is_fixed_and_rejects_unsafe_values(base_url):
    with pytest.raises(ProviderError):
        FTShareProvider(Settings(_env_file=None, ftshare_enabled=True, ftshare_base_url=base_url))


def test_custom_base_url_requires_explicit_nonproduction_opt_in():
    settings = Settings(_env_file=None, app_env="test", ftshare_enabled=True, ftshare_base_url="https://mock.local/gateway", ftshare_allow_custom_base_url=True)
    provider = FTShareProvider(settings, client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[]))))
    provider.close()


def test_custom_base_url_is_rejected_in_production_even_when_flagged():
    settings = Settings(
        _env_file=None,
        app_env="production",
        auth_enabled=False,
        ocr_mode="disabled",
        ftshare_enabled=True,
        ftshare_base_url="https://mock.local/gateway",
        ftshare_allow_custom_base_url=True,
    )
    with pytest.raises(ProviderError):
        FTShareProvider(settings)


def test_runtime_resolution_preserves_explicit_ftshare_modes(db_session):
    from app.services.runtime_service import RuntimeService

    for mode in ("ftshare", "public_composite"):
        settings = Settings(_env_file=None, market_provider=mode, ftshare_enabled=True)
        resolved = RuntimeService(settings).resolve_settings(db_session)
        assert resolved.market_provider == mode
