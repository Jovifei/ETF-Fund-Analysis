from __future__ import annotations

import logging
from datetime import date, datetime, timezone
import math
from typing import Any

from app.core.config import Settings, get_settings
from app.providers.base import CapabilityUnavailable, MarketProvider, ProviderError
from app.providers.types import BarRecord, InstrumentRecord, QuoteRecord

logger = logging.getLogger(__name__)

# Standard US broad-market and factor ETFs
_DEFAULT_US_ETF_CATALOG: list[dict[str, Any]] = [
    {
        "symbol": "SPY",
        "name": "SPDR S&P 500 ETF Trust",
        "exchange": "NYSE",
        "theme_l1": "宽基",
        "theme_l2": "标普500",
        "benchmark": "S&P 500",
    },
    {
        "symbol": "QQQ",
        "name": "Invesco QQQ Trust",
        "exchange": "NASDAQ",
        "theme_l1": "科技成长",
        "theme_l2": "纳斯达克100",
        "benchmark": "NASDAQ-100",
    },
    {
        "symbol": "IWM",
        "name": "iShares Russell 2000 ETF",
        "exchange": "NYSE",
        "theme_l1": "小盘",
        "theme_l2": "罗素2000",
        "benchmark": "Russell 2000",
    },
    {
        "symbol": "VTI",
        "name": "Vanguard Total Stock Market ETF",
        "exchange": "NYSE",
        "theme_l1": "全市场",
        "theme_l2": "美股全市场",
        "benchmark": "CRSP US Total Market",
    },
    {
        "symbol": "GLD",
        "name": "SPDR Gold Shares",
        "exchange": "NYSE",
        "theme_l1": "大宗商品",
        "theme_l2": "黄金现货",
        "benchmark": "LBMA Gold Price",
    },
    {
        "symbol": "TLT",
        "name": "iShares 20+ Year Treasury Bond ETF",
        "exchange": "NASDAQ",
        "theme_l1": "固收",
        "theme_l2": "长期美债",
        "benchmark": "ICE US Treasury 20+ Year Bond",
    },
    {
        "symbol": "EFA",
        "name": "iShares MSCI EAFE ETF",
        "exchange": "NYSE",
        "theme_l1": "发达市场",
        "theme_l2": "欧澳远东",
        "benchmark": "MSCI EAFE",
    },
]


def _normalize_us_symbol(code: str) -> tuple[str, str]:
    """Normalize input symbol to (ticker, ts_code).

    Accepts 'SPY', 'SPY.US', 'spy' -> ('SPY', 'SPY.US')
    """
    raw = str(code or "").strip().upper()
    if raw.endswith(".US"):
        ticker = raw[:-3]
    else:
        ticker = raw
    return ticker, f"{ticker}.US"


