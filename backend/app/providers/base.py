from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.market_context.contracts import MarketContextItem, MarketContextObservation
from app.providers.types import (
    BarRecord,
    InstrumentRecord,
    NewsRecord,
    QuoteRecord,
    SectorRecord,
)


class ProviderError(RuntimeError):
    """Sanitized provider failure with an optional allowlisted upstream code."""

    _SAFE_CODES = frozenset({"UPSTREAM_REJECTED"})

    def __init__(
        self,
        message: str = "provider error",
        *,
        safe_code: str | None = None,
        upstream_code: str | None = None,
    ) -> None:
        # `upstream_code` is a compatibility alias for consumers that use the
        # report vocabulary.  Values outside the explicit allowlist are never
        # retained, so raw provider response details cannot escape by accident.
        candidate = safe_code if safe_code is not None else upstream_code
        self.safe_code = candidate if candidate in self._SAFE_CODES else None
        self.upstream_code = self.safe_code
        super().__init__(message)


class CapabilityUnavailable(ProviderError):
    pass


class MarketProvider(ABC):
    name = "base"

    @abstractmethod
    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        raise NotImplementedError

    @abstractmethod
    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        raise NotImplementedError

    @abstractmethod
    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        raise NotImplementedError

    def fetch_news(self, since_hours: int = 24) -> list[NewsRecord]:
        return []

    def close(self) -> None:
        """Release provider-owned resources; injected providers may no-op."""
        return None

    def fetch_market_context(
        self, requests: list[MarketContextItem]
    ) -> list[MarketContextObservation]:
        del requests
        raise CapabilityUnavailable("market context capability is unavailable for this provider")

    def is_trade_day(self, day: date) -> bool:
        return day.weekday() < 5

    def resolve_instrument(self, code: str) -> InstrumentRecord | None:
        """按代码解析一个标的（名称/交易所/类型）；未找到或能力缺失返回 None。

        供用户自助添加自选使用；实现必须走既有上游接口（如 fund_basic），
        不允许在业务层直连行情站。
        """
        return None

    # ---- 板块涨跌家数（K线企稳看板）----
    # 行业/概念板块与全市场宽度分三个能力，各自可独立降级：
    # 不支持的 provider 默认抛 CapabilityUnavailable，由调用方决定是否跳过。

    def fetch_sector_snapshots(self, trade_date: date | None = None) -> list[SectorRecord]:
        """行业板块涨跌家数快照。"""
        raise CapabilityUnavailable("sector snapshots unavailable for this provider")

    def fetch_concept_snapshots(self, trade_date: date | None = None) -> list[SectorRecord]:
        """概念板块涨跌家数快照。"""
        raise CapabilityUnavailable("concept snapshots unavailable for this provider")

    def fetch_market_breadth(self, trade_date: date | None = None) -> SectorRecord | None:
        """全市场涨跌家数（宽度）。返回单条 board_type='market' 的快照，无数据返回 None。"""
        raise CapabilityUnavailable("market breadth unavailable for this provider")
