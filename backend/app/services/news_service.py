from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.contracts import (
    AnalysisEnvelope,
    AnalysisProvider,
    AnalysisStatus,
    DataProvenance,
    Freshness,
    VerifiedAnalysisInput,
)
from app.core.config import Settings, get_settings
from app.models import AnalysisRun, NewsItem
from app.providers.base import MarketProvider
from app.providers.mock import MockProvider
from app.providers.types import NewsRecord
from app.services.analysis_persistence_service import AnalysisPersistenceService
from app.services.analysis_service import AnalysisService
from app.services.audit_service import AuditTimer, record_provider_audit
from app.services.event_service import emit_event
from app.services.theme_service import ThemeClassifier
from app.utils.hashing import stable_hash
from app.utils.numbers import clamp

POSITIVE_WORDS = ["利好", "增长", "突破", "提振", "回升", "上调", "支持", "加速", "改善", "创新"]
NEGATIVE_WORDS = ["利空", "下降", "下调", "风险", "处罚", "收紧", "减产", "亏损", "波动", "分歧"]


class NewsProviderRefreshError(RuntimeError):
    """Sanitized provider refresh failure for task retry/observability."""

    def __init__(self, operation: str, exception_class: str) -> None:
        self.operation = operation
        self.exception_class = exception_class
        super().__init__(f"{operation} failed: {exception_class}")


@dataclass(frozen=True, slots=True)
class HeuristicNewsAnalysis:
    facts: list[str]
    inferences: list[str]
    risk_flags: list[str]
    affected_themes: list[str]
    impact_direction: str
    impact_horizon: str
    impact_score: float

    def model_dump(self) -> dict[str, Any]:
        return {"facts": list(self.facts), "inferences": list(self.inferences), "risk_flags": list(self.risk_flags), "affected_themes": list(self.affected_themes), "impact_direction": self.impact_direction, "impact_horizon": self.impact_horizon, "impact_score": self.impact_score}


