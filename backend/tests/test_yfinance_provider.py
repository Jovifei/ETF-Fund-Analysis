from __future__ import annotations

from datetime import date, datetime
import math
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.types import BarRecord, InstrumentRecord, QuoteRecord


def test_yfinance_provider_initialization_and_catalog():
    from app.providers.yfinance_provider import YFinanceProvider

    provider = YFinanceProvider()
    assert provider.name == "yfinance"
    catalog = provider.list_instruments()
    assert len(catalog) >= 7
    codes = {item.symbol for item in catalog}
    assert {"SPY", "QQQ", "IWM", "VTI", "GLD", "TLT", "EFA"}.issubset(codes)
    for item in catalog:
        assert isinstance(item, InstrumentRecord)
        assert item.kind == "ETF"
        assert item.exchange in {"NYSE", "NASDAQ", "BATS", "US"}


def test_yfinance_provider_resolve_instrument():
    from app.providers.yfinance_provider import YFinanceProvider

    provider = YFinanceProvider()
    spy = provider.resolve_instrument("SPY")
    assert spy is not None
    assert spy.symbol == "SPY"
    assert spy.ts_code == "SPY.US"

    spy_us = provider.resolve_instrument("SPY.US")
    assert spy_us is not None
    assert spy_us.symbol == "SPY"

    unknown = provider.resolve_instrument("UNKNOWN_999")
    assert unknown is None


def test_yfinance_provider_is_trade_day():
    from app.providers.yfinance_provider import YFinanceProvider

    provider = YFinanceProvider()
    assert provider.is_trade_day(date(2026, 10, 30)) is True
    assert provider.is_trade_day(date(2026, 10, 31)) is False
    assert provider.is_trade_day(date(2026, 11, 1)) is False


def test_yfinance_provider_fetch_daily_bars_with_mocked_data():
    from app.providers.yfinance_provider import YFinanceProvider

    provider = YFinanceProvider()

    dates = pd.to_datetime(["2026-10-27", "2026-10-28", "2026-10-29"])
    mock_df = pd.DataFrame(
        {
            "Open": [580.10, 582.50, 585.00],
            "High": [583.20, 586.00, 587.50],
            "Low": [579.50, 581.00, 584.20],
            "Close": [582.00, 584.80, 586.20],
            "Volume": [45000000, 42000000, 39000000],
        },
        index=dates,
    )

    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.return_value = mock_df
        mock_ticker.return_value = mock_instance

        bars = provider.fetch_daily_bars("SPY", date(2026, 10, 27), date(2026, 10, 29))
        assert len(bars) == 3
        for bar in bars:
            assert isinstance(bar, BarRecord)
            assert bar.ts_code == "SPY.US"
            assert bar.open > 0
            assert bar.high >= bar.low
            assert bar.source == "yfinance"

        assert bars[0].pre_close is None
        assert bars[1].pre_close == 582.00
        assert bars[1].pct_change == round((584.80 - 582.00) / 582.00 * 100, 4)


def test_yfinance_provider_fetch_daily_bars_filters_nan_and_inf():
    from app.providers.yfinance_provider import YFinanceProvider

    provider = YFinanceProvider()

    dates = pd.to_datetime(["2026-10-27", "2026-10-28", "2026-10-29"])
    mock_df = pd.DataFrame(
        {
            "Open": [580.10, float("nan"), 585.00],
            "High": [583.20, 586.00, float("inf")],
            "Low": [579.50, 581.00, 584.20],
            "Close": [582.00, 584.80, 586.20],
            "Volume": [45000000, 42000000, 39000000],
        },
        index=dates,
    )

    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.return_value = mock_df
        mock_ticker.return_value = mock_instance

        bars = provider.fetch_daily_bars("SPY", date(2026, 10, 27), date(2026, 10, 29))
        # Day 2 has NaN Open, Day 3 has Inf High -> only Day 1 should be retained
        assert len(bars) == 1
        assert bars[0].trade_date == date(2026, 10, 27)


def test_yfinance_provider_fetch_daily_bars_upstream_failure():
    from app.providers.yfinance_provider import YFinanceProvider

    provider = YFinanceProvider()
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.side_effect = ConnectionError("network unreachable")
        mock_ticker.return_value = mock_instance

        with pytest.raises(ProviderError, match="yfinance fetch failed"):
            provider.fetch_daily_bars("SPY", date(2026, 10, 27), date(2026, 10, 29))


def test_yfinance_provider_fetch_spot_quotes_never_realtime():
    from app.providers.yfinance_provider import YFinanceProvider

    provider = YFinanceProvider()

    mock_df = pd.DataFrame(
        {
            "Open": [585.00],
            "High": [587.50],
            "Low": [584.20],
            "Close": [586.20],
            "Volume": [39000000],
        },
        index=pd.to_datetime(["2026-10-29"]),
    )

    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.return_value = mock_df
        mock_ticker.return_value = mock_instance

        quotes = provider.fetch_spot_quotes(["SPY.US"])
        assert len(quotes) == 1
        quote = quotes[0]
        assert isinstance(quote, QuoteRecord)
        assert quote.ts_code == "SPY.US"
        assert quote.price == 586.20
        # Contract requirement: never mark delayed/research quote as realtime
        assert quote.is_realtime is False
        assert quote.source == "yfinance"


def test_yfinance_provider_factory():
    from app.core.config import Settings
    from app.providers.factory import build_provider
    from app.providers.yfinance_provider import YFinanceProvider

    settings = Settings(market_provider="yfinance")
    provider = build_provider(settings)
    assert provider.name == "yfinance"


def test_yfinance_bars_indicator_calculation_compatibility():
    from app.core.config import Settings
    from app.providers.yfinance_provider import YFinanceProvider
    from app.utils.indicators_v05 import calculate_indicators

    provider = YFinanceProvider()
    strategy = Settings().load_strategy()
    indicator_cfg = strategy["indicator"]

    # 150 synthetic bars simulating SPY daily history
    import numpy as np
    from datetime import timedelta
    start_d = date(2026, 1, 1)
    dates = pd.to_datetime([start_d + timedelta(days=i) for i in range(150)])
    closes = 500.0 + np.cumsum(np.linspace(0.1, 0.5, 150))
    mock_df = pd.DataFrame(
        {
            "Open": closes - 0.5,
            "High": closes + 1.2,
            "Low": closes - 1.0,
            "Close": closes,
            "Volume": np.full(150, 40000000.0),
        },
        index=dates,
    )

    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.return_value = mock_df
        mock_ticker.return_value = mock_instance

        bars = provider.fetch_daily_bars("SPY", date(2026, 1, 1), date(2026, 6, 1))
        assert len(bars) == 150

        # Convert bars into DataFrame expected by calculate_indicators
        df = pd.DataFrame([
            {
                "trade_date": b.trade_date,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ])
        result = calculate_indicators(df, indicator_cfg)
        assert result is not None
        assert len(result.values) >= 50
        assert "kdj_k" in result.values
