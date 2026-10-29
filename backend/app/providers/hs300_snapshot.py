"""Free public snapshots for the HS300 passive-holdings ratio research.

Three datasets, each with a different date contract:

* ``index_stock_cons_csindex`` — official constituent list. Carries the list
  (rebalance) date, not a valuation date.
* ``stock_zh_a_spot_em`` — whole-market market cap in 元. Carries **no**
  upstream trade date, so the adapter stamps ``observed_at`` with the local
  collection time. It is a same-day snapshot and must never be back-dated.
* ``fund_etf_fund_daily_em`` — exchange-traded fund NAV. The NAV date lives
  inside the column name (``YYYY-MM-DD-单位净值``), so the newest dated column
  is selected instead of assuming "today".

Nothing here computes a signal, and no helper substitutes a missing value.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.bounded_sdk import first
from app.providers.types import (
    FundNavRecord,
    IndexConstituentRecord,
    InstrumentRecord,
    StockMarketCapRecord,
    StockMarketCapSnapshot,
)
from app.utils.numbers import finite_or_none

logger = logging.getLogger(__name__)

CONSTITUENT_SOURCE = "akshare:index_stock_cons_csindex"
MARKET_CAP_SOURCE = "akshare:stock_zh_a_spot_em"
FUND_NAV_SOURCE = "akshare:fund_etf_fund_daily_em"

_NAV_COLUMN = re.compile(r"^(\d{4}-\d{2}-\d{2})-单位净值$")


def fetch_index_constituents(ak: Any, index_code: str) -> list[IndexConstituentRecord]:
    symbol = _index_symbol(index_code)
    function = getattr(ak, "index_stock_cons_csindex", None)
    if function is None:
        raise CapabilityUnavailable("index_constituent_endpoint_unavailable")
    try:
        frame = function(symbol=symbol)
    except TypeError:
        frame = function(symbol)
    except Exception as exc:  # transport/dependency failure, never echoed raw
        logger.warning("index_stock_cons_csindex failed: %s", type(exc).__name__)
        raise ProviderError("index_constituent_fetch_failed") from None

    rows: list[IndexConstituentRecord] = []
    for raw in _records(frame):
        ts_code = _stock_ts_code(first(raw, "成分券代码", "品种代码", "代码"))
        as_of = _as_date(first(raw, "日期", "更新日期"))
        if not ts_code or as_of is None:
            continue
        rows.append(
            IndexConstituentRecord(
                ts_code=ts_code,
                index_code=index_code.upper(),
                as_of=as_of,
                name=_text(first(raw, "成分券名称", "品种名称", "名称")),
                exchange=ts_code.split(".")[-1],
                source=CONSTITUENT_SOURCE,
            )
        )
    if not rows:
        raise ProviderError("index_constituent_empty")
    return _dedupe_constituents(rows)


def fetch_stock_float_market_caps(ak: Any, tz: ZoneInfo) -> StockMarketCapSnapshot:
    function = getattr(ak, "stock_zh_a_spot_em", None)
    if function is None:
        raise CapabilityUnavailable("stock_market_cap_endpoint_unavailable")
    observed_at = datetime.now(tz)
    try:
        frame = function()
    except Exception as exc:
        logger.warning("stock_zh_a_spot_em failed: %s", type(exc).__name__)
        raise ProviderError("stock_market_cap_fetch_failed") from None

    rows: list[StockMarketCapRecord] = []
    for raw in _records(frame):
        ts_code = _stock_ts_code(first(raw, "代码", "证券代码"))
        if not ts_code:
            continue
        total_mv = finite_or_none(first(raw, "总市值"))
        float_mv = finite_or_none(first(raw, "流通市值"))
        if float_mv is None or float_mv <= 0:
            # A suspended or newly listed stock can publish no float value.
            # Keep the row out instead of writing a zero that would understate
            # the denominator.
            continue
        rows.append(
            StockMarketCapRecord(
                ts_code=ts_code,
                total_mv=total_mv,
                float_mv=float_mv,
                name=_text(first(raw, "名称")),
                source=MARKET_CAP_SOURCE,
            )
        )
    if not rows:
        raise ProviderError("stock_market_cap_empty")
    return StockMarketCapSnapshot(observed_at=observed_at, source=MARKET_CAP_SOURCE, rows=rows)


def fetch_etf_nav_snapshot(ak: Any) -> list[FundNavRecord]:
    function = getattr(ak, "fund_etf_fund_daily_em", None)
    if function is None:
        raise CapabilityUnavailable("fund_nav_endpoint_unavailable")
    try:
        frame = function()
    except Exception as exc:
        logger.warning("fund_etf_fund_daily_em failed: %s", type(exc).__name__)
        raise ProviderError("fund_nav_fetch_failed") from None

    rows: list[FundNavRecord] = []
    for raw in _records(frame):
        ts_code = _fund_ts_code(first(raw, "基金代码", "代码"))
        if not ts_code:
            continue
        best: tuple[date, float] | None = None
        for column, value in raw.items():
            match = _NAV_COLUMN.match(str(column).strip())
            if match is None:
                continue
            nav = finite_or_none(value)
            nav_date = _as_date(match.group(1))
            if nav is None or nav <= 0 or nav_date is None:
                continue
            if best is None or nav_date > best[0]:
                best = (nav_date, nav)
        if best is None:
            continue
        rows.append(
            FundNavRecord(ts_code=ts_code, nav_date=best[0], nav=best[1], source=FUND_NAV_SOURCE)
        )
    if not rows:
        raise ProviderError("fund_nav_empty")
    return rows


def fetch_etf_catalog(ak: Any) -> list[InstrumentRecord]:
    """Enumerate exchange-traded ETFs for the one-off universe derivation.

    Names are returned verbatim. Matching a fund to 沪深300 stays an owner
    review step in the derivation script; the runtime never guesses by name.
    """
    function = getattr(ak, "fund_etf_spot_em", None)
    if function is None:
        raise CapabilityUnavailable("etf_catalog_endpoint_unavailable")
    try:
        frame = function()
    except Exception as exc:
        logger.warning("fund_etf_spot_em failed: %s", type(exc).__name__)
        raise ProviderError("etf_catalog_fetch_failed") from None

    rows: list[InstrumentRecord] = []
    for raw in _records(frame):
        ts_code = _fund_ts_code(first(raw, "代码", "基金代码"))
        name = _text(first(raw, "名称", "基金简称"))
        if not ts_code or not name:
            continue
        rows.append(
            InstrumentRecord(
                ts_code=ts_code,
                symbol=ts_code.split(".")[0],
                name=name,
                kind="ETF",
                exchange=ts_code.split(".")[-1],
                metadata={"provider": MARKET_CAP_SOURCE},
            )
        )
    if not rows:
        raise ProviderError("etf_catalog_empty")
    selected: dict[str, InstrumentRecord] = {}
    for row in rows:
        selected.setdefault(row.ts_code, row)
    return list(selected.values())


def _index_symbol(index_code: str) -> str:
    digits = "".join(ch for ch in str(index_code or "") if ch.isdigit())
    if len(digits) != 6:
        raise ProviderError("index_code_invalid")
    return digits


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return [dict(row) for row in frame.to_dict(orient="records")]
    return [dict(row) for row in frame]


def _dedupe_constituents(rows: list[IndexConstituentRecord]) -> list[IndexConstituentRecord]:
    selected: dict[str, IndexConstituentRecord] = {}
    for row in rows:
        selected.setdefault(row.ts_code, row)
    return list(selected.values())


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _digits(value: Any) -> str:
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
    return digits[-6:].zfill(6) if len(digits) >= 6 else ""


def _stock_ts_code(value: Any) -> str | None:
    symbol = _digits(value)
    if not symbol:
        return None
    if symbol.startswith("6"):
        return f"{symbol}.SH"
    if symbol.startswith(("0", "3")):
        return f"{symbol}.SZ"
    if symbol.startswith(("4", "8", "9")):
        return f"{symbol}.BJ"
    return None


def _fund_ts_code(value: Any) -> str | None:
    symbol = _digits(value)
    if not symbol:
        return None
    if symbol.startswith("5"):
        return f"{symbol}.SH"
    if symbol.startswith("1"):
        return f"{symbol}.SZ"
    return None


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
