"""Small, fail-closed HTTP adapter for the read-only FTShare ETF endpoints.

The user-facing FTShare Skill is intentionally not imported or executed here.
Only the three pinned endpoint paths below can be requested, and all upstream
values are treated as untrusted input until they pass the record validators.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from app.core.config import Settings, get_settings
from app.providers.base import CapabilityUnavailable, MarketProvider, ProviderError
from app.providers.types import BarRecord, InstrumentRecord, QuoteRecord

logger = logging.getLogger(__name__)

LIST_ENDPOINT = "/api/v1/market/data/etf-description-all"
OHLC_ENDPOINT = "/api/v1/market/data/daec/history/ohlcs"
PRICES_ENDPOINT = "/api/v1/market/data/daec/history/prices"

_CODE_RE = re.compile(r"^(\d{6})(?:\.([A-Z]{2,5}))?$")
_ALLOWED_EXCHANGES = {"SH", "SZ", "BJ", "XSHG", "XSHE", "XBSE"}
_ETF_KIND_VALUES = {"ETF", "EXCHANGE TRADED FUND", "EXCHANGE-TRADED FUND"}
_ALLOWED_METADATA_SOURCES = frozenset({"ftshare", "market.ft.tech"})
_SOURCE_TIME_TOLERANCE = timedelta(seconds=60)
_MIN_TIMESTAMP_MS = 946684800000  # 2000-01-01, before ETF history in this app
_MAX_TIMESTAMP_MS = 4102444800000  # 2100-01-01, bounds conversion and future data
_SAFE_TRANSPORT_LABELS = frozenset({"TimeoutException", "HTTPError", "RuntimeError", "ValueError", "TypeError", "OSError"})
_DAILY_SOURCE_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
_MAX_VOLUME_SHARES = 10**15


def normalize_code(value: object) -> str:
    """Normalize provider exchange suffixes to the app's SH/SZ/BJ form."""
    text = str(value or "").strip().upper()
    match = _CODE_RE.fullmatch(text)
    if not match:
        raise ValueError("invalid instrument code")
    symbol, exchange = match.groups()
    if exchange:
        if exchange not in _ALLOWED_EXCHANGES:
            raise ValueError("invalid instrument exchange")
        exchange = {"XSHG": "SH", "XSHE": "SZ", "XBSE": "BJ"}.get(exchange, exchange)
    else:
        if symbol.startswith(("5", "6")):
            exchange = "SH"
        elif symbol.startswith(("0", "1", "2", "3")):
            exchange = "SZ"
        elif symbol.startswith(("4", "8", "9")):
            exchange = "BJ"
        else:
            raise ValueError("cannot infer instrument exchange")
    return f"{symbol}.{exchange}"


def _finite(value: object, *, required: bool = True) -> float | None:
    if value is None or value == "":
        if required:
            raise ValueError("missing numeric field")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid numeric field") from exc
    if not math.isfinite(number):
        raise ValueError("non-finite numeric field")
    return number


