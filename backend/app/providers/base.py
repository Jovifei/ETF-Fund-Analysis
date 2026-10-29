from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.market_context.contracts import MarketContextItem, MarketContextObservation
from app.providers.types import (
    BarRecord,
    FundNavRecord,
    IndexConstituentRecord,
    InstrumentRecord,
    NewsRecord,
    QuoteRecord,
    SectorRecord,
    ShareScaleRecord,
    StockMarketCapSnapshot,
)


class ProviderError(RuntimeError):
    """Sanitized provider failure with an optional allowlisted upstream code."""

    _SAFE_CODES = frozenset({
        "UPSTREAM_REJECTED",
        "CREDENTIALS_MISSING",
        "PERMISSION_OR_CREDENTIALS_DENIED",
        "RATE_LIMITED",
        "RESPONSE_TOO_LARGE",
        "INVALID_RESPONSE_SCHEMA",
        "ENDPOINT_UNAVAILABLE",
        "UPSTREAM_HTTP_REJECTED",
        "PROVIDER_DEADLINE_EXCEEDED",
        "SINA_QUOTE_TIMEOUT",
        "SINA_QUOTE_TRANSPORT_FAILED",
        "SINA_QUOTE_UPSTREAM_REJECTED",
        "SINA_QUOTE_RESPONSE_TOO_LARGE",
        "SINA_QUOTE_RESPONSE_INVALID",
    })
    _SAFE_MESSAGES = {code.lower(): code for code in _SAFE_CODES}

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
        if candidate not in self._SAFE_CODES:
            candidate = self._SAFE_MESSAGES.get(str(message))
        self.safe_code = candidate if candidate in self._SAFE_CODES else None
        self.upstream_code = self.safe_code
        super().__init__(message)


class CapabilityUnavailable(ProviderError):
    pass


class QuoteCapabilityContractError(ProviderError):
    """An explicitly display-only adapter returned a qualified quote."""


class MarketProvider(ABC):
    name = "base"
    # Unknown adapters retain their original quote priority; degraded_only is
    # an adapter contract, not a timestamp or license qualification.
    quote_selection_capability = "unknown"

    @abstractmethod
    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        raise NotImplementedError

    @abstractmethod
    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        raise NotImplementedError

    @abstractmethod
    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        raise NotImplementedError

    def fetch_index_bars(self, symbol: str, start_date: date, end_date: date) -> list[BarRecord]:
        raise CapabilityUnavailable("index OHLC unavailable")

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

    def fetch_minute_bars(
        self,
        ts_code: str,
        interval: str,
        start_date: date,
        end_date: date,
    ) -> list[BarRecord]:
        """分钟级 OHLCV（interval ∈ {5m,15m,30m,60m}）。

        BarRecord.trade_date 携带 bar 结束时间（北京时间）。默认能力缺失，
        由具体 Provider 显式实现；日线永远不得冒充分钟线。
        """
        raise CapabilityUnavailable("minute bars unavailable for this provider")

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

    def fetch_share_scales(self, codes: list[str], start_date: date, end_date: date) -> list[ShareScaleRecord]:
        """Exchange share totals used only as a research 申赎 proxy.

        Providers that do not expose a free public helper must refuse. Callers
        must not replace that refusal with mock shares.
        """

        raise CapabilityUnavailable("share scale unavailable for this provider")

    def fetch_market_breadth(self, trade_date: date | None = None) -> SectorRecord | None:
        """全市场涨跌家数（宽度）。返回单条 board_type='market' 的快照，无数据返回 None。"""
        raise CapabilityUnavailable("market breadth unavailable for this provider")

    # ---- 沪深300 被动持仓占比研究（只读快照，不参与评分）----
    # 三个能力各自独立降级；调用方不得用近似值替代缺失的分母或分子。

    def fetch_index_constituents(self, index_code: str) -> list[IndexConstituentRecord]:
        """官方指数成分名单；``as_of`` 是名单（调样）日期，不是估值日。"""
        raise CapabilityUnavailable("index constituents unavailable for this provider")

    def fetch_stock_float_market_caps(self) -> StockMarketCapSnapshot:
        """全市场流通市值快照（元）。

        上游没有交易日字段，实现必须用采集时刻标注 ``observed_at``；
        调用方不得回填历史，也不得把盘中快照当成收盘值。
        """
        raise CapabilityUnavailable("stock float market caps unavailable for this provider")

    def fetch_etf_nav_snapshot(self) -> list[FundNavRecord]:
        """场内基金单位净值快照，净值日期随记录返回。"""
        raise CapabilityUnavailable("etf nav snapshot unavailable for this provider")

    def fetch_etf_catalog(self) -> list[InstrumentRecord]:
        """枚举全部场内 ETF（代码/名称原样返回）。

        只供一次性清单派生脚本使用；运行期不得按名称猜测跟踪标的。
        """
        raise CapabilityUnavailable("etf catalog unavailable for this provider")
