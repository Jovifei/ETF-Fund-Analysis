from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from typing import Annotated, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.utils.canonical_json import canonical_hash

Identifier = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=96, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$"),
]
BoundedText = Annotated[StrictStr, StringConstraints(min_length=1, max_length=12000)]
ShortText = Annotated[StrictStr, StringConstraints(min_length=1, max_length=512)]
SHA256Hash = Annotated[
    StrictStr,
    StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$"),
]

# Public so persistence layers use the exact same sanitized failure-class grammar.
FAILURE_CLASS_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$"


class AnalysisProvider(StrEnum):
    CODEX_OPENAI_RESPONSES = "codex_openai_responses"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    DEEPSEEK_OPENAI_COMPATIBLE = "deepseek_openai_compatible"


AnalysisProviderName = AnalysisProvider


class AnalysisStatus(StrEnum):
    COMPLETED = "completed"
    SUCCESS = "completed"
    ANALYSIS_UNAVAILABLE = "analysis_unavailable"
    INVALID_RESPONSE = "invalid_response"
    FAILED = "failed"


AnalysisRunStatus = AnalysisStatus


class Horizon(StrEnum):
    INTRADAY = "intraday"
    ONE_WEEK = "1w"
    ONE_MONTH = "1m"


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class CalibrationStatus(StrEnum):
    CALIBRATED = "calibrated"
    NOT_CALIBRATED = "not_calibrated"
    INSUFFICIENT_DATA = "insufficient_data"
    UNKNOWN = "unknown"


class _ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class InstrumentIdentity(_ContractModel):
    standard_code: ShortText
    name: ShortText
    theme_l1: ShortText | None = None
    theme_l2: ShortText | None = None
    configured_benchmark: ShortText | None = None


class DataProvenance(_ContractModel):
    source: ShortText
    source_timestamp: datetime | None = None
    data_cutoff: datetime | None = None
    freshness: Freshness = Freshness.UNKNOWN
    degraded: bool = False
    mock: bool = False
    strategy_version: ShortText | None = None
    indicator_version: ShortText | None = None
    forecast_version: ShortText | None = None

    _normalize_timestamps = field_validator("source_timestamp", "data_cutoff")(_utc)

    @property
    def is_degraded(self) -> bool:
        return self.degraded

    @property
    def is_mock(self) -> bool:
        return self.mock


class IndicatorFact(_ContractModel):
    name: Identifier
    value: StrictInt | StrictFloat
    unit: ShortText | None = None
    as_of: datetime | None = None
    version: ShortText | None = None

    _normalize_timestamp = field_validator("as_of")(_utc)

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: int | float) -> int | float:
        if not isfinite(value):
            raise ValueError("indicator value must be finite")
        return value


class PortfolioExposure(_ContractModel):
    shares: StrictInt | StrictFloat | None = Field(default=None, ge=0, le=1_000_000_000)
    cost: StrictInt | StrictFloat | None = Field(default=None, ge=0, le=1_000_000_000)
    current_weight: StrictInt | StrictFloat | None = Field(default=None, ge=0, le=1)
    target_weight: StrictInt | StrictFloat | None = Field(default=None, ge=0, le=1)

    @field_validator("shares", "cost", "current_weight", "target_weight")
    @classmethod
    def finite_values(cls, value: int | float | None) -> int | float | None:
        if value is not None and not isfinite(value):
            raise ValueError("portfolio exposure values must be finite")
        return value


class ForecastFact(_ContractModel):
    horizon: Horizon
    p_up: StrictInt | StrictFloat | None = Field(default=None, ge=0, le=1)
    expected_return: StrictInt | StrictFloat | None = Field(default=None, ge=-100, le=100)
    q10: StrictInt | StrictFloat | None = Field(default=None, ge=-100, le=100)
    q50: StrictInt | StrictFloat | None = Field(default=None, ge=-100, le=100)
    q90: StrictInt | StrictFloat | None = Field(default=None, ge=-100, le=100)
    sample_count: StrictInt | None = Field(default=None, ge=0, le=10_000_000)
    confidence: Literal["low", "medium", "high"] | None = None
    model_version: ShortText
    calibration_status: CalibrationStatus
    data_cutoff: datetime | None = None

    _normalize_timestamp = field_validator("data_cutoff")(_utc)

    @field_validator("p_up", "expected_return", "q10", "q50", "q90")
    @classmethod
    def finite_values(cls, value: int | float | None) -> int | float | None:
        if value is not None and not isfinite(value):
            raise ValueError("forecast values must be finite")
        return value


