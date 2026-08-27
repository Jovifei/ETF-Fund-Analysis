from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import ProviderAudit
from app.providers.composite import CompositeProvider
from app.utils.hashing import stable_hash


class AuditTimer:
    def __init__(self) -> None:
        self.started = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000


def record_provider_audit(
    db: Session,
    *,
    run_id: str,
    operation: str,
    provider: Any,
    result: Any = None,
    error: Exception | None = None,
    latency_ms: float | None = None,
    source_time: datetime | None = None,
) -> None:
    if isinstance(provider, CompositeProvider) and provider.last_trace:
        for trace in provider.last_trace:
            db.add(
                ProviderAudit(
                    run_id=run_id,
                    operation=trace.operation,
                    provider=trace.provider,
                    status=trace.status,
                    latency_ms=trace.latency_ms,
                    record_count=trace.record_count,
                    reason=trace.reason,
                    source_time=source_time,
                    quality_hash=trace.quality_hash,
                )
            )
        return
    count = len(result) if result is not None and hasattr(result, "__len__") else int(result is not None)
    db.add(
        ProviderAudit(
            run_id=run_id,
            operation=operation,
            provider=getattr(provider, "name", type(provider).__name__),
            status="failed" if error else "ok",
            latency_ms=latency_ms,
            record_count=count,
            reason=f"{type(error).__name__}: {error}" if error else None,
            source_time=source_time,
            quality_hash=stable_hash(result) if error is None and result is not None else None,
        )
    )
