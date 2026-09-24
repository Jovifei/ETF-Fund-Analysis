from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.core.config import Settings, get_settings
from app.providers.base import CapabilityUnavailable, MarketProvider, ProviderError
from app.providers.types import BarRecord, InstrumentRecord, QuoteRecord
from app.utils.numbers import finite_or_none

_QUOTE_LINE = re.compile(r'var\s+hq_str_(sh|sz)(\d{6})="([^"]*)";')
_MAX_RESPONSE_BYTES = 1_000_000


class SinaProvider(MarketProvider):
    """Bounded HTTPS Sina quote adapter; quantity fields stay unqualified."""

    name = "sina"

    def __init__(self, settings: Settings | None = None, *, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self.tz = ZoneInfo(self.settings.timezone_name)
        self.client = client or httpx.Client(timeout=6.0, follow_redirects=False)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        del codes
        raise CapabilityUnavailable("sina_catalog_unavailable")

    def fetch_daily_bars(self, ts_code: str, start_date, end_date) -> list[BarRecord]:
        del ts_code, start_date, end_date
        raise CapabilityUnavailable("sina_daily_history_unavailable")

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        requested: dict[str, str] = {}
        for code in codes:
            normalized = str(code or "").strip().upper()
            match = re.fullmatch(r"(\d{6})\.(SH|SZ)", normalized)
            if match:
                symbol, market = match.groups()
                requested[f"{market.lower()}{symbol}"] = normalized
        if not requested:
            raise CapabilityUnavailable("sina_quote_exchange_unavailable")

        try:
            with self.client.stream(
                "GET",
                "https://hq.sinajs.cn/list=" + ",".join(requested),
                headers={
                    "Referer": "https://finance.sina.com.cn/",
                    "User-Agent": "ETF-Research/1.0 (+private research display)",
                },
                timeout=6.0,
            ) as response:
                if response.status_code != 200:
                    raise ProviderError(
                        "sina_quote_upstream_rejected", safe_code="SINA_QUOTE_UPSTREAM_REJECTED"
                    )
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    content.extend(chunk)
                    if len(content) > _MAX_RESPONSE_BYTES:
                        raise ProviderError(
                            "sina_quote_response_too_large", safe_code="SINA_QUOTE_RESPONSE_TOO_LARGE"
                        )
        except httpx.TimeoutException:
            raise ProviderError(
                "sina_quote_timeout", safe_code="SINA_QUOTE_TIMEOUT"
            ) from None
        except httpx.RequestError:
            raise ProviderError(
                "sina_quote_transport_failed", safe_code="SINA_QUOTE_TRANSPORT_FAILED"
            ) from None

        try:
            body = bytes(content).decode("gb18030", errors="strict")
        except UnicodeDecodeError:
            raise ProviderError(
                "sina_quote_response_encoding_invalid", safe_code="SINA_QUOTE_RESPONSE_INVALID"
            ) from None

        matches = list(_QUOTE_LINE.finditer(body))
        if body.strip() and not matches:
            raise ProviderError(
                "sina_quote_response_schema_invalid", safe_code="SINA_QUOTE_RESPONSE_INVALID"
            )

        fetched_at = datetime.now(self.tz)
        result: list[QuoteRecord] = []
        for match in matches:
            ts_code = requested.get(f"{match.group(1)}{match.group(2)}")
            if ts_code is None:
                continue
            fields = match.group(3).split(",")
            if len(fields) <= 31:
                continue
            price = finite_or_none(fields[3])
            if price is None or price <= 0:
                continue
            pre_close = finite_or_none(fields[2])
            try:
                source_time = datetime.strptime(
                    f"{fields[30]} {fields[31]}", "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=self.tz)
            except ValueError:
                source_time = None
            result.append(QuoteRecord(
                ts_code=ts_code,
                quote_time=source_time or fetched_at,
                price=price,
                open=finite_or_none(fields[1]) or None,
                high=finite_or_none(fields[4]) or None,
                low=finite_or_none(fields[5]) or None,
                pre_close=pre_close if pre_close and pre_close > 0 else None,
                pct_change=(price / pre_close - 1) * 100 if pre_close and pre_close > 0 else None,
                volume=None,
                amount=None,
                premium_rate=None,
                source="sina:hq_sinajs:v1",
                is_realtime=source_time is not None,
                degraded_reason=None if source_time is not None else "source_timestamp_missing_observed_at_fetch",
            ))
        return result
