from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from app.market_context.contracts import MarketContextItem, MarketContextObservation

__all__ = [
    "InstrumentRecord",
    "BarRecord",
    "QuoteRecord",
    "NewsRecord",
    "SectorRecord",
    "ShareScaleRecord",
    "IndexConstituentRecord",
    "StockMarketCapRecord",
    "StockMarketCapSnapshot",
    "FundNavRecord",
    "MarketContextItem",
    "MarketContextObservation",
]


@dataclass(slots=True)
class InstrumentRecord:
    ts_code: str
    symbol: str
    name: str
    kind: str = "ETF"
    exchange: str | None = None
    theme_l1: str | None = None
    theme_l2: str | None = None
    benchmark: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BarRecord:
    ts_code: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    pre_close: float | None = None
    volume: float | None = None
    amount: float | None = None
    pct_change: float | None = None
    adjust: str = "none"
    source: str = "unknown"
    raw_volume: float | None = None
    raw_amount: float | None = None
    volume_raw_unit: str | None = None
    amount_raw_unit: str | None = None
    source_upstream: str | None = None
    endpoint_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuoteRecord:
    ts_code: str
    quote_time: datetime
    price: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    pre_close: float | None = None
    pct_change: float | None = None
    volume: float | None = None
    amount: float | None = None
    premium_rate: float | None = None
    source: str = "unknown"
    is_realtime: bool = False
    degraded_reason: str | None = None
    iopv: float | None = None
    latest_shares: float | None = None
    main_net_inflow: float | None = None
    super_large_net_inflow: float | None = None
    large_net_inflow: float | None = None
    medium_net_inflow: float | None = None
    small_net_inflow: float | None = None
    flow_contract: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ShareScaleRecord:
    """Exchange-published fund shares. Unit is 份 as returned by the AKShare helper."""

    ts_code: str
    trade_date: date
    shares: float
    source: str
    exchange: str
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IndexConstituentRecord:
    """Official index constituent list. ``as_of`` is the list/rebalance date.

    It is not a valuation date: membership and market cap are dated separately.
    """

    ts_code: str
    index_code: str
    as_of: date
    name: str | None = None
    exchange: str | None = None
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StockMarketCapRecord:
    """One stock's market value. Units are 元 exactly as published."""

    ts_code: str
    total_mv: float | None
    float_mv: float | None
    name: str | None = None
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StockMarketCapSnapshot:
    """A whole-market market-cap snapshot with the moment it was observed.

    The upstream endpoint exposes no trade date, so ``observed_at`` is the
    local collection time. Callers must not back-date it.
    """

    observed_at: datetime
    source: str
    rows: list[StockMarketCapRecord] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.rows)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FundNavRecord:
    """Published unit NAV for one fund on ``nav_date``. Unit is 元 per share."""

    ts_code: str
    nav_date: date
    nav: float
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NewsRecord:
    source: str
    source_id: str
    title: str
    published_at: datetime
    summary: str | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SectorRecord:
    """板块涨跌家数快照（K线企稳看板用）。

    Attributes:
        sector_name: 板块名称（如 "半导体"、"芯片概念"、"全市场"）。
        trade_date: 交易日。
        up_count: 上涨家数。
        down_count: 下跌家数。
        flat_count: 平盘家数。
        total_count: 总家数。
        pct_change: 板块涨跌幅（百分比，可选）。
        source: 数据源（默认 akshare）。
        board_type: 板块类别，"industry" 行业 / "concept" 概念 / "market" 全市场。
    """

    sector_name: str
    trade_date: date
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    total_count: int = 0
    pct_change: float | None = None
    source: str = "akshare"
    board_type: str = "industry"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
