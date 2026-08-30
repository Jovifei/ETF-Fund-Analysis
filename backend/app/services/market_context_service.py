from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.market_context.contracts import (
    FreshnessStatus,
    MarketContextItem,
    MarketContextObservation,
    RegistryConfig,
    VerificationStatus,
)
from app.models import MarketContextRegistry, MarketContextSnapshot, ProviderAudit
from app.providers.base import CapabilityUnavailable, MarketProvider
from app.providers.composite import CompositeProvider


@dataclass(frozen=True, slots=True)
class MarketContextRefreshOutcome:
    """Immutable, bounded facts from one market-context refresh attempt."""

    configured: int
    eligible: int
    provider_calls: int
    observed: int
    inserted: int
    missing: int
    mock: int
    degraded: int


class MarketContextError(RuntimeError):
    """Base class for sanitized market-context refresh failures."""

    def __init__(self, message: str, *, outcome: MarketContextRefreshOutcome | None = None) -> None:
        self.outcome = outcome
        super().__init__(message)


class MarketContextProviderError(MarketContextError):
    """A provider failed without exposing its error message to callers or audit rows."""

    def __init__(
        self,
        operation: str,
        exception_class: str,
        *,
        outcome: MarketContextRefreshOutcome | None = None,
    ) -> None:
        self.operation = operation
        self.exception_class = exception_class
        super().__init__(f"{operation} failed: {exception_class}", outcome=outcome)


class MarketContextObservationError(MarketContextError):
    """Provider observations did not match the requested, typed contract."""


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _error_class(error: BaseException) -> str:
    return type(error).__name__


