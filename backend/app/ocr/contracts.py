from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from typing import Annotated, Literal, Protocol, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

OCRText: TypeAlias = Annotated[StrictStr, StringConstraints(min_length=1, max_length=2000)]
OCRIdentifier: TypeAlias = Annotated[StrictStr, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
SHA256Hash: TypeAlias = Annotated[StrictStr, StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")]
Confidence: TypeAlias = Annotated[StrictInt | StrictFloat, Field(ge=0.0, le=1.0)]
Coordinate: TypeAlias = Annotated[StrictInt | StrictFloat, Field(ge=0.0, le=1_000_000.0)]

class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True, str_strip_whitespace=True)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("OCR timestamps must be timezone-aware")
    return value.astimezone(UTC)


class OCRBox(_Contract):
    """A four-corner quadrilateral in source-image pixel coordinates."""

    points: tuple[tuple[Coordinate, Coordinate], ...] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def exactly_four_points(self) -> OCRBox:
        if len(self.points) != 4:
            raise ValueError("OCR boxes must contain exactly four points")
        return self


class OCRLine(_Contract):
    text: OCRText
    confidence: Confidence
    box: OCRBox | None = None

    @property
    def recognized_text(self) -> str:
        return self.text

    @field_validator("confidence")
    @classmethod
    def finite_confidence(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("OCR confidence must be finite")
        return value


class OCRResult(_Contract):
    status: Literal["completed"] = "completed"
    lines: tuple[OCRLine, ...] = Field(default=(), max_length=512)
    backend: OCRIdentifier
    model: OCRIdentifier
    version: OCRIdentifier
    processed_at: datetime
    image_sha256: SHA256Hash | None = None

    _normalize_timestamp = field_validator("processed_at")(_utc)

    @property
    def recognized_lines(self) -> tuple[OCRLine, ...]:
        return self.lines

    @field_validator("lines", mode="before")
    @classmethod
    def reject_untyped_lines(cls, value: object) -> object:
        if isinstance(value, (set, frozenset, Mapping)):
            raise ValueError("lines must be an ordered sequence")
        return value


class OCRUnavailableReason(StrEnum):
    MODEL_DIRECTORY_MISSING = "model_directory_missing"
    MODEL_DIRECTORY_UNQUALIFIED = "model_directory_unqualified"
    PADDLEOCR_PACKAGE_MISSING = "paddleocr_package_missing"
    PADDLE_PACKAGE_MISSING = "paddle_package_missing"
    ENGINE_UNAVAILABLE = "engine_unavailable"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    TIMEOUT = "timeout"
    INVALID_IMAGE = "invalid_image"
    WORKER_CLEANUP_FAILED = "worker_cleanup_failed"


class OCRUnavailable(_Contract):
    """A sanitized, typed unavailable result; never includes exception details."""

    status: Literal["ocr_unavailable"] = "ocr_unavailable"
    reason: OCRUnavailableReason
    backend: OCRIdentifier = "local_paddle"
    model: OCRIdentifier = "unavailable"
    version: OCRIdentifier = "unavailable"


class CandidateField(StrEnum):
    TS_CODE = "ts_code"
    NAME = "name"
    SHARES = "shares"
    COST_PRICE = "cost_price"
    TARGET_WEIGHT = "target_weight"


class ConfidenceEntry(_Contract):
    field: CandidateField
    confidence: Confidence

    @field_validator("confidence")
    @classmethod
    def finite_confidence(cls, value: int | float) -> int | float:
        if not isfinite(value):
            raise ValueError("field confidence must be finite")
        return value


class OCRMatchStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"
    LOW_CONFIDENCE = "low_confidence"
    DUPLICATE = "duplicate"


class OCRCandidateStatus(StrEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"


class OCRCandidateAction(StrEnum):
    NONE = "none"
    CONFIRM = "confirm"
    REJECT = "reject"


class HoldingCandidate(_Contract):
    """Allowlisted, editable holding fields derived from an OCR row."""

    row_index: StrictInt = Field(ge=0, le=10_000)
    ts_code: Annotated[StrictStr, StringConstraints(min_length=1, max_length=32)] | None = None
    name: Annotated[StrictStr, StringConstraints(min_length=1, max_length=128)] | None = None
    shares: StrictInt | StrictFloat | None = Field(default=None, ge=0, le=1_000_000_000)
    cost_price: StrictInt | StrictFloat | None = Field(default=None, ge=0, le=1_000_000_000)
    target_weight: StrictInt | StrictFloat | None = Field(default=None, ge=0, le=1)
    user_note: Annotated[StrictStr, StringConstraints(min_length=1, max_length=2000)] | None = None
    match_status: OCRMatchStatus = OCRMatchStatus.UNMATCHED
    status: OCRCandidateStatus = OCRCandidateStatus.PENDING
    action: OCRCandidateAction = OCRCandidateAction.NONE
    safe_alternatives: tuple[Annotated[StrictStr, StringConstraints(min_length=1, max_length=128)], ...] = Field(default=(), max_length=16)
    field_confidence: tuple[ConfidenceEntry, ...] = Field(default=(), max_length=6)
    normalized_ocr_text_hash: SHA256Hash | None = None
    selected_code: Annotated[StrictStr, StringConstraints(min_length=1, max_length=32)] | None = None

    @property
    def field_confidences(self) -> tuple[ConfidenceEntry, ...]:
        return self.field_confidence

    @field_validator("safe_alternatives", mode="before")
    @classmethod
    def reject_untyped_alternatives(cls, value: object) -> object:
        if isinstance(value, (set, frozenset, Mapping)):
            raise ValueError("safe_alternatives must be ordered")
        return value

    @field_validator("field_confidence", mode="before")
    @classmethod
    def reject_mutable_confidence(cls, value: object) -> object:
        if isinstance(value, (Mapping, set, frozenset)):
            raise ValueError("field_confidence must be an ordered immutable sequence")
        return value

    @model_validator(mode="after")
    def unique_confidence_fields(self) -> HoldingCandidate:
        fields = [entry.field for entry in self.field_confidence]
        if len(fields) != len(set(fields)):
            raise ValueError("field_confidence fields must be unique")
        return self

    @field_validator("shares", "cost_price", "target_weight")
    @classmethod
    def finite_numbers(cls, value: int | float | None) -> int | float | None:
        if value is not None and not isfinite(value):
            raise ValueError("candidate numbers must be finite")
        return value

    @model_validator(mode="after")
    def coherent_action(self) -> HoldingCandidate:
        if self.status is OCRCandidateStatus.CONFIRMED and self.action is not OCRCandidateAction.CONFIRM:
            raise ValueError("confirmed candidate requires confirm action")
        if self.status is OCRCandidateStatus.REJECTED and self.action is not OCRCandidateAction.REJECT:
            raise ValueError("rejected candidate requires reject action")
        if self.status in {OCRCandidateStatus.PENDING, OCRCandidateStatus.REVIEWED} and self.action is not OCRCandidateAction.NONE:
            raise ValueError("pending/reviewed candidate requires no terminal action")
        return self


# Descriptive compatibility aliases used by adapters and future C2 code.
RecognizedTextBox = OCRBox
RecognizedLine = OCRLine
OCRRecognizedLine = OCRLine
OCRRecognizedTextLine = OCRLine
OCRRecognizedTextBox = OCRBox
HoldingImportCandidateContract = HoldingCandidate
NormalizedHoldingCandidate = HoldingCandidate
NormalizedCandidate = HoldingCandidate


class OCRBackend(Protocol):
    def recognize(self, image: bytes) -> OCRResult | OCRUnavailable: ...
