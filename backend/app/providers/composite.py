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
    code = getattr(error, "safe_code", None)
    if code in ProviderError._SAFE_CODES:
        return code
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

    def fetch_index_bars(self, symbol, start_date, end_date):
        return self._invoke("fetch_index_bars", lambda p: p.fetch_index_bars(symbol, start_date, end_date))

    @staticmethod
    def _daily_candidate(rows: list[BarRecord], end_date: date) -> tuple[int, bool, str | None]:
        """Rank one provider's complete daily batch without mixing sources.

        A non-empty Sina price-only response is useful for chart display, but it
        must not hide a later provider with documented units.  The ranking is
        deliberately conservative: source identity, quantity presence, OHLC
        continuity, and target-date coverage are all considered before a batch
        can be selected for shared calculations.
        """

        if not rows:
            return 0, False, "empty_result"
        from app.providers.data_contract import DOCUMENTED_UNIT_SOURCES, price_history_issue

        sources = {str(getattr(row, "source", "")) for row in rows}
        if len(sources) != 1:
            return 0, False, "mixed_source_batch"
        source = next(iter(sources))
        latest = max((row.trade_date for row in rows), default=None)
        covers_target = latest is not None and latest >= end_date
        if source in DOCUMENTED_UNIT_SOURCES:
            from app.providers.corporate_action_contract import research_history_rows
            issue = price_history_issue(research_history_rows(rows, rows[0].ts_code))
            if issue:
                return 0, covers_target, issue
            if any(getattr(row, "volume", None) is None or getattr(row, "amount", None) is None for row in rows):
                return 0, covers_target, "documented_source_missing_quantity"
            return 3, covers_target, None if covers_target else "target_date_missing"
        if source.startswith("akshare:sina:"):
            return 1, covers_target, "price_only_units_unverified"
        return 0, covers_target, "unknown_units_unverified"

    def _fetch_daily_bars_quality_aware(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        self.last_trace = []
        candidates: list[tuple[int, bool, int, int, list[BarRecord], ProviderTrace]] = []
        unsupported = 0
        errors: list[str] = []
        for index, provider in enumerate(self.providers):
            started = time.perf_counter()
            try:
                rows = list(provider.fetch_daily_bars(ts_code, start_date, end_date) or [])
                quality, covers_target, reason = self._daily_candidate(rows, end_date)
                trace = ProviderTrace(
                    operation="fetch_daily_bars",
                    provider=provider.name,
                    status="candidate",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    record_count=len(rows),
                    reason=reason,
                    quality_hash=stable_hash(rows),
                )
                self.last_trace.append(trace)
                candidates.append((quality, covers_target, len(rows), -index, rows, trace))
                # A fully qualified batch through the requested date cannot be
                # improved by a lower-priority source.
                if quality == 3 and covers_target:
                    break
            except CapabilityUnavailable as exc:
                unsupported += 1
                label = _safe_failure_label(exc)
                self.last_trace.append(ProviderTrace(
                    operation="fetch_daily_bars", provider=provider.name, status="unsupported",
                    latency_ms=(time.perf_counter() - started) * 1000, record_count=0, reason=label,
                ))
            except Exception as exc:
                label = _safe_failure_label(exc)
                errors.append(f"{provider.name}={label}")
                self.last_trace.append(ProviderTrace(
                    operation="fetch_daily_bars", provider=provider.name, status="failed",
                    latency_ms=(time.perf_counter() - started) * 1000, record_count=0, reason=label,
                ))

        if candidates:
            selected = max(candidates, key=lambda item: item[:4])
            selected_trace = selected[-1]
            for quality, _covers_target, _count, _priority, _rows, trace in candidates:
                if trace is selected_trace:
                    if quality == 3 and _covers_target:
                        trace.status = "ok" if _priority == 0 else "fallback_used"
                        trace.reason = None
                    else:
                        trace.status = "partial" if _priority == 0 else "fallback_partial"
                elif quality < selected[0]:
                    trace.status = "quality_fallback"
                else:
                    trace.status = "superseded"
            return selected[4]
        if unsupported == len(self.providers):
            raise CapabilityUnavailable("all providers unsupported: fetch_daily_bars") from None
        raise ProviderError(f"所有数据源均失败：fetch_daily_bars; {'; '.join(errors)}") from None

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
        daily_fallbacks: dict[str, T] = {}
        degraded_quotes: dict[str, T] = {}
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
                    if operation == "fetch_spot_quotes" and str(getattr(row, "source", "")).startswith("tushare:fund_daily"):
                        daily_fallbacks.setdefault(key, row)
                        continue
                    if operation == "fetch_spot_quotes" and not self._quote_is_qualified(row):
                        # A public snapshot can be useful as a degraded display
                        # value, but it must not prevent a later provider from
                        # supplying a timestamped realtime quote.
                        degraded_quotes.setdefault(key, row)
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

        for code, row in degraded_quotes.items():
            selected.setdefault(code, row)
        for code, row in daily_fallbacks.items():
            selected.setdefault(code, row)
        if selected:
            return [selected[code] for code in requested if code in selected]
        if unsupported == len(self.providers):
            raise CapabilityUnavailable(f"all providers unsupported: {operation}") from None
        if not successful_calls and errors:
            raise ProviderError(f"所有数据源均失败：{operation}; {'; '.join(errors)}") from None
        raise ProviderError(f"所有数据源均未返回请求代码：{operation}") from None

    @staticmethod
    def _quote_is_qualified(row: T) -> bool:
        source = str(getattr(row, "source", ""))
        timestamp = getattr(row, "quote_time", None)
        return (
            bool(getattr(row, "is_realtime", False))
            and not getattr(row, "degraded_reason", None)
            and bool(source)
            and timestamp is not None
            and source not in {"akshare:em:v101", "tushare:fund_daily:v101"}
        )

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
        return self._fetch_daily_bars_quality_aware(ts_code, start_date, end_date)

    def fetch_minute_bars(self, ts_code: str, interval: str, start_date: date, end_date: date) -> list[BarRecord]:
        return self._invoke("fetch_minute_bars", lambda provider: provider.fetch_minute_bars(ts_code, interval, start_date, end_date))

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        return self._invoke_by_requested_code(
            "fetch_spot_quotes",
            codes,
            lambda provider, missing: getattr(provider, "fetch_current_quotes", provider.fetch_spot_quotes)(missing),
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