class YFinanceProvider(MarketProvider):
    """US ETF Market Data Provider via Yahoo Finance.

    Provides non-realtime daily bars and quotes for US ETFs for local research.
    Per AGENTS.md rules, all quotes are marked non-realtime (is_realtime=False)
    and currencies are explicit USD.
    """

    name = "yfinance"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._catalog_map = {item["symbol"]: item for item in _DEFAULT_US_ETF_CATALOG}

    def is_trade_day(self, day: date) -> bool:
        # Standard US market trading days (Monday to Friday, ignoring federal holidays for basic check)
        return day.weekday() < 5

    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        results: list[InstrumentRecord] = []
        filter_tickers = {c.upper().replace(".US", "") for c in codes} if codes else None
        for item in _DEFAULT_US_ETF_CATALOG:
            if filter_tickers and item["symbol"] not in filter_tickers:
                continue
            results.append(
                InstrumentRecord(
                    ts_code=f"{item['symbol']}.US",
                    symbol=item["symbol"],
                    name=item["name"],
                    kind="ETF",
                    exchange=item["exchange"],
                    theme_l1=item.get("theme_l1"),
                    theme_l2=item.get("theme_l2"),
                    benchmark=item.get("benchmark"),
                    enabled=True,
                    metadata={"market": "US", "currency": "USD", "provider": "yfinance"},
                )
            )
        return results

    def resolve_instrument(self, code: str) -> InstrumentRecord | None:
        ticker, ts_code = _normalize_us_symbol(code)
        item = self._catalog_map.get(ticker)
        if not item:
            return None
        return InstrumentRecord(
            ts_code=ts_code,
            symbol=ticker,
            name=item["name"],
            kind="ETF",
            exchange=item["exchange"],
            theme_l1=item.get("theme_l1"),
            theme_l2=item.get("theme_l2"),
            benchmark=item.get("benchmark"),
            enabled=True,
            metadata={"market": "US", "currency": "USD", "provider": "yfinance"},
        )

    def fetch_daily_bars(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> list[BarRecord]:
        ticker, normalized_code = _normalize_us_symbol(ts_code)
        try:
            import yfinance as yf
        except ImportError:
            raise CapabilityUnavailable("yfinance library is not installed")

        try:
            t = yf.Ticker(ticker)
            # Fetch with auto adjustment for split/dividend continuity
            df = t.history(
                start=start_date.isoformat(),
                end=end_date.isoformat() if end_date != start_date else None,
                auto_adjust=True,
            )
        except Exception as exc:
            logger.error("yfinance fetch error for %s: %s", ticker, exc)
            raise ProviderError(f"yfinance fetch failed for {ticker}") from exc

        if df is None or df.empty:
            return []

        bars: list[BarRecord] = []
        prev_close: float | None = None

        # Sort by index date ascending
        df = df.sort_index(ascending=True)

        for idx, row in df.iterrows():
            # Date can be Timestamp with or without timezone
            if hasattr(idx, "date"):
                bar_date = idx.date()
            else:
                bar_date = date.fromisoformat(str(idx)[:10])

            open_val = row.get("Open")
            high_val = row.get("High")
            low_val = row.get("Low")
            close_val = row.get("Close")
            vol_val = row.get("Volume", 0)

            if any(v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) for v in (open_val, high_val, low_val, close_val)):
                continue

            open_f = round(float(open_val), 4)
            high_f = round(float(high_val), 4)
            low_f = round(float(low_val), 4)
            close_f = round(float(close_val), 4)
            vol_f = float(vol_val) if vol_val and not math.isnan(float(vol_val)) else 0.0

            pct_change: float | None = None
            if prev_close and prev_close > 0:
                pct_change = round((close_f - prev_close) / prev_close * 100.0, 4)

            bars.append(
                BarRecord(
                    ts_code=normalized_code,
                    trade_date=bar_date,
                    open=open_f,
                    high=high_f,
                    low=low_f,
                    close=close_f,
                    pre_close=prev_close,
                    volume=vol_f,
                    amount=None,
                    pct_change=pct_change,
                    adjust="qfq",
                    source="yfinance",
                )
            )
            prev_close = close_f

        return bars

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        try:
            import yfinance as yf
        except ImportError:
            raise CapabilityUnavailable("yfinance library is not installed")

        quotes: list[QuoteRecord] = []
        now_utc = datetime.now(timezone.utc)

        for code in codes:
            ticker, ts_code = _normalize_us_symbol(code)
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="2d", auto_adjust=True)
            except Exception as exc:
                logger.warning("Failed to fetch yfinance quote for %s: %s", ticker, exc)
                continue

            if hist is None or hist.empty:
                continue

            latest_row = hist.iloc[-1]
            close_val = latest_row.get("Close")
            if close_val is None or (isinstance(close_val, float) and math.isnan(close_val)):
                continue

            price = round(float(close_val), 4)
            open_f = round(float(latest_row.get("Open", price)), 4)
            high_f = round(float(latest_row.get("High", price)), 4)
            low_f = round(float(latest_row.get("Low", price)), 4)
            vol_f = float(latest_row.get("Volume", 0.0))

            pre_close: float | None = None
            pct_change: float | None = None
            if len(hist) >= 2:
                prev_row = hist.iloc[-2]
                prev_close_val = prev_row.get("Close")
                if prev_close_val and not math.isnan(float(prev_close_val)):
                    pre_close = round(float(prev_close_val), 4)
                    if pre_close > 0:
                        pct_change = round((price - pre_close) / pre_close * 100.0, 4)

            quotes.append(
                QuoteRecord(
                    ts_code=ts_code,
                    quote_time=now_utc,
                    price=price,
                    open=open_f,
                    high=high_f,
                    low=low_f,
                    pre_close=pre_close,
                    pct_change=pct_change,
                    volume=vol_f,
                    amount=None,
                    is_realtime=False,
                    source="yfinance",
                )
            )

        return quotes
