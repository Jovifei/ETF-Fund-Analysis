from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    StringConstraints,
    ValidationError,
    field_validator,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AgentReviewCandidate
from app.models.entities import REVIEW_MEMO_MAX_SERIALIZED_CHARS, REVIEW_NOTE_MAX_CHARS
from app.services.analysis_persistence_service import ensure_analysis_storage_ready
from app.utils.canonical_json import canonical_dumps, canonical_hash, validate_safe_text

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ALLOWED_RUNNERS = frozenset({"codex_review_runner", "claude_code_review_runner"})
_MAX_MEMO_CHARS = REVIEW_MEMO_MAX_SERIALIZED_CHARS
_MemoSummary = Annotated[StrictStr, StringConstraints(min_length=1, max_length=4000)]
_MemoEvidence = Annotated[StrictStr, StringConstraints(min_length=1, max_length=512)]
_MemoRisk = Annotated[StrictStr, StringConstraints(min_length=1, max_length=2000)]


class CandidateNotFoundError(LookupError):
    pass


class ReviewMemo(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    summary: _MemoSummary
    evidence_ids: tuple[_MemoEvidence, ...] = Field(default=(), max_length=128)
    risk_flags: tuple[_MemoRisk, ...] = Field(default=(), max_length=32)
    limitations: tuple[_MemoRisk, ...] = Field(default=(), max_length=32)

    @field_validator("evidence_ids", "risk_flags", "limitations", mode="before")
    @classmethod
    def reject_untyped_collections(cls, value: object) -> object:
        if isinstance(value, (set, frozenset, Mapping)):
            raise ValueError("memo collections must be ordered sequences")
        if not isinstance(value, (list, tuple)):
            raise ValueError("memo collections must be ordered sequences")
        # Pydantic strict mode intentionally rejects list -> tuple coercion.  The
        # public persistence boundary accepts JSON arrays, then normalizes them
        # to immutable tuples before canonical serialization.
        return tuple(value)

    @field_validator("summary", "evidence_ids", "risk_flags", "limitations")
    @classmethod
    def reject_sensitive_content(cls, value: Any) -> Any:
        if isinstance(value, str):
            return validate_safe_text(value)
        return tuple(validate_safe_text(item) for item in value)


def _strict_hash(value: str, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a strict 64-hex SHA-256 hash")
    return value.lower()


def _canonical(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _validated_memo(value: Any) -> tuple[ReviewMemo, str]:
    try:
        memo = ReviewMemo.model_validate(_canonical(value))
    except ValidationError as exc:
        raise ValueError("memo schema validation failed") from exc
    serialized = canonical_dumps(memo.model_dump(mode="json"), object_only=True)
    if len(serialized) > _MAX_MEMO_CHARS:
        raise ValueError("memo exceeds the bounded persistence size")
    return memo, serialized


def _sanitize_note(note: str | None) -> str | None:
    if note is None:
        return None
    if not isinstance(note, str) or len(note) > REVIEW_NOTE_MAX_CHARS:
        raise ValueError("review_note must be at most 2000 characters")
    return validate_safe_text(note)


class ReviewService:
    allowed_runners = _ALLOWED_RUNNERS

    @staticmethod
    def enqueue_from_hash(
        db: Session,
        *,
        runner: str,
        bundle_hash: str,
        memo: Any,
        memo_hash: str | None = None,
        candidate_id: str | None = None,
    ) -> AgentReviewCandidate:
        """Persist a review candidate from a pre-hashed bundle only.

        The application review API intentionally receives no raw bundle.  This
        wrapper keeps that boundary explicit while sharing the existing strict
        memo/hash validation and storage-readiness checks.
        """
        return ReviewService.enqueue_candidate(
            db,
            runner=runner,
            bundle=None,
            memo=memo,
            bundle_hash=bundle_hash,
            memo_hash=memo_hash,
            candidate_id=candidate_id,
        )

    @staticmethod
    def enqueue_candidate(
        db: Session,
        *,
        runner: str,
        bundle: Any = None,
        memo: Any = None,
        bundle_hash: str | None = None,
        memo_hash: str | None = None,
        candidate_id: str | None = None,
    ) -> AgentReviewCandidate:
        ensure_analysis_storage_ready(db)
        if runner not in _ALLOWED_RUNNERS:
            raise ValueError("runner is not allowlisted")
        if bundle is None and bundle_hash is None:
            raise ValueError("bundle or bundle_hash is required")
        if memo is None:
            raise ValueError("memo is required for hash-bound persistence")
        _, memo_text = _validated_memo(memo)
        memo_payload = json.loads(memo_text)
        computed_bundle_hash = canonical_hash(_canonical(bundle)) if bundle is not None else None
        computed_memo_hash = canonical_hash(memo_payload, object_only=True)
        normalized_bundle_hash = _strict_hash(bundle_hash, "bundle_hash") if bundle_hash is not None else computed_bundle_hash
        normalized_memo_hash = _strict_hash(memo_hash, "memo_hash") if memo_hash is not None else computed_memo_hash
        if computed_bundle_hash is not None and normalized_bundle_hash != computed_bundle_hash:
            raise ValueError("bundle_hash does not match bundle")
        if normalized_memo_hash != computed_memo_hash:
            raise ValueError("memo_hash does not match memo")
        assert normalized_bundle_hash is not None
        candidate = AgentReviewCandidate(
            candidate_id=candidate_id or uuid4().hex,
            runner=runner,
            bundle_hash=normalized_bundle_hash,
            memo_hash=normalized_memo_hash,
            memo_json=memo_text,
            review_status="pending",
        )
        db.add(candidate)
        db.flush()
        return candidate

    enqueue = enqueue_candidate

    @staticmethod
    def get(db: Session, candidate_id: str) -> AgentReviewCandidate:
        ensure_analysis_storage_ready(db)
        candidate = db.scalar(select(AgentReviewCandidate).where(AgentReviewCandidate.candidate_id == candidate_id))
        if candidate is None:
            raise CandidateNotFoundError("review candidate not found")
        return candidate

    @staticmethod
    def list(db: Session, *, review_status: str | None = None, runner: str | None = None, limit: int = 100) -> list[AgentReviewCandidate]:
        ensure_analysis_storage_ready(db)
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        statement = select(AgentReviewCandidate)
        if review_status is not None:
            if review_status not in {"pending", "accepted", "rejected"}:
                raise ValueError("unknown review status")
            statement = statement.where(AgentReviewCandidate.review_status == review_status)
        if runner is not None:
            if runner not in _ALLOWED_RUNNERS:
                raise ValueError("runner is not allowlisted")
            statement = statement.where(AgentReviewCandidate.runner == runner)
        return list(db.scalars(statement.order_by(AgentReviewCandidate.created_at.desc()).limit(limit)).all())

    @staticmethod
    def _transition(db: Session, candidate_id: str, target: str, note: str | None) -> AgentReviewCandidate:
        ensure_analysis_storage_ready(db)
        if target not in {"accepted", "rejected"}:
            raise ValueError("invalid review transition")
        sanitized_note = _sanitize_note(note)
        now = datetime.now(UTC)
        result = db.execute(
            update(AgentReviewCandidate)
            .where(AgentReviewCandidate.candidate_id == candidate_id, AgentReviewCandidate.review_status == "pending")
            # Do not let SQLAlchemy partially synchronize an identity-mapped
            # object: the refresh event validates complete persisted state, and
            # a partial in-memory row would look incoherent during the UPDATE.
            .execution_options(synchronize_session=False)
            .values(
                review_status=target,
                review_note=sanitized_note,
                updated_at=now,
                accepted_at=now if target == "accepted" else None,
                rejected_at=now if target == "rejected" else None,
            )
        )
        if result.rowcount == 0:
            # Refresh explicitly: callers may have loaded this candidate in the
            # same Session and SQLAlchemy sessions intentionally do not expire on
            # commit.  This keeps the conditional-update decision race-safe and
            # portable across dialects with different rowcount behavior.
            candidate = db.scalar(
                select(AgentReviewCandidate)
                .where(AgentReviewCandidate.candidate_id == candidate_id)
                .execution_options(populate_existing=True)
            )
            if candidate is None:
                raise CandidateNotFoundError("review candidate not found")
            if candidate.review_status == target:
                return candidate
            if candidate.review_status != "pending":
                raise ValueError("terminal review candidate cannot change state")
            raise ValueError("review transition lost its conditional update race")
        return db.scalar(
            select(AgentReviewCandidate)
            .where(AgentReviewCandidate.candidate_id == candidate_id)
            .execution_options(populate_existing=True)
        ) or ReviewService.get(db, candidate_id)

    @staticmethod
    def accept(db: Session, candidate_id: str, note: str | None = None) -> AgentReviewCandidate:
        return ReviewService._transition(db, candidate_id, "accepted", note)

    @staticmethod
    def reject(db: Session, candidate_id: str, note: str | None = None) -> AgentReviewCandidate:
        return ReviewService._transition(db, candidate_id, "rejected", note)

    @staticmethod
    def validate_integrity(db: Session) -> int:
        rows = list(db.scalars(select(AgentReviewCandidate).execution_options(populate_existing=True)).all())
        return len(rows)