class MarketContextService:
    """Synchronize configured context cards and persist verified provider observations."""

    operation = "fetch_market_context"

    def __init__(
        self,
        provider: MarketProvider,
        settings: Settings | None = None,
        *,
        persist_provider_audits: bool = True,
    ) -> None:
        self.provider = provider
        self.settings = settings or get_settings()
        self.persist_provider_audits = persist_provider_audits

    def _config(self, config: RegistryConfig | Iterable[MarketContextItem] | None) -> RegistryConfig:
        if config is None:
            return self.settings.load_market_context()
        if isinstance(config, RegistryConfig):
            return config
        return RegistryConfig(items=tuple(config))

    @staticmethod
    def _item_values(item: MarketContextItem, *, display_order: int | None = None) -> dict[str, Any]:
        return {
            "context_id": item.context_id,
            "label": item.label,
            "region": item.region,
            "context_kind": _enum_value(item.context_kind),
            "source_symbol": item.source_symbol,
            "display_code": item.display_code,
            "is_tradable_proxy": item.is_tradable_proxy,
            "enabled": item.enabled,
            "display_order": item.display_order if display_order is None else display_order,
            "source_priority": list(item.source_priority),
            "freshness_rule": item.freshness_rule,
            "verification_status": _enum_value(item.verification_status),
        }

    @staticmethod
    def _insert_registry_if_absent(
        db: Session,
        item: MarketContextItem,
        display_order: int,
    ) -> tuple[MarketContextRegistry, bool]:
        values = MarketContextService._item_values(item, display_order=display_order)
        dialect = db.get_bind().dialect.name
        inserted = False
        try:
            with db.begin_nested():
                if dialect == "sqlite":
                    statement = sqlite_insert(MarketContextRegistry).values(**values).on_conflict_do_nothing(
                        index_elements=["context_id"]
                    )
                    result = db.execute(statement)
                    inserted = bool(result.rowcount)
                elif dialect == "postgresql":
                    statement = postgresql_insert(MarketContextRegistry).values(**values).on_conflict_do_nothing(
                        index_elements=["context_id"]
                    )
                    result = db.execute(statement)
                    inserted = bool(result.rowcount)
                else:
                    db.add(MarketContextRegistry(**values))
                    db.flush()
                    inserted = True
        except IntegrityError:
            result = None
        row = db.scalar(
            select(MarketContextRegistry).where(MarketContextRegistry.context_id == item.context_id)
        )
        if row is None:
            raise ValueError("market context registry insert did not produce a row")
        return row, inserted

    @staticmethod
    def _next_temporary_order(used: set[int], reserved: set[int]) -> int:
        for order in range(10_000, 0, -1):
            if order not in used and order not in reserved:
                return order
        raise ValueError("market context registry has no safe temporary display orders")

    def _make_display_orders_safe(
        self,
        db: Session,
        rows: list[MarketContextRegistry],
        target_orders: dict[MarketContextRegistry, int],
    ) -> None:
        """Move rows through unused bounded orders before applying changed orders."""
        if all(row.display_order == target_orders[row] for row in rows):
            return
        used = {int(row.display_order) for row in rows}
        final_orders = set(target_orders.values())
        temporary = [
            value
            for value in range(10_000, 0, -1)
            if value not in used and value not in final_orders
        ]
        if len(temporary) < len(rows):
            # This is only possible for a registry approaching its 10,000-row DB bound.
            # Keep the operation deterministic and fail closed instead of violating a unique key.
            raise ValueError("market context registry has no safe temporary display orders")
        for row, order in zip(
            sorted(rows, key=lambda item: (item.context_id, item.id)), temporary[: len(rows)], strict=True
        ):
            row.display_order = order
        db.flush()
        for row in rows:
            row.display_order = target_orders[row]

    def sync_registry(
        self,
        db: Session,
        config: RegistryConfig | Iterable[MarketContextItem] | None = None,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Upsert config rows while retaining historical rows that have snapshots."""
        del run_id  # Reserved for the task-layer audit/event boundary in B2b.
        registry = self._config(config)
        configured = {item.context_id: item for item in registry.items}
        rows = db.scalars(select(MarketContextRegistry).order_by(MarketContextRegistry.id)).all()
        by_context = {row.context_id: row for row in rows}
        created = 0
        updated = 0

        # Rows without history are safe to remove when configuration no longer names them.
        registry_ids = [row.id for row in rows if row.id is not None]
        snapshot_registry_ids = (
            set(
                db.scalars(
                    select(MarketContextSnapshot.registry_id).where(
                        MarketContextSnapshot.registry_id.in_(registry_ids)
                    )
                ).all()
            )
            if registry_ids
            else set()
        )
        removed = [
            row
            for row in rows
            if row.context_id not in configured and row.id not in snapshot_registry_ids
        ]
        for row in removed:
            db.delete(row)
            rows.remove(row)
        if removed:
            # Ensure a new config row can reuse an old display order under
            # databases with immediate unique-constraint enforcement.
            db.flush()
        historical = [row for row in rows if row.context_id not in configured]
        kept: list[MarketContextRegistry] = []
        configured_orders = {item.display_order for item in registry.items}
        reserved_orders = {int(row.display_order) for row in rows}
        for item in registry.items:
            row = by_context.get(item.context_id)
            if row is None or row in removed:
                while True:
                    temporary_order = self._next_temporary_order(reserved_orders, configured_orders)
                    try:
                        row, inserted = self._insert_registry_if_absent(db, item, temporary_order)
                        break
                    except ValueError as exc:
                        if "did not produce a row" not in str(exc):
                            raise
                        reserved_orders.add(temporary_order)
                if inserted:
                    reserved_orders.add(temporary_order)
                    rows.append(row)
                    created += 1
                else:
                    updated += 1
                by_context[item.context_id] = row
            else:
                updated += 1
                for key, value in self._item_values(item).items():
                    if key == "display_order":
                        continue
                    setattr(row, key, value)
            kept.append(row)

        # A removed row with snapshots remains visible as an explicitly unavailable card.
        # Clear source/display codes because an old code is not current verification.
        for row in historical:
            row.enabled = False
            row.verification_status = VerificationStatus.UNVERIFIED.value
            row.source_symbol = None
            row.display_code = None
            row.source_priority = []

        all_kept = kept + historical
        desired: dict[MarketContextRegistry, int] = {}
        for item, row in zip(registry.items, kept, strict=True):
            desired[row] = item.display_order
        configured_orders = {item.display_order for item in registry.items}
        historical_orders = [
            order for order in range(10_000, 0, -1) if order not in configured_orders
        ]
        if len(historical_orders) < len(historical):
            raise ValueError("market context registry has no legal display orders for historical rows")
        for order, row in zip(
            historical_orders[: len(historical)], sorted(historical, key=lambda item: item.context_id), strict=True
        ):
            desired[row] = order
        if all_kept:
            self._make_display_orders_safe(db, all_kept, desired)
        db.flush()
        return {
            "created": created,
            "updated": updated,
            "stale": len(historical),
            "total": len(all_kept),
        }

    @staticmethod
    def _row_item(row: MarketContextRegistry) -> MarketContextItem:
        return MarketContextItem(
            context_id=row.context_id,
            label=row.label,
            region=row.region,
            context_kind=row.context_kind,
            source_symbol=row.source_symbol,
            display_code=row.display_code,
            is_tradable_proxy=bool(row.is_tradable_proxy),
            enabled=bool(row.enabled),
            display_order=row.display_order,
            source_priority=tuple(row.source_priority or []),
            freshness_rule=row.freshness_rule,
            verification_status=row.verification_status,
        )

    def _validate_source_priority(self, rows: Iterable[MarketContextRegistry]) -> None:
        provider_order = (
            tuple(provider.name for provider in self.provider.providers)
            if isinstance(self.provider, CompositeProvider)
            else (getattr(self.provider, "name", type(self.provider).__name__),)
        )
        for row in rows:
            priority = tuple(row.source_priority or [])
            if priority and priority != provider_order:
                raise MarketContextError(
                    f"source_priority cannot be honored for context_id: {row.context_id}"
                )

    def build_requests(self, db: Session) -> list[MarketContextItem]:
        rows = db.scalars(
            select(MarketContextRegistry)
            .where(
                MarketContextRegistry.enabled.is_(True),
                MarketContextRegistry.verification_status == VerificationStatus.VERIFIED.value,
                MarketContextRegistry.source_symbol.is_not(None),
            )
            .order_by(MarketContextRegistry.display_order)
        ).all()
        self._validate_source_priority(rows)
        return [self._row_item(row) for row in rows]

    # Compatibility aliases for task/API layers that use request terminology.
    eligible_requests = build_requests
    build_market_context_requests = build_requests

    def _record_audit(
        self,
        db: Session,
        *,
        run_id: str,
        status: str,
        record_count: int,
        latency_ms: float | None = None,
        reason: str | None = None,
        include_traces: bool = True,
    ) -> None:
        if not self.persist_provider_audits:
            return
        traces = (
            getattr(self.provider, "last_trace", None)
            if include_traces and isinstance(self.provider, CompositeProvider)
            else None
        )
        if traces:
            for trace in traces:
                trace_reason = trace.reason
                if trace.status in {"failed", "unsupported"} and trace_reason:
                    trace_reason = trace_reason.split(":", 1)[0].strip()
                db.add(
                    ProviderAudit(
                        run_id=run_id,
                        operation=self.operation,
                        provider=trace.provider,
                        status=trace.status,
                        latency_ms=trace.latency_ms,
                        record_count=trace.record_count,
                        reason=trace_reason,
                        quality_hash=trace.quality_hash,
                    )
                )
            return
        db.add(
            ProviderAudit(
                run_id=run_id,
                operation=self.operation,
                provider=getattr(self.provider, "name", type(self.provider).__name__),
                status=status,
                latency_ms=latency_ms,
                record_count=record_count,
                reason=reason,
                quality_hash=None,
            )
        )

    @staticmethod
    def _validate_observations(
        requests: list[MarketContextItem],
        observations: Iterable[MarketContextObservation | dict[str, Any]],
    ) -> list[MarketContextObservation]:
        expected = {item.context_id: item for item in requests}
        seen: set[str] = set()
        validated: list[MarketContextObservation] = []
        for raw in observations:
            try:
                observation = (
                    raw if isinstance(raw, MarketContextObservation) else MarketContextObservation.model_validate(raw)
                )
            except Exception as exc:
                raise MarketContextObservationError(f"invalid observation: {_error_class(exc)}") from None
            if observation.context_id not in expected:
                raise MarketContextObservationError(f"unknown observation context_id: {observation.context_id}")
            request = expected[observation.context_id]
            if observation.source_symbol != request.source_symbol:
                raise MarketContextObservationError(
                    f"source_symbol mismatch for context_id: {observation.context_id}"
                )
            if not observation.is_mock and observation.verification_status is not VerificationStatus.VERIFIED:
                raise MarketContextObservationError(
                    f"verification status mismatch for context_id: {observation.context_id}"
                )
            if observation.context_id in seen:
                raise MarketContextObservationError(f"duplicate observation context_id: {observation.context_id}")
            seen.add(observation.context_id)
            validated.append(observation)
        return validated

    def _persist_observations(
        self,
        db: Session,
        observations: Iterable[MarketContextObservation],
        rows_by_context: dict[str, MarketContextRegistry],
    ) -> int:
        inserted = 0
        for observation in observations:
            row = rows_by_context[observation.context_id]
            values = {
                "registry_id": row.id,
                "source_symbol": observation.source_symbol,
                "observed_value": observation.observed_value,
                "today_pct_change": observation.today_pct_change,
                "price": observation.price,
                "source": observation.source,
                "source_timestamp": observation.source_timestamp,
                "fetched_at": observation.fetched_at,
                "freshness": _enum_value(observation.freshness),
                "verification_status": _enum_value(observation.verification_status),
                "is_mock": observation.is_mock,
                "degraded_reason": observation.degraded_reason,
            }
            dialect = db.get_bind().dialect.name
            if dialect == "sqlite":
                statement = sqlite_insert(MarketContextSnapshot).values(**values).on_conflict_do_nothing(
                    index_elements=["registry_id", "source_symbol", "source", "source_timestamp"]
                )
            elif dialect == "postgresql":
                statement = postgresql_insert(MarketContextSnapshot).values(**values).on_conflict_do_nothing(
                    index_elements=["registry_id", "source_symbol", "source", "source_timestamp"]
                )
            else:
                try:
                    with db.begin_nested():
                        db.add(MarketContextSnapshot(**values))
                        db.flush()
                    inserted += 1
                except IntegrityError:
                    pass
                continue
            result = db.execute(statement)
            if result.rowcount:
                inserted += 1
        db.flush()
        return inserted

    def refresh(
        self,
        db: Session,
        *,
        config: RegistryConfig | Iterable[MarketContextItem] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or uuid4().hex
        registry = self._config(config)
        self.sync_registry(db, config=registry, run_id=run_id)
        try:
            requests = self.build_requests(db)
        except MarketContextError as exc:
            eligible = len(
                db.scalars(
                    select(MarketContextRegistry)
                    .where(
                        MarketContextRegistry.enabled.is_(True),
                        MarketContextRegistry.verification_status == VerificationStatus.VERIFIED.value,
                        MarketContextRegistry.source_symbol.is_not(None),
                    )
                ).all()
            )
            outcome = MarketContextRefreshOutcome(
                configured=len(registry.items),
                eligible=eligible,
                provider_calls=0,
                observed=0,
                inserted=0,
                missing=eligible,
                mock=0,
                degraded=0,
            )
            exc.outcome = outcome
            raise
        result: dict[str, Any] = {
            "run_id": run_id,
            "configured": len(registry.items),
            "eligible": len(requests),
            "requested": len(requests),
            "provider_calls": 0,
            "received": 0,
            "observed": 0,
            "missing": 0,
            "inserted": 0,
            "mock": 0,
            "degraded": 0,
        }
        if not requests:
            return result
        started = datetime.now().timestamp()
        outcome = MarketContextRefreshOutcome(
            configured=len(registry.items),
            eligible=len(requests),
            provider_calls=1,
            observed=0,
            inserted=0,
            missing=len(requests),
            mock=0,
            degraded=0,
        )
        try:
            observations = self.provider.fetch_market_context(requests)
            result["provider_calls"] = 1
            validated = self._validate_observations(requests, observations)
        except Exception as exc:
            result["provider_calls"] = 1
            sanitized = (
                exc
                if isinstance(exc, MarketContextObservationError)
                else MarketContextProviderError(self.operation, _error_class(exc), outcome=outcome)
            )
            if isinstance(sanitized, MarketContextObservationError):
                sanitized.outcome = outcome
            self._record_audit(
                db,
                run_id=run_id,
                status="failed" if not isinstance(exc, CapabilityUnavailable) else "unsupported",
                record_count=0,
                latency_ms=(datetime.now().timestamp() - started) * 1000,
                reason=getattr(sanitized, "exception_class", _error_class(exc)),
                include_traces=not isinstance(exc, MarketContextObservationError),
            )
            db.flush()
            raise sanitized from None
        self._record_audit(
            db,
            run_id=run_id,
            status="ok",
            record_count=len(validated),
            latency_ms=(datetime.now().timestamp() - started) * 1000,
            reason=None,
        )
        rows = db.scalars(select(MarketContextRegistry)).all()
        rows_by_context = {row.context_id: row for row in rows}
        result["received"] = len(validated)
        result["observed"] = len(validated)
        result["missing"] = len(requests) - len(validated)
        result["inserted"] = self._persist_observations(db, validated, rows_by_context)
        result["mock"] = sum(observation.is_mock for observation in validated)
        result["degraded"] = sum(
            _enum_value(observation.freshness) in {FreshnessStatus.DEGRADED.value, FreshnessStatus.UNAVAILABLE.value}
            for observation in validated
        )
        return result

    refresh_market_context = refresh

    @staticmethod
    def _observation_dict(snapshot: MarketContextSnapshot | None) -> dict[str, Any] | None:
        if snapshot is None:
            return None
        return {
            "source_symbol": snapshot.source_symbol,
            "observed_value": snapshot.observed_value,
            "today_pct_change": snapshot.today_pct_change,
            "price": snapshot.price,
            "source": snapshot.source,
            "source_timestamp": snapshot.source_timestamp,
            "fetched_at": snapshot.fetched_at,
            "freshness": snapshot.freshness,
            "verification_status": snapshot.verification_status,
            "is_mock": bool(snapshot.is_mock),
            "degraded": snapshot.freshness in {FreshnessStatus.DEGRADED.value, FreshnessStatus.UNAVAILABLE.value},
            "degraded_reason": snapshot.degraded_reason,
        }

    @staticmethod
    def _snapshot_is_displayable(snapshot: MarketContextSnapshot) -> bool:
        freshness = snapshot.freshness
        has_reason = bool(snapshot.degraded_reason)
        coherent_freshness = (
            freshness in {FreshnessStatus.FRESH.value, FreshnessStatus.STALE.value} and not has_reason
        ) or (freshness in {FreshnessStatus.DEGRADED.value, FreshnessStatus.UNAVAILABLE.value} and has_reason)
        if not coherent_freshness and freshness != FreshnessStatus.UNKNOWN.value:
            return False
        if snapshot.is_mock:
            return (
                snapshot.verification_status == VerificationStatus.UNVERIFIED.value
                and freshness == FreshnessStatus.DEGRADED.value
                and has_reason
            )
        return snapshot.verification_status == VerificationStatus.VERIFIED.value

    def latest_view(self, db: Session) -> list[dict[str, Any]]:
        registries = db.scalars(select(MarketContextRegistry).order_by(MarketContextRegistry.display_order)).all()
        ranked_snapshots = select(
            MarketContextSnapshot.id.label("snapshot_id"),
            func.row_number()
            .over(
                partition_by=MarketContextSnapshot.registry_id,
                order_by=(MarketContextSnapshot.source_timestamp.desc(), MarketContextSnapshot.id.desc()),
            )
            .label("snapshot_rank"),
        ).join(
            MarketContextRegistry,
            (MarketContextRegistry.id == MarketContextSnapshot.registry_id)
            & (MarketContextRegistry.source_symbol == MarketContextSnapshot.source_symbol),
        ).subquery()
        snapshots = db.scalars(
            select(MarketContextSnapshot)
            .join(ranked_snapshots, ranked_snapshots.c.snapshot_id == MarketContextSnapshot.id)
            .where(ranked_snapshots.c.snapshot_rank == 1)
        ).all()
        latest: dict[int, MarketContextSnapshot] = {}
        for snapshot in snapshots:
            latest.setdefault(snapshot.registry_id, snapshot)
        result: list[dict[str, Any]] = []
        for row in registries:
            eligible = bool(row.enabled) and row.verification_status == VerificationStatus.VERIFIED.value
            snapshot = latest.get(row.id) if eligible else None
            observation = (
                self._observation_dict(snapshot)
                if snapshot is not None and self._snapshot_is_displayable(snapshot)
                else None
            )
            status = observation["freshness"] if observation else FreshnessStatus.UNAVAILABLE.value
            public = {
                "context_id": row.context_id,
                "label": row.label,
                "region": row.region,
                "context_kind": row.context_kind,
                "source_symbol": row.source_symbol,
                "display_code": row.display_code,
                "is_tradable_proxy": bool(row.is_tradable_proxy),
                "enabled": bool(row.enabled),
                "display_order": row.display_order,
                "source_priority": list(row.source_priority or []),
                "freshness_rule": row.freshness_rule,
                "verification_status": row.verification_status,
                "status": status,
                "observation": observation,
            }
            if observation:
                public.update({key: value for key, value in observation.items() if key != "verification_status"})
            else:
                public.update(
                    {
                        "observed_value": None,
                        "today_pct_change": None,
                        "price": None,
                        "source": None,
                        "source_timestamp": None,
                        "fetched_at": None,
                        "freshness": status,
                        "is_mock": False,
                        "degraded": True,
                        "degraded_reason": None,
                    }
                )
            result.append(public)
        return result

    latest = latest_view


__all__ = [
    "MarketContextError",
    "MarketContextRefreshOutcome",
    "MarketContextObservationError",
    "MarketContextProviderError",
    "MarketContextService",
]
