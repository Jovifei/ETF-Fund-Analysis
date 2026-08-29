from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.analysis.contracts import AnalysisEnvelope, AnalysisProvider, AnalysisStatus
from app.models import AgentReviewCandidate, AnalysisRun, NewsItem
from app.utils.canonical_json import canonical_dumps, canonical_hash_text


class AnalysisPersistenceError(ValueError):
    """Raised when a validated analysis envelope cannot be persisted safely."""


class AnalysisStorageNotMigrated(RuntimeError):
    """Raised when the append-only analysis schema is not installed."""


_REQUIRED_ANALYSIS_TRIGGERS = (
    ("trg_analysis_runs_append_only", "analysis_runs"),
    ("trg_analysis_runs_no_delete", "analysis_runs"),
    ("trg_agent_review_candidates_immutable", "agent_review_candidates"),
    ("trg_agent_review_candidates_no_delete", "agent_review_candidates"),
)


def ensure_analysis_storage_ready(db: Session) -> None:
    """Fail closed unless the migration-owned append-only triggers are present."""
    try:
        bind = db.get_bind()
        dialect = bind.dialect.name
        if dialect == "sqlite":
            for trigger_name, table_name in _REQUIRED_ANALYSIS_TRIGGERS:
                present = db.scalar(
                    text(
                        "SELECT 1 FROM sqlite_master "
                        "WHERE type = 'trigger' AND name = :trigger_name "
                        "AND tbl_name = :table_name"
                    ),
                    {"trigger_name": trigger_name, "table_name": table_name},
                )
                if present != 1:
                    raise AnalysisStorageNotMigrated("analysis storage migration is not applied")
        elif dialect == "postgresql":
            for trigger_name, table_name in _REQUIRED_ANALYSIS_TRIGGERS:
                present = db.scalar(
                    text(
                        "SELECT 1 "
                        "FROM pg_trigger AS trg "
                        "JOIN pg_class AS relation ON relation.oid = trg.tgrelid "
                        "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
                        "WHERE trg.tgname = :trigger_name "
                        "AND relation.relname = :table_name "
                        "AND namespace.nspname = current_schema() "
                        "AND NOT trg.tgisinternal"
                    ),
                    {"trigger_name": trigger_name, "table_name": table_name},
                )
                if present != 1:
                    raise AnalysisStorageNotMigrated("analysis storage migration is not applied")
        else:
            raise AnalysisStorageNotMigrated("analysis storage dialect is unsupported")
    except AnalysisStorageNotMigrated:
        raise
    except Exception as exc:
        raise AnalysisStorageNotMigrated("analysis storage migration readiness could not be verified") from exc


class AnalysisPersistenceService:
    @staticmethod
    def record(
        db: Session,
        envelope: AnalysisEnvelope | Mapping[str, Any],
        news_item_id: int | None = None,
        *,
        expected_input_hash: str | None = None,
        expected_provider: AnalysisProvider | str | None = None,
        expected_model: str | None = None,
        expected_prompt_version: str | None = None,
        expected_schema_version: str | None = None,
    ) -> AnalysisRun:
        ensure_analysis_storage_ready(db)
        try:
            validated = (
                envelope
                if isinstance(envelope, AnalysisEnvelope)
                else AnalysisEnvelope.model_validate(envelope)
            )
        except ValidationError as exc:
            raise AnalysisPersistenceError("analysis envelope validation failed") from exc

        expected_provider_value = (
            expected_provider.value
            if isinstance(expected_provider, AnalysisProvider)
            else expected_provider
        )
        expected_values = (
            (expected_input_hash, validated.input_hash),
            (expected_provider_value, validated.provider.value),
            (expected_model, validated.model),
            (expected_prompt_version, validated.prompt_version),
            (expected_schema_version, validated.schema_version),
        )
        if any(expected is not None and expected != actual for expected, actual in expected_values):
            raise AnalysisPersistenceError("analysis envelope provenance mismatch")

        status = validated.status.value
        output_json: str | None = None
        if validated.status is AnalysisStatus.COMPLETED:
            if validated.output is None or validated.result_hash is None:
                raise AnalysisPersistenceError("completed analysis requires output and result hash")
            output_json = canonical_dumps(validated.output.model_dump(mode="json"), object_only=True)
            if validated.result_hash.lower() != canonical_hash_text(output_json):
                raise AnalysisPersistenceError("analysis result hash does not match output")
            failure_class = None
        else:
            if validated.output is not None or validated.result_hash is not None:
                raise AnalysisPersistenceError("unavailable analysis cannot contain output or result hash")
            if not validated.failure_class:
                raise AnalysisPersistenceError("unavailable analysis requires failure class")
            failure_class = validated.failure_class

        if news_item_id is not None and db.get(NewsItem, news_item_id) is None:
            raise AnalysisPersistenceError("news item does not exist")

        run = AnalysisRun(
            provider=validated.provider.value,
            model=validated.model,
            status=status,
            latency_ms=float(validated.latency_ms),
            input_hash=validated.input_hash,
            prompt_version=validated.prompt_version,
            schema_version=validated.schema_version,
            result_hash=validated.result_hash,
            output_json=output_json,
            failure_class=failure_class,
        )
        db.add(run)
        db.flush()

        if news_item_id is not None:
            news_item = db.get(NewsItem, news_item_id)
            if news_item is not None:
                news_item.analysis_run_id = run.id
                news_item.analysis_source = validated.provider.value
                news_item.analysis_status = status
                db.flush()
        return run

    @staticmethod
    def validate_integrity(db: Session) -> int:
        """Force a fresh ORM load so raw/bulk mutations cannot remain undetected."""
        runs = list(db.scalars(select(AnalysisRun).execution_options(populate_existing=True)).all())
        candidates = list(db.scalars(select(AgentReviewCandidate).execution_options(populate_existing=True)).all())
        return len(runs) + len(candidates)