def _shares(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("volume must be integer shares")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        raise ValueError("volume must be integer shares")
    if number < 0 or number > _MAX_VOLUME_SHARES:
        raise ValueError("volume out of bounds")
    return number


def _bounded_pct(current: float, previous: float | None) -> float | None:
    if previous is None or previous <= 0:
        return None
    value = (current / previous - 1) * 100
    if not math.isfinite(value) or abs(value) > 100:
        raise ProviderError("derived percent out of bounds")
    return value


def _parse_day(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if text.isdigit() and len(text) >= 13:
        return _parse_timestamp(text).date()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.date()
        except ValueError:
            continue
    raise ValueError("invalid date field")


def _parse_timestamp(value: object) -> datetime:
    try:
        if isinstance(value, datetime):
            parsed = value if value.tzinfo else value.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        elif isinstance(value, int) and not isinstance(value, bool):
            number = value
            if not _MIN_TIMESTAMP_MS <= number <= _MAX_TIMESTAMP_MS:
                raise ValueError("non-finite timestamp")
            parsed = datetime.fromtimestamp(number / 1000, tz=ZoneInfo("Asia/Shanghai"))
        elif isinstance(value, str) and value.strip().isdigit():
            number = int(value.strip())
            if not _MIN_TIMESTAMP_MS <= number <= _MAX_TIMESTAMP_MS:
                raise ValueError("timestamp out of bounds")
            parsed = datetime.fromtimestamp(number / 1000, tz=ZoneInfo("Asia/Shanghai"))
        else:
            text = str(value or "").strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return parsed.astimezone(ZoneInfo("Asia/Shanghai"))
    except (OSError, OverflowError, TypeError, ValueError) as exc:
        raise ValueError("invalid source timestamp") from exc


def _validate_source_timestamp(value: object, *, now: datetime) -> datetime:
    timestamp = _parse_timestamp(value)
    if timestamp > now + _SOURCE_TIME_TOLERANCE:
        raise ValueError("future source timestamp")
    return timestamp


def _parse_millis(value: object) -> datetime:
    if isinstance(value, bool) or (not isinstance(value, int) and not (isinstance(value, str) and value.strip().isdigit())):
        raise ValueError("timestamp must be integer milliseconds")
    number = value if isinstance(value, int) else int(value.strip())
    if not _MIN_TIMESTAMP_MS <= number <= _MAX_TIMESTAMP_MS:
        raise ValueError("timestamp out of bounds")
    try:
        return datetime.fromtimestamp(number / 1000, tz=ZoneInfo("Asia/Shanghai"))
    except (OSError, OverflowError, ValueError) as exc:
        raise ValueError("invalid timestamp") from exc


def _parse_daily_source_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not _DAILY_SOURCE_TS_RE.fullmatch(value):
        raise ValueError("daily timestamp must be Beijing ISO")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid daily timestamp") from exc


class FTShareProvider(MarketProvider):
    name = "ftshare"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.ftshare_enabled:
            raise CapabilityUnavailable("FTShare provider is disabled")
        if client is not None and http_client is not None:
            raise ProviderError("FTShare client specified more than once")
        client = http_client or client
        parsed = urlparse(self.settings.ftshare_base_url)
        try:
            hostname = parsed.hostname.lower() if parsed.hostname else ""
            port = parsed.port
        except ValueError as exc:
            raise ProviderError("FTShare base URL rejected") from exc
        fixed_host = hostname == "market.ft.tech" and port in (None, 443)
        custom_allowed = (
            self.settings.ftshare_allow_custom_base_url
            and self.settings.app_env in {"development", "test"}
        )
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/gateway"
            or not (fixed_host or custom_allowed)
        ):
            raise ProviderError("FTShare base URL rejected")
        # Strip a harmless trailing slash and preserve a test-only custom host.
        self.base_url = f"{parsed.scheme}://{parsed.netloc}/gateway"
        self.tz = ZoneInfo(self.settings.timezone_name)
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=self.settings.ftshare_timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> FTShareProvider:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - best effort interpreter cleanup
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def _code_from_row(row: dict[str, Any]) -> str:
        return normalize_code(row.get("symbol") or row.get("ts_code") or row.get("code"))

    @staticmethod
    def _required_row_code(row: dict[str, Any]) -> str:
        value = row.get("symbol")
        if value is None:
            value = row.get("ts_code")
        if value is None:
            value = row.get("code")
        if value is None:
            raise ValueError("row instrument code missing")
        return normalize_code(value)

    @staticmethod
    def _optional_row_code(row: dict[str, Any]) -> str | None:
        """Validate optional response symbols without requiring Skill-omitted fields."""
        values = [row[key] for key in ("symbol", "ts_code", "code") if key in row]
        if not values:
            return None
        normalized = {normalize_code(value) for value in values}
        if len(normalized) != 1:
            raise ValueError("row instrument codes disagree")
        return normalized.pop()

    @staticmethod
    def _optional_row_day(row: dict[str, Any], timestamp_day: date) -> date:
        """Use the request-bound timestamp day when the Skill omits trade_date."""
        values = [row[key] for key in ("trade_date", "date") if key in row]
        if not values:
            return timestamp_day
        parsed = {_parse_day(value) for value in values}
        if len(parsed) != 1:
            raise ValueError("row trade dates disagree")
        return parsed.pop()

    def _validate_envelope(self, response: httpx.Response, *, tool: str, operation: str, key: str) -> list[Any]:
        if response.status_code >= 400:
            code = ""
            try:
                body = response.json()
                if isinstance(body, dict):
                    error = body.get("error") if isinstance(body.get("error"), dict) else body
                    code = str(error.get("code") or "").upper() if isinstance(error, dict) else ""
            except (ValueError, TypeError):
                pass
            if code == "UPSTREAM_REJECTED":
                raise CapabilityUnavailable(
                    f"FTShare {operation} rejected by upstream",
                    safe_code="UPSTREAM_REJECTED",
                )
            raise ProviderError(f"FTShare {operation} HTTP request failed")
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            raise ProviderError(f"FTShare {operation} returned invalid JSON") from exc
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            if str(body["error"].get("code") or "").upper() == "UPSTREAM_REJECTED":
                raise CapabilityUnavailable(
                    f"FTShare {operation} rejected by upstream",
                    safe_code="UPSTREAM_REJECTED",
                )
            raise ProviderError(f"FTShare {operation} returned an upstream error")
        if isinstance(body, list):
            payload = body
        elif isinstance(body, dict):
            metadata = body.get("metadata") or body.get("meta")
            if not isinstance(metadata, dict):
                raise ProviderError(f"FTShare {operation} metadata missing")
            source = str(metadata.get("source") or "")
            if source not in _ALLOWED_METADATA_SOURCES:
                raise ProviderError(f"FTShare {operation} metadata source invalid")
            if str(metadata.get("tool") or "") != tool:
                raise ProviderError(f"FTShare {operation} metadata tool invalid")
            if str(metadata.get("operation") or "") != operation:
                raise ProviderError(f"FTShare {operation} metadata operation invalid")
            # The pinned scripts document both bare arrays and the endpoint's
            # native {ohlcs}/{prices} wrappers.  Require provenance whenever a
            # generic envelope is used, so metadata cannot be silently lost.
            payload = body.get(key)
            if payload is None and "data" in body:
                payload = body.get("data")
            if not isinstance(payload, list):
                raise ProviderError(f"FTShare {operation} response shape invalid")
            if operation == "fetch_daily_bars":
                adjustment = metadata.get("adjustment") or metadata.get("adjust")
                if adjustment is not None and str(adjustment).strip().lower() not in {"none", "unadjusted"}:
                    raise ProviderError(f"FTShare {operation} adjustment provenance invalid")
            pagination = body.get("pagination")
            if pagination is not None:
                if not isinstance(pagination, dict):
                    raise ProviderError(f"FTShare {operation} pagination invalid")
                def positive_int(field: str) -> int | None:
                    value = pagination.get(field)
                    if value is None:
                        return None
                    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                        raise ProviderError(f"FTShare {operation} pagination invalid")
                    return value

                page = positive_int("page")
                pages = positive_int("pages")
                if pages is None:
                    pages = positive_int("total_pages")
                if pages is not None and pages > self.settings.ftshare_max_pages:
                    raise CapabilityUnavailable(f"FTShare {operation} pagination exceeds bound")
                if page is not None and pages is not None and page > pages:
                    raise ProviderError(f"FTShare {operation} pagination invalid")
                if page is not None and page > self.settings.ftshare_max_pages:
                    raise CapabilityUnavailable(f"FTShare {operation} pagination exceeds bound")
                truncated = pagination.get("truncated")
                has_next = pagination.get("has_next")
                if (truncated is not None and not isinstance(truncated, bool)) or (
                    has_next is not None and not isinstance(has_next, bool)
                ):
                    raise ProviderError(f"FTShare {operation} pagination invalid")
                if truncated or has_next:
                    raise CapabilityUnavailable(f"FTShare {operation} response truncated")
            warnings = body.get("warnings")
            if warnings is not None and not isinstance(warnings, list):
                raise ProviderError(f"FTShare {operation} warnings invalid")
            if warnings:
                raise CapabilityUnavailable(f"FTShare {operation} returned warnings")
        else:
            raise ProviderError(f"FTShare {operation} response envelope invalid")
        if len(payload) > self.settings.ftshare_max_rows:
            raise CapabilityUnavailable(f"FTShare {operation} response exceeds row bound")
        if not payload:
            raise CapabilityUnavailable(f"FTShare {operation} returned no records")
        return payload

    def _get(self, endpoint: str, *, params: dict[str, str], tool: str, operation: str, key: str) -> list[Any]:
        # endpoint and parameter names are constants in this module; callers
        # cannot provide an arbitrary URL or tool name.
        expected = {
            LIST_ENDPOINT: "etf-description-all",
            OHLC_ENDPOINT: "etf-ohlcs",
            PRICES_ENDPOINT: "etf-prices",
        }.get(endpoint)
        if expected is None or tool != expected:
            raise ProviderError("FTShare endpoint is not allowlisted")
        try:
            with self.client.stream(
                "GET",
                f"{self.base_url}{endpoint}",
                params=params,
                headers={"Accept": "application/json", "X-Client-Name": "ft-claw"},
                timeout=self.settings.ftshare_timeout_seconds,
                follow_redirects=False,
            ) as response:
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > self.settings.ftshare_max_response_bytes:
                        raise CapabilityUnavailable(f"FTShare {operation} response exceeds byte bound")
                    chunks.append(chunk)
                response = httpx.Response(
                    response.status_code,
                    headers=response.headers,
                    content=b"".join(chunks),
                )
            return self._validate_envelope(response, tool=tool, operation=operation, key=key)
        except httpx.TimeoutException as exc:
            logger.warning("FTShare %s failed: TimeoutException", operation)
            raise CapabilityUnavailable(f"FTShare {operation} timed out") from exc
        except httpx.HTTPError as exc:
            logger.warning("FTShare %s failed: HTTPError", operation)
            raise CapabilityUnavailable(f"FTShare {operation} unavailable") from exc
        except (KeyboardInterrupt, SystemExit):
            raise
        except (CapabilityUnavailable, ProviderError):
            raise
        except Exception as exc:
            label = type(exc).__name__ if type(exc).__name__ in _SAFE_TRANSPORT_LABELS else "ProviderError"
            logger.warning("FTShare %s failed: %s", operation, label)
            raise ProviderError(f"FTShare {operation} transport failure") from None

    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        wanted = {normalize_code(code) for code in codes} if codes else None
        rows = self._get(LIST_ENDPOINT, params={}, tool="etf-description-all", operation="list_instruments", key="data")
        result: list[InstrumentRecord] = []
        seen: set[str] = set()
        for raw in rows:
            if not isinstance(raw, dict):
                raise ProviderError("FTShare list_instruments row invalid")
            try:
                code = self._code_from_row(raw)
            except ValueError as exc:
                raise ProviderError("FTShare list_instruments code invalid") from exc
            if code in seen:
                raise ProviderError("FTShare list_instruments duplicate code")
            seen.add(code)
            kind = str(raw.get("kind") or raw.get("type") or raw.get("security_type") or "ETF").strip().upper()
            if kind not in _ETF_KIND_VALUES:
                continue
            name = str(raw.get("name") or "").strip()
            if not name:
                raise ProviderError("FTShare list_instruments name missing")
            if wanted and code not in wanted:
                continue
            result.append(
                InstrumentRecord(
                    ts_code=code,
                    symbol=code.split(".")[0],
                    name=name,
                    kind="ETF",
                    exchange=code.split(".")[1],
                    enabled=True,
                    metadata={"provider": self.name},
                )
            )
        if not result:
            raise CapabilityUnavailable("FTShare list_instruments returned no ETF records")
        return result

    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        code = normalize_code(ts_code)
        if start_date > end_date:
            raise ProviderError("FTShare daily date range invalid")
        if (end_date - start_date).days > self.settings.ftshare_max_date_span_days:
            raise CapabilityUnavailable("FTShare daily date range exceeds bound")
        rows = self._get(
            OHLC_ENDPOINT,
            params={
                "symbol": code.replace(".SH", ".XSHG").replace(".SZ", ".XSHE").replace(".BJ", ".XBSE"),
                "since": start_date.strftime("%Y%m%d"),
                "until": end_date.strftime("%Y%m%d"),
                "interval": "Day",
                "adjust": "None",
            },
            tool="etf-ohlcs",
            operation="fetch_daily_bars",
            key="ohlcs",
        )
        result: list[BarRecord] = []
        seen: set[date] = set()
        now = datetime.now(self.tz)
        today = now.date()
        for raw in rows:
            if not isinstance(raw, dict):
                raise ProviderError("FTShare daily row invalid")
            try:
                row_code = self._optional_row_code(raw)
                if row_code is not None and row_code != code:
                    raise ValueError("daily row instrument mismatch")
                if "open_ts_ms" not in raw or "close_ts_ms" not in raw:
                    raise ValueError("daily timestamps missing")
                open_timestamp = _parse_daily_source_timestamp(raw["open_ts_ms"])
                close_timestamp = _parse_daily_source_timestamp(raw["close_ts_ms"])
                if open_timestamp > close_timestamp:
                    raise ValueError("daily timestamps reversed")
                if open_timestamp > now + _SOURCE_TIME_TOLERANCE or close_timestamp > now + _SOURCE_TIME_TOLERANCE:
                    raise ValueError("future source timestamp")
                if open_timestamp.date() != close_timestamp.date():
                    raise ValueError("daily timestamps span multiple dates")
                day = self._optional_row_day(raw, open_timestamp.date())
                if open_timestamp.date() != day:
                    raise ValueError("daily timestamp date mismatch")
                if day < start_date or day > end_date or day > today or day in seen:
                    raise ValueError("daily date outside range or duplicate")
                open_price = _finite(raw.get("open"))
                high = _finite(raw.get("high"))
                low = _finite(raw.get("low"))
                close = _finite(raw.get("close"))
                volume = _shares(raw.get("volume"))
                amount = _finite(raw.get("turnover") if raw.get("turnover") is not None else raw.get("amount"))
                if min(open_price, high, low, close) <= 0 or high < max(open_price, close) or low > min(open_price, close):
                    raise ValueError("daily OHLC relationship invalid")
                if volume < 0 or amount < 0:
                    raise ValueError("daily volume/amount invalid")
            except (TypeError, ValueError) as exc:
                raise ProviderError("FTShare daily row validation failed") from exc
            seen.add(day)
            result.append(
                BarRecord(
                    ts_code=code,
                    trade_date=day,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    pre_close=None,
                    volume=volume,
                    amount=amount,
                    pct_change=None,
                    adjust="none",
                    source="ftshare:fetch_daily_bars",
                )
            )
        result.sort(key=lambda item: item.trade_date)
        previous_close: float | None = None
        for item in result:
            item.pre_close = previous_close
            item.pct_change = _bounded_pct(item.close, previous_close)
            previous_close = item.close
        return result

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        if not codes:
            raise CapabilityUnavailable("FTShare spot quotes require ETF codes")
        result: list[QuoteRecord] = []
        seen: set[str] = set()
        now = datetime.now(self.tz)
        for raw_code in codes:
            code = normalize_code(raw_code)
            if code in seen:
                raise ProviderError("FTShare spot duplicate code")
            seen.add(code)
            rows = self._get(
                PRICES_ENDPOINT,
                params={
                    "symbol": code.replace(".SH", ".XSHG").replace(".SZ", ".XSHE").replace(".BJ", ".XBSE"),
                    "range": "Today",
                },
                tool="etf-prices",
                operation="fetch_spot_quotes",
                key="prices",
            )
            latest: tuple[datetime, dict[str, Any]] | None = None
            for row in rows:
                if not isinstance(row, dict):
                    raise ProviderError("FTShare spot row invalid")
                try:
                    # Requests are intentionally one ETF per call, so a Skill
                    # row without a code is safely bound to this request.  Do
                    # not add a positional/batch mapping for multi-code input.
                    row_code = self._optional_row_code(row)
                    if row_code is not None and row_code != code:
                        raise ValueError("spot row instrument mismatch")
                    timestamp_value = row.get("ts_ms") if "ts_ms" in row else row.get("timestamp")
                    timestamp = _validate_source_timestamp(timestamp_value, now=now)
                    price = _finite(row.get("price"))
                    open_price = _finite(row.get("open"), required=False)
                    high = _finite(row.get("high"), required=False)
                    low = _finite(row.get("low"), required=False)
                    volume = _shares(row.get("volume"))
                    amount = _finite(row.get("turnover") if row.get("turnover") is not None else row.get("amount"))
                    if price <= 0 or volume < 0 or amount < 0:
                        raise ValueError("spot value invalid")
                    if open_price is not None and open_price <= 0:
                        raise ValueError("spot open invalid")
                    if high is not None and (high <= 0 or high < max(price, open_price or price)):
                        raise ValueError("spot high relationship invalid")
                    if low is not None and (low <= 0 or low > min(price, open_price if open_price is not None else price)):
                        raise ValueError("spot low relationship invalid")
                except (OSError, OverflowError, TypeError, ValueError) as exc:
                    raise ProviderError("FTShare spot row validation failed") from exc
                if latest is None or timestamp > latest[0]:
                    latest = (timestamp, row)
            if latest is None:
                raise CapabilityUnavailable("FTShare spot quote missing")
            timestamp, row = latest
            pre_close = _finite(row.get("pre_close"), required=False)
            if pre_close is not None and pre_close < 0:
                raise ProviderError("FTShare spot row validation failed")
            result.append(
                QuoteRecord(
                    ts_code=code,
                    quote_time=timestamp,
                    price=_finite(row.get("price")),
                    open=_finite(row.get("open"), required=False),
                    high=_finite(row.get("high"), required=False),
                    low=_finite(row.get("low"), required=False),
                    pre_close=pre_close,
                    pct_change=_bounded_pct(_finite(row.get("price")), pre_close),
                    volume=_shares(row.get("volume")),
                    amount=_finite(row.get("turnover") if row.get("turnover") is not None else row.get("amount")),
                    source="ftshare:fetch_spot_quotes",
                    is_realtime=False,
                    degraded_reason="FTShare source timestamp is not yet qualified for realtime use",
                )
            )
        return result
