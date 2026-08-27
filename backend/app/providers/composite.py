from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, TypeVar

from app.providers.base import CapabilityUnavailable, MarketProvider, ProviderError
from app.providers.types import BarRecord, InstrumentRecord, NewsRecord, QuoteRecord
from app.utils.hashing import stable_hash

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(slots=True)
class ProviderTrace:
    operation: str
    provider: str
    status: str
    latency_ms: float
    record_count: int
    reason: str | None = None
    quality_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "provider": self.provider,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "record_count": self.record_count,
            "reason": self.reason,
            "quality_hash": self.quality_hash,
        }


class CompositeProvider(MarketProvider):
    name = "composite"

    def __init__(self, providers: list[MarketProvider]) -> None:
        if not providers:
            raise ValueError("CompositeProvider 至少需要一个 provider")
        self.providers = providers
        self.last_trace: list[ProviderTrace] = []

    def _invoke(self, operation: str, call: Callable[[MarketProvider], T], allow_empty: bool = False) -> T:
        self.last_trace = []
        errors: list[str] = []
        for index, provider in enumerate(self.providers):
            started = time.perf_counter()
            try:
                result = call(provider)
                count = len(result) if hasattr(result, "__len__") else 1
                if count == 0 and not allow_empty:
                    raise ProviderError("empty result")
                trace = ProviderTrace(
                    operation=operation,
                    provider=provider.name,
                    status="ok" if index == 0 else "fallback_used",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    record_count=count,
                    quality_hash=stable_hash(result),
                )
                self.last_trace.append(trace)
                return result
            except Exception as exc:  # data-source fallback is intentional
                message = f"{type(exc).__name__}: {exc}"
                errors.append(f"{provider.name}={message}")
                self.last_trace.append(
                    ProviderTrace(
                        operation=operation,
                        provider=provider.name,
                        status="failed",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        record_count=0,
                        reason=message,
                    )
                )
                logger.warning("Provider %s operation %s failed: %s", provider.name, operation, exc)
        raise ProviderError(f"所有数据源均失败：{operation}; {'; '.join(errors)}")

    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        return self._invoke("list_instruments", lambda provider: provider.list_instruments(codes))

    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        return self._invoke(
            "fetch_daily_bars",
            lambda provider: provider.fetch_daily_bars(ts_code, start_date, end_date),
        )

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        return self._invoke("fetch_spot_quotes", lambda provider: provider.fetch_spot_quotes(codes))

    def fetch_news(self, since_hours: int = 24) -> list[NewsRecord]:
        # News is additive rather than a strict primary/fallback capability. Pull
        # every configured source, retain per-provider audit traces, then dedupe.
        self.last_trace = []
        combined: list[NewsRecord] = []
        successful_calls = 0
        errors: list[str] = []
        for provider in self.providers:
            started = time.perf_counter()
            try:
                rows = provider.fetch_news(since_hours)
                successful_calls += 1
                combined.extend(rows)
                self.last_trace.append(
                    ProviderTrace(
                        operation="fetch_news",
                        provider=provider.name,
                        status="ok",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        record_count=len(rows),
                        reason="empty result" if not rows else None,
                        quality_hash=stable_hash(rows),
                    )
                )
            except CapabilityUnavailable as exc:
                self.last_trace.append(
                    ProviderTrace(
                        operation="fetch_news",
                        provider=provider.name,
                        status="unsupported",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        record_count=0,
                        reason=str(exc),
                    )
                )
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                errors.append(f"{provider.name}={message}")
                self.last_trace.append(
                    ProviderTrace(
                        operation="fetch_news",
                        provider=provider.name,
                        status="failed",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        record_count=0,
                        reason=message,
                    )
                )
        if not successful_calls and errors:
            raise ProviderError("所有新闻数据源均失败；" + "; ".join(errors))
        unique: dict[tuple[str, str], NewsRecord] = {}
        for item in combined:
            unique[(item.source, item.source_id)] = item
        return sorted(unique.values(), key=lambda item: item.published_at, reverse=True)

    def is_trade_day(self, day: date) -> bool:
        for provider in self.providers:
            try:
                return provider.is_trade_day(day)
            except Exception:
                continue
        return day.weekday() < 5
