from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, TypeVar

from app.market_context.contracts import MarketContextItem, MarketContextObservation
from app.providers.base import CapabilityUnavailable, MarketProvider, ProviderError
from app.providers.types import BarRecord, InstrumentRecord, NewsRecord, QuoteRecord, SectorRecord
from app.utils.hashing import stable_hash

logger = logging.getLogger(__name__)
T = TypeVar("T")
_SAFE_FAILURE_CLASSES = frozenset(
    {
        "CapabilityUnavailable",
        "ConnectionError",
        "KeyError",
        "ProviderError",
        "RuntimeError",
        "TimeoutError",
        "TypeError",
        "ValueError",
    }
)


def _safe_failure_label(error: BaseException) -> str:
    name = type(error).__name__
    return name if name in _SAFE_FAILURE_CLASSES else "ProviderError"


def _normalized_codes(codes: list[str]) -> list[str]:
    """Normalize requested symbols once while preserving caller order."""

    result: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        code = str(raw or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(code)
    return result


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
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        failures: list[str] = []
        for provider in self.providers:
            close = getattr(provider, "close", None)
            if callable(close):
                try:
                    close()
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as exc:
                    failures.append(_safe_failure_label(exc))
        if failures:
            raise ProviderError("provider close failed: " + ",".join(failures)) from None

    def _invoke(self, operation: str, call: Callable[[MarketProvider], T], allow_empty: bool = False) -> T:
        self.last_trace = []
        errors: list[str] = []
        unsupported = 0
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
            except CapabilityUnavailable as exc:
                unsupported += 1
                label = _safe_failure_label(exc)
                self.last_trace.append(
                    ProviderTrace(
                        operation=operation,
                        provider=provider.name,
                        status="unsupported",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        record_count=0,
                        reason=label,
                    )
                )
                logger.warning("Provider %s operation %s unsupported: %s", provider.name, operation, label)
                continue
            except Exception as exc:  # data-source fallback is intentional
                label = _safe_failure_label(exc)
                errors.append(f"{provider.name}={label}")
                self.last_trace.append(
                    ProviderTrace(
                        operation=operation,
                        provider=provider.name,
                        status="failed",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        record_count=0,
                        reason=label,
                    )
                )
                logger.warning("Provider %s operation %s failed: %s", provider.name, operation, label)
        if unsupported == len(self.providers):
            raise CapabilityUnavailable(f"all providers unsupported: {operation}") from None
        raise ProviderError(f"所有数据源均失败：{operation}; {'; '.join(errors)}")

    def _invoke_by_requested_code(
        self,
        operation: str,
        codes: list[str],
        call: Callable[[MarketProvider, list[str]], list[T]],
        aliases: Callable[[T], set[str]],
    ) -> list[T]:
        """Fill a requested code set provider-by-provider without overwriting priority.

        Generic `_invoke` is correct for capabilities where one provider owns the
        complete response. It is not correct for quote/instrument batches: a
        non-empty primary response can still omit individual ETFs. This method
        keeps the earliest provider's record for each requested code and asks
        later providers only for the codes that are still missing.
        """

        requested = _normalized_codes(codes)
        self.last_trace = []
        if not requested:
            return []

        selected: dict[str, T] = {}
        errors: list[str] = []
        unsupported = 0
        successful_calls = 0

        for index, provider in enumerate(self.providers):
            missing = [code for code in requested if code not in selected]
            if not missing:
                break
            started = time.perf_counter()
            try:
                rows = list(call(provider, missing) or [])
                successful_calls += 1
                accepted = 0
                for row in rows:
                    row_aliases = {
                        str(value or "").strip().upper()
                        for value in aliases(row)
                        if str(value or "").strip()
                    }
                    key = next((code for code in missing if code in row_aliases), None)
                    if key is None or key in selected:
                        # Unexpected/extraneous provider rows never widen the
                        # caller's requested universe and never overwrite an
                        # earlier provider's record.
                        continue
                    selected[key] = row
                    accepted += 1

                remaining = len(requested) - len(selected)
                if not rows:
                    status = "empty"
                    reason = f"missing={remaining}"
                elif remaining:
                    status = "partial" if index == 0 else "fallback_partial"
                    reason = f"missing={remaining}"
                else:
                    status = "ok" if index == 0 else "fallback_used"
                    reason = None
                self.last_trace.append(
                    ProviderTrace(
                        operation=operation,
                        provider=provider.name,
                        status=status,
                        latency_ms=(time.perf_counter() - started) * 1000,
                        record_count=accepted,
                        reason=reason,
                        quality_hash=stable_hash(rows),
                    )
                )
            except CapabilityUnavailable as exc:
                unsupported += 1
                label = _safe_failure_label(exc)
                self.last_trace.append(
                    ProviderTrace(
                        operation=operation,
                        provider=provider.name,
                        status="unsupported",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        record_count=0,
                        reason=label,
                    )
                )
                logger.warning("Provider %s operation %s unsupported: %s", provider.name, operation, label)
            except Exception as exc:
                label = _safe_failure_label(exc)
                errors.append(f"{provider.name}={label}")
                self.last_trace.append(
                    ProviderTrace(
                        operation=operation,
                        provider=provider.name,
                        status="failed",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        record_count=0,
                        reason=label,
                    )
                )
                logger.warning("Provider %s operation %s failed: %s", provider.name, operation, label)

        if selected:
            return [selected[code] for code in requested if code in selected]
        if unsupported == len(self.providers):
            raise CapabilityUnavailable(f"all providers unsupported: {operation}") from None
        if not successful_calls and errors:
            raise ProviderError(f"所有数据源均失败：{operation}; {'; '.join(errors)}") from None
        raise ProviderError(f"所有数据源均未返回请求代码：{operation}") from None

    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        if codes is None:
            return self._invoke("list_instruments", lambda provider: provider.list_instruments(codes))
        return self._invoke_by_requested_code(
            "list_instruments",
            codes,
            lambda provider, missing: provider.list_instruments(missing),
            lambda item: {item.ts_code, item.symbol},
        )

    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        return self._invoke(
            "fetch_daily_bars",
            lambda provider: provider.fetch_daily_bars(ts_code, start_date, end_date),
        )

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        return self._invoke_by_requested_code(
            "fetch_spot_quotes",
            codes,
            lambda provider, missing: provider.fetch_spot_quotes(missing),
            lambda item: {item.ts_code},
        )

    def fetch_sector_snapshots(self, trade_date: date | None = None) -> list[SectorRecord]:
        return self._invoke(
            "fetch_sector_snapshots", lambda provider: provider.fetch_sector_snapshots(trade_date)
        )

    def fetch_concept_snapshots(self, trade_date: date | None = None) -> list[SectorRecord]:
        return self._invoke(
            "fetch_concept_snapshots", lambda provider: provider.fetch_concept_snapshots(trade_date)
        )

    def fetch_market_breadth(self, trade_date: date | None = None) -> SectorRecord | None:
        # market breadth is a single record and may legitimately be None when the
        # provider cannot reach any breadth source; treat a missing row as empty.
        return self._invoke(
            "fetch_market_breadth",
            lambda provider: provider.fetch_market_breadth(trade_date),
            allow_empty=True,
        )

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
                label = _safe_failure_label(exc)
                self.last_trace.append(
                    ProviderTrace(
                        operation="fetch_news",
                        provider=provider.name,
                        status="unsupported",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        record_count=0,
                        reason=label,
                    )
                )
            except Exception as exc:
                label = _safe_failure_label(exc)
                errors.append(f"{provider.name}={label}")
                self.last_trace.append(
                    ProviderTrace(
                        operation="fetch_news",
                        provider=provider.name,
                        status="failed",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        record_count=0,
                        reason=label,
                    )
                )
        if not successful_calls and errors:
            raise ProviderError("所有新闻数据源均失败；" + "; ".join(errors))
        unique: dict[tuple[str, str], NewsRecord] = {}
        for item in combined:
            unique[(item.source, item.source_id)] = item
        return sorted(unique.values(), key=lambda item: item.published_at, reverse=True)

    def fetch_market_context(self, requests: list[MarketContextItem]) -> list[MarketContextObservation]:
        # Context cards may be partially covered by a provider, so an empty result
        # is a valid response and missing requested rows remain explicit in the service.
        return self._invoke(
            "fetch_market_context",
            lambda provider: provider.fetch_market_context(requests),
            allow_empty=True,
        )

    def is_trade_day(self, day: date) -> bool:
        for provider in self.providers:
            try:
                return provider.is_trade_day(day)
            except Exception:
                continue
        return day.weekday() < 5
