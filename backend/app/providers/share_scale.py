"""Free exchange share-scale reads for ETF/LOF 申赎 research.

Shanghai uses ``fund_etf_scale_sse`` (one date per call). Shenzhen prefers
``fund_scale_daily_szse`` and only falls back to ``fund_etf_scale_szse`` when
the daily helper is missing. AKShare already normalizes both helpers to 份;
this module does not apply a second unit conversion. A snapshot without a
trade date is not persisted and is not assigned "today".
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.bounded_sdk import first
from app.providers.types import ShareScaleRecord
from app.utils.numbers import finite_or_none

logger = logging.getLogger(__name__)

SSE_SOURCE = "akshare:fund_etf_scale_sse"
SZSE_DAILY_SOURCE = "akshare:fund_scale_daily_szse"
SZSE_SNAPSHOT_SOURCE = "akshare:fund_etf_scale_szse"
ALLOWED_SOURCES = frozenset({SSE_SOURCE, SZSE_DAILY_SOURCE, SZSE_SNAPSHOT_SOURCE})
MAX_WINDOW_DAYS = 12

_DATE_KEYS = ("统计日期", "日期", "trade_date")
_CODE_KEYS = ("基金代码", "代码", "symbol")
_SHARE_KEYS = ("基金份额", "最新份额", "shares")
_NAME_KEYS = ("基金简称", "名称", "name")


def fetch_share_scales(
    ak: Any,
    codes: list[str],
    start_date: date,
    end_date: date,
) -> list[ShareScaleRecord]:
    if end_date < start_date or (end_date - start_date).days > MAX_WINDOW_DAYS - 1:
        raise ProviderError("share_scale_window_invalid")
    wanted = _wanted(codes)
    if not wanted:
        return []
    sh_symbols = {symbol for symbol, ts_code in wanted.items() if ts_code.endswith(".SH")}
    sz_symbols = {symbol for symbol, ts_code in wanted.items() if ts_code.endswith(".SZ")}
    rows: list[ShareScaleRecord] = []
    errors: list[str] = []
    if sh_symbols:
        rows.extend(_fetch_sse(ak, wanted, start_date, end_date, errors))
    if sz_symbols:
        rows.extend(_fetch_szse(ak, wanted, start_date, end_date, errors))
    rows = _dedupe(rows)
    if rows:
        if errors:
            logger.warning("share scale partial: %s", ",".join(errors))
        return rows
    if errors and all(item.endswith(":missing") for item in errors):
        raise CapabilityUnavailable("share_scale_endpoint_unavailable")
    if any("undated" in item for item in errors):
        raise ProviderError("share_scale_undated_or_unavailable")
    if errors:
        raise ProviderError("share_scale_fetch_failed")
    raise ProviderError("share_scale_empty")


def _wanted(codes: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in codes:
        ts_code = str(raw or "").strip().upper()
        symbol = _symbol(ts_code.split(".")[0])
        if len(symbol) != 6 or not ts_code.endswith((".SH", ".SZ")):
            continue
        result[symbol] = ts_code
    return result


def _fetch_sse(ak: Any, wanted: dict[str, str], start: date, end: date, errors: list[str]) -> list[ShareScaleRecord]:
    function = getattr(ak, "fund_etf_scale_sse", None)
    if function is None:
        errors.append("fund_etf_scale_sse:missing")
        return []
    rows: list[ShareScaleRecord] = []
    day = start
    while day <= end:
        try:
            frame = function(date=day.strftime("%Y%m%d"))
        except TypeError:
            try:
                frame = function(day.strftime("%Y%m%d"))
            except Exception as exc:
                errors.append(f"fund_etf_scale_sse:{type(exc).__name__}")
                day += timedelta(days=1)
                continue
        except Exception as exc:
            errors.append(f"fund_etf_scale_sse:{type(exc).__name__}")
            day += timedelta(days=1)
            continue
        rows.extend(_parse_frame(frame, wanted, SSE_SOURCE, "SH", default_date=day))
        day += timedelta(days=1)
    return rows


def _fetch_szse(ak: Any, wanted: dict[str, str], start: date, end: date, errors: list[str]) -> list[ShareScaleRecord]:
    daily = getattr(ak, "fund_scale_daily_szse", None)
    if daily is not None:
        rows: list[ShareScaleRecord] = []
        symbols = _szse_symbols(wanted)
        failed = False
        for symbol in symbols:
            try:
                frame = daily(
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    symbol=symbol,
                )
            except Exception as exc:
                errors.append(f"fund_scale_daily_szse:{type(exc).__name__}")
                failed = True
                continue
            rows.extend(_parse_frame(frame, wanted, SZSE_DAILY_SOURCE, "SZ"))
        if rows or not failed:
            return rows
    else:
        errors.append("fund_scale_daily_szse:missing")
    snapshot = getattr(ak, "fund_etf_scale_szse", None)
    if snapshot is None:
        errors.append("fund_etf_scale_szse:missing")
        return []
    try:
        frame = snapshot()
    except Exception as exc:
        errors.append(f"fund_etf_scale_szse:{type(exc).__name__}")
        return []
    dated = _parse_frame(frame, wanted, SZSE_SNAPSHOT_SOURCE, "SZ", require_explicit_date=True)
    if dated:
        return dated
    if _records(frame):
        errors.append("fund_etf_scale_szse:undated_snapshot")
    return []


def _szse_symbols(wanted: dict[str, str]) -> list[str]:
    symbols: list[str] = []
    sz = [symbol for symbol, ts_code in wanted.items() if ts_code.endswith(".SZ")]
    if any(not symbol.startswith("16") for symbol in sz):
        symbols.append("ETF")
    if any(symbol.startswith("16") for symbol in sz):
        symbols.append("LOF")
    return symbols


def _parse_frame(
    frame: Any,
    wanted: dict[str, str],
    source: str,
    exchange: str,
    *,
    default_date: date | None = None,
    require_explicit_date: bool = False,
) -> list[ShareScaleRecord]:
    rows: list[ShareScaleRecord] = []
    for raw in _records(frame):
        symbol = _symbol(first(raw, *_CODE_KEYS))
        ts_code = wanted.get(symbol)
        if ts_code is None or not ts_code.endswith(f".{exchange}"):
            continue
        explicit = _as_date(first(raw, *_DATE_KEYS))
        if require_explicit_date and explicit is None:
            continue
        trade_date = explicit or default_date
        shares = finite_or_none(first(raw, *_SHARE_KEYS))
        if trade_date is None or shares is None or shares < 0:
            continue
        name = first(raw, *_NAME_KEYS)
        rows.append(
            ShareScaleRecord(
                ts_code=ts_code,
                trade_date=trade_date,
                shares=float(shares),
                source=source,
                exchange=exchange,
                name=str(name).strip() if name else None,
            )
        )
    return rows


def _dedupe(rows: list[ShareScaleRecord]) -> list[ShareScaleRecord]:
    selected: dict[tuple[str, date, str], ShareScaleRecord] = {}
    for row in rows:
        if row.source not in ALLOWED_SOURCES or "mock" in row.source.lower():
            continue
        key = (row.ts_code, row.trade_date, row.source)
        current = selected.get(key)
        if current is not None and current.shares != row.shares:
            raise ProviderError("share_scale_duplicate_conflict")
        selected[key] = row
    return list(selected.values())


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        records = frame.to_dict(orient="records")
        return [dict(row) for row in records]
    return [dict(row) for row in frame]


def _symbol(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float):
        if not value.is_integer():
            return ""
        value = int(value)
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) < 6:
        return ""
    return digits[-6:]


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text or text.lower() in {"nat", "none", "nan", "null"}:
        return None
    text = text[:10].replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