class VerifiedAnalysisInput(_ContractModel):
    """Allowlisted deterministic evidence supplied to a direct model adapter."""

    instrument: InstrumentIdentity | None = None
    provenance: DataProvenance | None = None
    indicators: tuple[IndicatorFact, ...] = Field(default=(), max_length=128)
    signal_state: Identifier | None = None
    portfolio_exposure: PortfolioExposure | None = None
    forecast_statistics: tuple[ForecastFact, ...] = Field(default=(), max_length=32)
    news_title: ShortText | None = None
    news_body: BoundedText | None = None
    evidence_ids: tuple[ShortText, ...] = Field(default=(), max_length=128)
    prompt_version: ShortText = "analysis-v1"
    schema_version: ShortText = "analysis-v1"

    @field_validator("indicators", "forecast_statistics", "evidence_ids", mode="before")
    @classmethod
    def reject_untyped_collections(cls, value: object) -> object:
        if isinstance(value, (set, frozenset, Mapping)):
            raise ValueError("analysis collections must be ordered typed sequences")
        return value

    @property
    def canonical_hash(self) -> SHA256Hash:
        return canonical_hash(self.model_dump(mode="json"), object_only=True)

    @property
    def input_hash(self) -> SHA256Hash:
        return self.canonical_hash

    @property
    def instrument_code(self) -> str | None:
        return self.instrument.standard_code if self.instrument else None

    @property
    def standard_name(self) -> str | None:
        return self.instrument.name if self.instrument else None

    @property
    def configured_benchmark(self) -> str | None:
        return self.instrument.configured_benchmark if self.instrument else None

    @property
    def is_degraded(self) -> bool:
        return self.provenance.degraded if self.provenance else False

    @property
    def is_mock(self) -> bool:
        return self.provenance.mock if self.provenance else False


class AnalysisOutput(_ContractModel):
    """Candidate text analysis; deterministic numeric decision fields are forbidden."""

    facts: tuple[BoundedText, ...] = Field(default=(), max_length=32)
    inferences: tuple[BoundedText, ...] = Field(default=(), max_length=32)
    risk_flags: tuple[BoundedText, ...] = Field(default=(), max_length=32)
    affected_themes: tuple[ShortText, ...] = Field(default=(), max_length=32)
    impact_horizon: Horizon = Horizon.ONE_WEEK
    evidence_ids: tuple[ShortText, ...] = Field(default=(), max_length=128)
    confidence_statement: BoundedText | None = Field(default=None, max_length=2000)
    provider: AnalysisProvider | None = None
    model: ShortText | None = None
    prompt_version: ShortText | None = None

    @field_validator("facts", "inferences", "risk_flags", "affected_themes", "evidence_ids", mode="before")
    @classmethod
    def reject_untyped_collections(cls, value: object) -> object:
        if isinstance(value, (set, frozenset, Mapping)):
            raise ValueError("analysis collections must be ordered typed sequences")
        return value

    @model_validator(mode="after")
    def require_substantive_candidate(self) -> AnalysisOutput:
        if not (self.facts or self.inferences or self.risk_flags):
            raise ValueError("analysis output requires a substantive fact, inference, or risk")
        if self.confidence_statement is None or not self.confidence_statement.strip():
            raise ValueError("analysis output requires a confidence statement")
        return self

    @property
    def result_hash(self) -> SHA256Hash:
        return canonical_hash(self.model_dump(mode="json"), object_only=True)

    @property
    def output_hash(self) -> SHA256Hash:
        return self.result_hash


class AnalysisEnvelope(_ContractModel):
    status: AnalysisStatus
    provider: AnalysisProvider
    model: ShortText
    latency_ms: FiniteFloat = Field(ge=0, le=86_400_000)
    input_hash: SHA256Hash
    prompt_version: ShortText
    schema_version: ShortText
    output: AnalysisOutput | None = None
    result_hash: SHA256Hash | None = None
    failure_class: Annotated[
        StrictStr,
        StringConstraints(
            min_length=1,
            max_length=128,
            pattern=FAILURE_CLASS_PATTERN,
        ),
    ] | None = None

    @model_validator(mode="after")
    def validate_status_coherence(self) -> AnalysisEnvelope:
        if self.status is AnalysisStatus.COMPLETED:
            if self.output is None or self.result_hash is None:
                raise ValueError("completed analysis requires output and result_hash")
            if self.result_hash.lower() != self.output.result_hash.lower():
                raise ValueError("result_hash does not match output")
            if self.failure_class is not None:
                raise ValueError("completed analysis cannot contain failure_class")
            return self
        if self.status in {
            AnalysisStatus.ANALYSIS_UNAVAILABLE,
            AnalysisStatus.INVALID_RESPONSE,
            AnalysisStatus.FAILED,
        }:
            if self.output is not None or self.result_hash is not None:
                raise ValueError("unavailable analysis cannot contain output or result_hash")
            if self.failure_class is None:
                raise ValueError("unavailable analysis requires failure_class")
        return self


class AnalysisAdapter(Protocol):
    def analyze(self, input_data: VerifiedAnalysisInput) -> AnalysisEnvelope:
        ...


AnalysisAdapterProtocol = AnalysisAdapter