class NewsService:
    def __init__(self, provider: MarketProvider, settings: Settings | None = None, *, analysis_service: Any | None = None, persistence_service: Any = AnalysisPersistenceService) -> None:
        self.provider = provider
        self.settings = settings or get_settings()
        self.classifier = ThemeClassifier(self.settings)
        self.analysis_service = analysis_service
        self.persistence_service = persistence_service

    def _heuristic_analysis(self, title: str, summary: str | None) -> HeuristicNewsAnalysis:
        text = f"{title} {summary or ''}"
        matches = self.classifier.classify(text)
        positive = sum(text.count(word) for word in POSITIVE_WORDS)
        negative = sum(text.count(word) for word in NEGATIVE_WORDS)
        score = clamp((positive - negative) / max(3, positive + negative), -1, 1)
        direction = "positive" if score > 0.15 else "negative" if score < -0.15 else "mixed" if positive or negative else "neutral"
        return HeuristicNewsAnalysis([title], [], ["仅基于标题与可用摘要，需结合行情验证"] if summary is None else [], [item.theme_l2 for item in matches], direction, "1w", float(score))

    def _analysis_input(self, record: NewsRecord) -> VerifiedAnalysisInput:
        source = record.source.strip().lower()
        source_is_mock = source in {"mock", "mock-news"} or source.startswith(("mock:", "mock-news:"))
        is_mock = isinstance(self.provider, MockProvider) or getattr(self.provider, "name", "").strip().lower() == "mock" or source_is_mock
        return VerifiedAnalysisInput(
            instrument=None,
            provenance=DataProvenance(
                source=record.source,
                source_timestamp=record.published_at,
                data_cutoff=record.published_at,
                freshness=Freshness.DEGRADED if is_mock else Freshness.UNKNOWN,
                degraded=is_mock,
                mock=is_mock,
            ),
            news_title=record.title,
            news_body=record.summary,
            evidence_ids=(f"news:{record.source}:{record.source_id}",),
            prompt_version=self.settings.analysis_prompt_version,
            schema_version=self.settings.analysis_schema_version,
        )

    def _operation_service(self) -> tuple[Any | None, bool]:
        if not self.settings.analysis_enabled:
            return None, False
        return (self.analysis_service, False) if self.analysis_service is not None else (AnalysisService(self.settings), True)

    def _persist(self, db: Session, record: NewsRecord, item: NewsItem, service: Any) -> AnalysisEnvelope:
        data = self._analysis_input(record)
        expected_provider = self.settings.analysis_primary_provider or AnalysisProvider.CODEX_OPENAI_RESPONSES
        expected_model = self.settings.analysis_primary_model.strip() or "analysis-invalid-config"
        expected_prompt = self.settings.analysis_prompt_version
        expected_schema = self.settings.analysis_schema_version
        try:
            envelope = service.analyze(data)
            envelope = envelope if isinstance(envelope, AnalysisEnvelope) else AnalysisEnvelope.model_validate(envelope)
            if (
                envelope.input_hash != data.input_hash
                or envelope.provider is not expected_provider
                or envelope.model != expected_model
                or envelope.prompt_version != expected_prompt
                or envelope.schema_version != expected_schema
            ):
                raise ValueError("analysis envelope provenance mismatch")
        except Exception:
            envelope = AnalysisEnvelope(
                status=AnalysisStatus.INVALID_RESPONSE,
                provider=expected_provider,
                model=expected_model,
                latency_ms=0,
                input_hash=data.input_hash,
                prompt_version=expected_prompt,
                schema_version=expected_schema,
                failure_class="invalid_analysis_provenance",
            )
        self.persistence_service.record(
            db,
            envelope,
            news_item_id=item.id,
            expected_input_hash=data.input_hash,
            expected_provider=expected_provider,
            expected_model=expected_model,
            expected_prompt_version=expected_prompt,
            expected_schema_version=expected_schema,
        )
        item.analysis_source = envelope.provider.value
        item.analysis_status = envelope.status.value
        return envelope

    def _store(
        self,
        db: Session,
        record: NewsRecord,
        service: Any | None,
        counters: dict[str, int],
        existing: NewsItem | None = None,
        *,
        reuse_analysis: bool = False,
    ) -> None:
        heuristic = self._heuristic_analysis(record.title, record.summary)
        if existing is None:
            existing = NewsItem(source=record.source, source_id=record.source_id, title=record.title, published_at=record.published_at, quality_hash=stable_hash({**record.to_dict(), "heuristic": heuristic.model_dump()}))
            db.add(existing)
            db.flush()
            counters["inserted"] += 1
        else:
            counters["updated"] += 1
        existing.title, existing.summary, existing.url, existing.published_at = record.title, record.summary, record.url, record.published_at
        existing.facts_json, existing.inferences_json, existing.risk_flags_json = heuristic.facts, heuristic.inferences, heuristic.risk_flags
        existing.affected_themes_json, existing.impact_direction, existing.impact_horizon, existing.impact_score = heuristic.affected_themes, heuristic.impact_direction, heuristic.impact_horizon, heuristic.impact_score
        existing.llm_model = None
        existing.quality_hash = stable_hash({**record.to_dict(), "heuristic": heuristic.model_dump()})
        if reuse_analysis:
            counters["analysis_reused"] += 1
            return
        if service is None:
            existing.analysis_run_id = None
            existing.analysis_source, existing.analysis_status = "heuristic", "disabled"
            counters["analysis_disabled"] += 1
            return
        envelope = self._persist(db, record, existing, service)
        if envelope.status is AnalysisStatus.COMPLETED:
            counters["analysis_completed"] += 1
        elif envelope.status is AnalysisStatus.ANALYSIS_UNAVAILABLE:
            counters["analysis_unavailable"] += 1
        elif envelope.status is AnalysisStatus.FAILED:
            counters["analysis_failed"] += 1
        else:
            counters["analysis_invalid"] += 1

    def _run(
        self,
        db: Session,
        records: list[NewsRecord],
        existing: dict[tuple[str, str], NewsItem] | None,
        provider_calls: int,
        reuse_keys: set[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        counters = {
            "inserted": 0,
            "updated": 0,
            "analysis_completed": 0,
            "analysis_unavailable": 0,
            "analysis_invalid": 0,
            "analysis_failed": 0,
            "analysis_disabled": 0,
            "analysis_reused": 0,
        }
        service, owned = self._operation_service()
        reuse_keys = reuse_keys or set()
        try:
            for record in records:
                self._store(
                    db,
                    record,
                    service,
                    counters,
                    (existing or {}).get((record.source, record.source_id)),
                    reuse_analysis=(record.source, record.source_id) in reuse_keys,
                )
            db.flush()
        finally:
            if owned and service is not None and callable(getattr(service, "close", None)):
                service.close()
        counters["provider_calls"] = provider_calls
        return counters

    def refresh(self, db: Session, since_hours: int = 30, run_id: str | None = None) -> dict[str, Any]:
        run_id = run_id or uuid4().hex
        timer = AuditTimer()
        try:
            records = self.provider.fetch_news(since_hours)
        except Exception as exc:
            sanitized = NewsProviderRefreshError("fetch_news", type(exc).__name__)
            for trace in getattr(self.provider, "last_trace", ()) or ():
                if getattr(trace, "reason", None):
                    trace.reason = str(sanitized)
            record_provider_audit(
                db,
                run_id=run_id,
                operation="fetch_news",
                provider=self.provider,
                error=sanitized,
                latency_ms=timer.elapsed_ms,
            )
            db.flush()
            raise sanitized from None
        record_provider_audit(
            db,
            run_id=run_id,
            operation="fetch_news",
            provider=self.provider,
            result=records,
            latency_ms=timer.elapsed_ms,
        )
        existing = {(row.source, row.source_id): row for row in db.scalars(select(NewsItem)).all()}
        result = self._run(db, records, existing, 1)
        emit_event(
            db,
            "news.updated",
            {
                "run_id": run_id,
                "inserted": result["inserted"],
                "updated": result["updated"],
                "analysis_completed": result["analysis_completed"],
                "analysis_unavailable": result["analysis_unavailable"],
                "analysis_invalid": result["analysis_invalid"],
                "analysis_failed": result["analysis_failed"],
                "analysis_disabled": result["analysis_disabled"],
                "analysis_reused": result["analysis_reused"],
            },
        )
        result.update({"run_id": run_id, "provider_error": None})
        return result

    def _analysis_is_reusable(self, db: Session, row: NewsItem, input_data: VerifiedAnalysisInput) -> bool:
        expected_provider = self.settings.analysis_primary_provider or AnalysisProvider.CODEX_OPENAI_RESPONSES
        expected_model = self.settings.analysis_primary_model.strip() or "analysis-invalid-config"
        if (
            row.analysis_run_id is None
            or row.analysis_source != expected_provider.value
            or row.analysis_status != AnalysisStatus.COMPLETED.value
        ):
            return False
        try:
            run = db.get(AnalysisRun, row.analysis_run_id)
        except Exception:
            return False
        return bool(
            run is not None
            and run.status == AnalysisStatus.COMPLETED.value
            and run.input_hash == input_data.canonical_hash
            and run.provider == expected_provider.value
            and run.model == expected_model
            and run.prompt_version == self.settings.analysis_prompt_version
            and run.schema_version == self.settings.analysis_schema_version
        )

    def analyze_existing(
        self,
        db: Session,
        limit: int = 30,
        *,
        force: bool = False,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or uuid4().hex
        bounded_limit = max(0, min(int(limit), 1000))
        rows = db.scalars(
            select(NewsItem)
            .order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
            .limit(bounded_limit)
        ).all()
        records = [NewsRecord(source=row.source, source_id=row.source_id, title=row.title, summary=row.summary, url=row.url, published_at=row.published_at) for row in rows]
        existing = {(row.source, row.source_id): row for row in rows}
        reuse_keys = {
            (record.source, record.source_id)
            for row, record in zip(rows, records, strict=True)
            if not force and self._analysis_is_reusable(db, row, self._analysis_input(record))
        }
        result = self._run(db, records, existing, 0, reuse_keys)
        result.update({"run_id": run_id, "status": "succeeded"})
        emit_event(db, "news.analysis.updated", dict(result))
        return result
