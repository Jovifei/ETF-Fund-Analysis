from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from math import isfinite
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import ColumnElement

from app.analysis.contracts import FAILURE_CLASS_PATTERN
from app.db.base import Base
from app.ocr.contracts import CandidateField, ConfidenceEntry
from app.utils.canonical_json import (
    canonical_dumps,
    canonical_hash_text,
    canonical_loads,
    validate_review_memo_payload,
    validate_safe_text,
)

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_IDENTIFIER_RE = re.compile(FAILURE_CLASS_PATTERN)
REVIEW_MEMO_MAX_SERIALIZED_CHARS = 12000
REVIEW_NOTE_MAX_CHARS = 2000
OCR_MAX_NOTE_CHARS = 2000
_IMPORT_JSON_MAX_ALTERNATIVES = 16
_IMPORT_JSON_MAX_CONFIDENCE = 6
_IMPORT_FIELDS = frozenset(item.value for item in CandidateField)
_SENSITIVE_IMPORT_KEYS = frozenset(
    {"account", "account_number", "password", "identity", "cookie", "token", "secret", "raw_ocr", "raw_text", "ocr_text", "pixels"}
)


def _validate_safe_import_text(value: str, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("import text exceeds its bound")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError("import text contains a control character")
    return validate_safe_text(value)


def _validate_import_json(value: Any, kind: str) -> Any:
    if kind == "alternatives":
        if not isinstance(value, (list, tuple)) or len(value) > _IMPORT_JSON_MAX_ALTERNATIVES:
            raise ValueError("safe_alternatives_json must be a bounded ordered sequence")
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str) or not 1 <= len(item.strip()) <= 128:
                raise ValueError("safe alternatives must be bounded strings")
            cleaned = item.strip()
            if any(key in cleaned.casefold() for key in _SENSITIVE_IMPORT_KEYS):
                raise ValueError("safe alternatives contain a forbidden sensitive field")
            normalized.append(cleaned)
        return tuple(normalized)
    if not isinstance(value, (list, tuple)) or len(value) > _IMPORT_JSON_MAX_CONFIDENCE:
        raise ValueError("field_confidence_json must be a bounded ordered sequence")
    normalized_entries: list[ConfidenceEntry] = []
    fields: set[str] = set()
    for item in value:
        if isinstance(item, ConfidenceEntry):
            field, confidence = item.field.value, item.confidence
        elif isinstance(item, dict):
            if set(item) != {"field", "confidence"}:
                raise ValueError("field confidence entries contain unsupported keys")
            field, confidence = item["field"], item["confidence"]
        else:
            raise ValueError("field confidence entries must be typed mappings")
        if field not in _IMPORT_FIELDS or field in fields or not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("field confidence entry is invalid")
        fields.add(field)
        normalized_entries.append(ConfidenceEntry(field=field, confidence=confidence))
    return tuple(normalized_entries)


class _ValidatedImportJSON(TypeDecorator):
    impl = Text
    cache_ok = False

    def __init__(self, kind: str) -> None:
        self._kind = str(kind)
        super().__init__()

    def process_bind_param(self, value: Any, dialect: Any) -> str:
        del dialect
        normalized = _validate_import_json(value, self._kind)
        if self._kind == "confidence":
            normalized = [
                {"field": entry.field.value, "confidence": entry.confidence} for entry in normalized
            ]
        return canonical_dumps(list(normalized))

    def process_result_value(self, value: str | None, dialect: Any) -> Any:
        del dialect
        if value is None:
            return None
        parsed = canonical_loads(value)
        normalized = _validate_import_json(parsed, self._kind)
        if self._kind == "confidence":
            canonical_value = [
                {"field": entry.field.value, "confidence": entry.confidence} for entry in normalized
            ]
        else:
            canonical_value = list(normalized)
        if canonical_dumps(canonical_value) != value:
            raise ValueError("persisted OCR import JSON is not canonical")
        return normalized


class _SafeImportText(TypeDecorator):
    """Fail-closed text persistence for OCR candidate user-visible strings."""

    impl = String
    cache_ok = False

    def __init__(self, length: int) -> None:
        self._length = length
        super().__init__(length)

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        del dialect
        if value is None:
            return None
        if len(value) > self._length:
            raise ValueError("import text exceeds its bound")
        return _validate_safe_import_text(value, self._length)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        del dialect
        if value is None:
            return None
        if len(value) > self._length:
            raise ValueError("persisted import text exceeds its bound")
        return _validate_safe_import_text(value, self._length)


def _strict_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a strict 64-hex SHA-256 hash")
    return value.lower()


def _failure_class(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 128 or _IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError("failure_class must be a sanitized identifier")
    return value


def _canonical_object(value: str | None, field_name: str) -> Any | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be canonical JSON text")
    try:
        parsed = canonical_loads(value, object_only=True)
        canonical = canonical_dumps(parsed, object_only=True)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be canonical JSON text") from exc
    if canonical != value:
        raise ValueError(f"{field_name} must use canonical JSON serialization")
    return parsed


def _portable_hex_check(column: str) -> str:
    stripped = column
    for character in "0123456789abcdefABCDEF":
        stripped = f"replace({stripped}, '{character}', '')"
    return f"length({column}) = 64 AND {stripped} = ''"


def _portable_opaque_token_check(column: str, maximum: int = 128) -> str:
    stripped = column
    for character in "0123456789abcdef":
        stripped = f"replace({stripped}, '{character}', '')"
    return f"length({column}) BETWEEN 16 AND {maximum} AND lower({column}) = {column} AND {stripped} = ''"


def _portable_etf_code_check(column: str) -> str:
    stripped = column
    for character in "0123456789":
        stripped = f"replace({stripped}, '{character}', '')"
    stripped = f"replace({stripped}, '.', '')"
    return f"length({column}) = 9 AND substr({column}, 7, 1) = '.' AND {stripped} IN ('SH', 'SZ', 'BJ')"


def _portable_safe_text_check(column: str, maximum: int) -> str:
    blocked = (
        "http://", "https://", "www.", "bearer ", "token=", "token ", "secret=", "password", "passwd",
        "api_key", "authorization", "cookie", "traceback", "powershell", "cmd ", "bash ", "../", "..\\", "/", ":",
        "\n", "\r", "\t",
    )
    checks = [
        f"{column} = trim({column})",
        f"length({column}) BETWEEN 1 AND {maximum}",
    ]
    checks.extend(f"lower({column}) NOT LIKE '%{item}%'" for item in blocked)
    return " AND ".join(checks)


class _NoBackslash(ColumnElement[bool]):
    inherit_cache = False

    def __init__(self, column_name: str) -> None:
        self.column_name = column_name


@compiles(_NoBackslash, "sqlite")
def _compile_no_backslash_sqlite(element: _NoBackslash, compiler: Any, **_: Any) -> str:
    return f"instr({element.column_name}, char(92)) = 0"


@compiles(_NoBackslash, "postgresql")
def _compile_no_backslash_postgresql(element: _NoBackslash, compiler: Any, **_: Any) -> str:
    return f"position(chr(92) in {element.column_name}) = 0"


def _portable_failure_class_check(column: str) -> str:
    """SQLite equivalent of FAILURE_CLASS_PATTERN; PostgreSQL uses regex."""
    return (
        f"length({column}) BETWEEN 1 AND 128 AND "
        f"{column} GLOB '[A-Za-z_]*' AND "
        f"{column} NOT GLOB '*[^A-Za-z0-9_.]*' AND "
        f"{column} NOT GLOB '*.' AND "
        f"{column} NOT GLOB '*..*' AND "
        f"{column} NOT GLOB '*.[^A-Za-z_]*'"
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Instrument(Base, TimestampMixin):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="ETF")
    exchange: Mapped[str | None] = mapped_column(String(16))
    theme_l1: Mapped[str | None] = mapped_column(String(64), index=True)
    theme_l2: Mapped[str | None] = mapped_column(String(128), index=True)
    benchmark: Mapped[str | None] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    holding: Mapped[Holding | None] = relationship(back_populates="instrument", uselist=False)


class DailyBar(Base):
    __tablename__ = "daily_bars"
    __table_args__ = (
        UniqueConstraint("instrument_id", "trade_date", "adjust", name="uq_daily_bar_instrument_date_adjust"),
        Index("ix_daily_bars_instrument_date", "instrument_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"))
    trade_date: Mapped[date] = mapped_column(Date)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    pre_close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    pct_change: Mapped[float | None] = mapped_column(Float)
    adjust: Mapped[str] = mapped_column(String(8), default="none")
    source: Mapped[str] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    quality_hash: Mapped[str] = mapped_column(String(64), index=True)


class QuoteSnapshot(Base):
    __tablename__ = "quote_snapshots"
    __table_args__ = (Index("ix_quote_instrument_time", "instrument_id", "quote_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    quote_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    price: Mapped[float] = mapped_column(Float)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    pre_close: Mapped[float | None] = mapped_column(Float)
    pct_change: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    premium_rate: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32))
    is_realtime: Mapped[bool] = mapped_column(Boolean, default=False)
    degraded_reason: Mapped[str | None] = mapped_column(Text)
    quality_hash: Mapped[str] = mapped_column(String(64), index=True)


class MarketContextRegistry(Base, TimestampMixin):
    """Configuration-backed context item kept independent from ETF instruments."""

    __tablename__ = "market_context_registry"
    __table_args__ = (
        UniqueConstraint("context_id", name="uq_market_context_registry_context_id"),
        UniqueConstraint("display_order", name="uq_market_context_registry_display_order"),
        CheckConstraint(
            "context_kind IN ('sector_breadth', 'index', 'tradable_proxy')",
            name="ck_market_context_registry_context_kind",
        ),
        CheckConstraint(
            "verification_status IN ('verified', 'unverified')",
            name="ck_market_context_registry_verification_status",
        ),
        CheckConstraint(
            "length(trim(context_id)) BETWEEN 1 AND 96 AND length(trim(label)) BETWEEN 1 AND 512 AND "
            "length(trim(region)) BETWEEN 1 AND 512 AND length(trim(freshness_rule)) BETWEEN 1 AND 512",
            name="ck_market_context_registry_text_bounded",
        ),
        CheckConstraint(
            "display_order BETWEEN 1 AND 10000",
            name="ck_market_context_registry_display_order_bounded",
        ),
        CheckConstraint(
            "NOT enabled OR (verification_status = 'verified' AND source_symbol IS NOT NULL)",
            name="ck_market_context_registry_enabled_verified",
        ),
        CheckConstraint(
            "(context_kind = 'tradable_proxy' AND is_tradable_proxy) OR "
            "(context_kind <> 'tradable_proxy' AND NOT is_tradable_proxy)",
            name="ck_market_context_registry_proxy_kind_equivalent",
        ),
        CheckConstraint(
            "is_tradable_proxy OR display_code IS NULL",
            name="ck_market_context_registry_nonproxy_display_code_null",
        ),
        CheckConstraint(
            "NOT is_tradable_proxy OR "
            "(verification_status = 'verified' AND display_code IS NOT NULL) OR "
            "(verification_status = 'unverified' AND source_symbol IS NULL AND display_code IS NULL)",
            name="ck_market_context_registry_proxy_code_coherent",
        ),
        CheckConstraint(
            "source_symbol IS NULL OR length(trim(source_symbol)) BETWEEN 1 AND 128",
            name="ck_market_context_registry_source_symbol_bounded",
        ),
        CheckConstraint(
            "display_code IS NULL OR length(trim(display_code)) BETWEEN 1 AND 128",
            name="ck_market_context_registry_display_code_bounded",
        ),
        Index("ix_market_context_registry_enabled_order", "enabled", "display_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[str] = mapped_column(String(96), nullable=False)
    label: Mapped[str] = mapped_column(String(512), nullable=False)
    region: Mapped[str] = mapped_column(String(512), nullable=False)
    context_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_symbol: Mapped[str | None] = mapped_column(String(128))
    display_code: Mapped[str | None] = mapped_column(String(128))
    is_tradable_proxy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_priority: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    freshness_rule: Mapped[str] = mapped_column(String(512), nullable=False, default="provider_defined")
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unverified")

    snapshots: Mapped[list[MarketContextSnapshot]] = relationship(
        back_populates="registry", cascade="all, delete-orphan"
    )


class MarketContextSnapshot(Base):
    """Immutable-ish observation provenance for one market-context registry item."""

    __tablename__ = "market_context_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "registry_id",
            "source_symbol",
            "source",
            "source_timestamp",
            name="uq_market_context_snapshot_idempotency",
        ),
        Index(
            "ix_market_context_snapshot_registry_symbol_source_time",
            "registry_id",
            "source_symbol",
            "source_timestamp",
        ),
        CheckConstraint(
            "length(trim(source_symbol)) BETWEEN 1 AND 128",
            name="ck_market_context_snapshot_source_symbol_bounded",
        ),
        CheckConstraint(
            "observed_value BETWEEN -1000000000000000 AND 1000000000000000 AND "
            "today_pct_change BETWEEN -100000 AND 100000",
            name="ck_market_context_snapshot_values_finite_bounded",
        ),
        CheckConstraint(
            "price IS NULL OR price BETWEEN 0 AND 1000000000000000",
            name="ck_market_context_snapshot_price_finite_bounded",
        ),
        CheckConstraint(
            "freshness IN ('fresh', 'stale', 'degraded', 'unknown', 'unavailable')",
            name="ck_market_context_snapshot_freshness",
        ),
        CheckConstraint(
            "verification_status IN ('verified', 'unverified')",
            name="ck_market_context_snapshot_verification_status",
        ),
        CheckConstraint(
            "length(trim(source)) BETWEEN 1 AND 512",
            name="ck_market_context_snapshot_source_bounded",
        ),
        CheckConstraint(
            "freshness NOT IN ('degraded', 'unavailable') OR degraded_reason IS NOT NULL",
            name="ck_market_context_snapshot_degraded_reason",
        ),
        CheckConstraint(
            "freshness NOT IN ('fresh', 'stale') OR degraded_reason IS NULL",
            name="ck_market_context_snapshot_fresh_stale_no_degraded_reason",
        ),
        CheckConstraint(
            "degraded_reason IS NULL OR length(trim(degraded_reason)) BETWEEN 1 AND 512",
            name="ck_market_context_snapshot_degraded_reason_bounded",
        ),
        CheckConstraint(
            "source_timestamp <= fetched_at",
            name="ck_market_context_snapshot_source_before_fetch",
        ),
        CheckConstraint(
            "NOT is_mock OR (verification_status = 'unverified' AND freshness = 'degraded' AND degraded_reason IS NOT NULL)",
            name="ck_market_context_snapshot_mock_provenance",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registry_id: Mapped[int] = mapped_column(
        ForeignKey("market_context_registry.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_value: Mapped[float] = mapped_column(Float, nullable=False)
    today_pct_change: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unverified")
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    degraded_reason: Mapped[str | None] = mapped_column(Text)

    registry: Mapped[MarketContextRegistry] = relationship(back_populates="snapshots")


class IndicatorSnapshot(Base):
    __tablename__ = "indicator_snapshots"
    __table_args__ = (
        UniqueConstraint("instrument_id", "as_of_date", "version", name="uq_indicator_instrument_date_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    version: Mapped[str] = mapped_column(String(32))
    values_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    technical_score: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float)
    trend_label: Mapped[str] = mapped_column(String(64))
    data_quality: Mapped[float] = mapped_column(Float)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ForecastSnapshot(Base):
    __tablename__ = "forecast_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "as_of_date", "horizon", "model_version", name="uq_forecast_key"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    horizon: Mapped[int] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(String(64))
    p_up: Mapped[float | None] = mapped_column(Float)
    expected_return: Mapped[float | None] = mapped_column(Float)
    q10: Mapped[float | None] = mapped_column(Float)
    q50: Mapped[float | None] = mapped_column(Float)
    q90: Mapped[float | None] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    calibration_status: Mapped[str] = mapped_column(String(32), default="not_calibrated")
    similarity_distance: Mapped[float | None] = mapped_column(Float)
    diagnostics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SignalSnapshot(Base):
    __tablename__ = "signal_snapshots"
    __table_args__ = (
        UniqueConstraint("instrument_id", "as_of_time", "strategy_version", name="uq_signal_key"),
        Index("ix_signal_instrument_time", "instrument_id", "as_of_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    strategy_version: Mapped[str] = mapped_column(String(32))
    indicator_version: Mapped[str] = mapped_column(String(32))
    forecast_version: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    target_weight: Mapped[float | None] = mapped_column(Float)
    first_step_target_weight: Mapped[float | None] = mapped_column(Float)
    reasons_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    risks_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_actionable: Mapped[bool] = mapped_column(Boolean, default=False)
    data_quality: Mapped[float] = mapped_column(Float)


class Holding(Base, TimestampMixin):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), unique=True)
    shares: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    target_weight: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)

    instrument: Mapped[Instrument] = relationship(back_populates="holding")


class HoldingImportSession(Base, TimestampMixin):
    """Metadata for a short-lived screenshot import; never stores image bytes."""

    __tablename__ = "holding_import_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'editing', 'confirming', 'confirmed', 'cancelled', 'expired', 'failed')",
            name="ck_holding_import_sessions_status",
        ),
        CheckConstraint(_portable_hex_check("image_sha256"), name="ck_holding_import_sessions_image_sha256"),
        CheckConstraint(
            "detected_mime IN ('image/png', 'image/jpeg', 'image/webp')",
            name="ck_holding_import_sessions_detected_mime",
        ),
        CheckConstraint("image_bytes BETWEEN 1 AND 52428800", name="ck_holding_import_sessions_bytes_bounded"),
        CheckConstraint(
            "image_width BETWEEN 1 AND 50000 AND image_height BETWEEN 1 AND 50000",
            name="ck_holding_import_sessions_dimensions_bounded",
        ),
        CheckConstraint(
            "candidate_count BETWEEN 0 AND 10000",
            name="ck_holding_import_sessions_candidate_count_bounded",
        ),
        CheckConstraint(
            _portable_opaque_token_check("session_id", 96) + " AND length(trim(ocr_mode)) BETWEEN 1 AND 32 AND "
            "length(trim(ocr_backend)) BETWEEN 1 AND 128 AND length(trim(ocr_model)) BETWEEN 1 AND 128 AND "
            "length(trim(ocr_version)) BETWEEN 1 AND 128",
            name="ck_holding_import_sessions_text_bounded",
        ),
        CheckConstraint(
            "(cloud_consent IS TRUE AND cloud_consent_at IS NOT NULL) OR "
            "(cloud_consent IS FALSE AND cloud_consent_at IS NULL)",
            name="ck_holding_import_sessions_cloud_consent_coherent",
        ),
        CheckConstraint(
            "status <> 'confirmed' OR (confirmed_at IS NOT NULL AND cancelled_at IS NULL)",
            name="ck_holding_import_sessions_confirmed_timestamp",
        ),
        CheckConstraint(
            "status <> 'cancelled' OR (cancelled_at IS NOT NULL AND confirmed_at IS NULL)",
            name="ck_holding_import_sessions_cancelled_timestamp",
        ),
        CheckConstraint(
            "confirmed_at IS NULL OR status = 'confirmed'",
            name="ck_holding_import_sessions_confirmed_status_bidirectional",
        ),
        CheckConstraint(
            "cancelled_at IS NULL OR status = 'cancelled'",
            name="ck_holding_import_sessions_cancelled_status_bidirectional",
        ),
        CheckConstraint(
            "status NOT IN ('pending', 'processing', 'ready', 'failed', 'expired') OR "
            "(confirmed_at IS NULL AND cancelled_at IS NULL)",
            name="ck_holding_import_sessions_nonterminal_timestamps",
        ),
        CheckConstraint(
            "status NOT IN ('confirmed', 'cancelled', 'expired') OR expires_at IS NOT NULL",
            name="ck_holding_import_sessions_expiry_required",
        ),
        CheckConstraint(
            "storage_key IS NULL OR " + _portable_opaque_token_check("storage_key", 256),
            name="ck_holding_import_sessions_storage_key_bounded",
        ),
        Index("ix_holding_import_sessions_status_expires", "status", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(96), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    image_sha256: Mapped[str] = mapped_column(String(64), index=True)
    detected_mime: Mapped[str] = mapped_column(String(32))
    image_bytes: Mapped[int] = mapped_column(Integer)
    image_width: Mapped[int] = mapped_column(Integer)
    image_height: Mapped[int] = mapped_column(Integer)
    ocr_mode: Mapped[str] = mapped_column(String(32))
    ocr_backend: Mapped[str] = mapped_column(String(128))
    ocr_model: Mapped[str] = mapped_column(String(128))
    ocr_version: Mapped[str] = mapped_column(String(128))
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    cloud_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    cloud_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_key: Mapped[str | None] = mapped_column(String(256))

    candidates: Mapped[list[HoldingImportCandidate]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    @validates("session_id", "storage_key")
    def validate_opaque_token(self, key: str, value: str | None) -> str | None:
        if value is None and key == "storage_key":
            return None
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{16,256}", value):
            raise ValueError("import identifiers must be lowercase opaque hex tokens")
        return value


class HoldingImportCandidate(Base, TimestampMixin):
    """Allowlisted parsed/editable fields for one import row."""

    __tablename__ = "holding_import_candidates"
    __table_args__ = (
        UniqueConstraint("session_id", "row_index", name="uq_holding_import_candidate_session_row"),
        CheckConstraint(
            "row_index BETWEEN 0 AND 10000",
            name="ck_holding_import_candidates_row_index_bounded",
        ),
        CheckConstraint(
            "match_status IN ('matched', 'ambiguous', 'unmatched', 'low_confidence', 'duplicate')",
            name="ck_holding_import_candidates_match_status",
        ),
        CheckConstraint(
            "status IN ('pending', 'reviewed', 'rejected', 'confirmed')",
            name="ck_holding_import_candidates_status",
        ),
        CheckConstraint(
            "action IN ('none', 'confirm', 'reject')",
            name="ck_holding_import_candidates_action",
        ),
        CheckConstraint(
            "(status IN ('pending', 'reviewed') AND action = 'none') OR "
            "(status = 'rejected' AND action = 'reject') OR "
            "(status = 'confirmed' AND action = 'confirm')",
            name="ck_holding_import_candidates_status_action_coherent",
        ),
        CheckConstraint(
            "(selected_code IS NULL AND selected_at IS NULL) OR "
            "(selected_code IS NOT NULL AND selected_at IS NOT NULL)",
            name="ck_holding_import_candidates_selection_bidirectional",
        ),
        CheckConstraint(
            "status <> 'confirmed' OR (selected_code IS NOT NULL AND selected_at IS NOT NULL)",
            name="ck_holding_import_candidates_confirmed_selection",
        ),
        CheckConstraint(
            "status <> 'rejected' OR (selected_code IS NULL AND selected_at IS NULL)",
            name="ck_holding_import_candidates_rejected_selection",
        ),
        CheckConstraint(
            "ts_code IS NULL OR " + _portable_etf_code_check("ts_code"),
            name="ck_holding_import_candidates_code_bounded",
        ),
        CheckConstraint(
            "name IS NULL OR (" + _portable_safe_text_check("name", 128) + ")",
            name="ck_holding_import_candidates_name_bounded",
        ),
        CheckConstraint(
            "selected_code IS NULL OR " + _portable_etf_code_check("selected_code"),
            name="ck_holding_import_candidates_selected_code_bounded",
        ),
        CheckConstraint(
            "user_note IS NULL OR (" + _portable_safe_text_check("user_note", 2000) + " AND lower(user_note) NOT LIKE '%account%' AND lower(user_note) NOT LIKE '%identity%' AND lower(user_note) NOT LIKE '%raw_ocr%')",
            name="ck_holding_import_candidates_user_note_bounded",
        ),
        CheckConstraint(
            "lower(safe_alternatives_json) NOT LIKE '%password%' AND lower(safe_alternatives_json) NOT LIKE '%account%' AND "
            "lower(safe_alternatives_json) NOT LIKE '%identity%' AND lower(safe_alternatives_json) NOT LIKE '%raw_ocr%' AND "
            "lower(safe_alternatives_json) NOT LIKE '%raw_text%' AND lower(safe_alternatives_json) NOT LIKE '%ocr_text%' AND "
            "lower(safe_alternatives_json) NOT LIKE '%pixels%' AND lower(safe_alternatives_json) NOT LIKE '%cookie%' AND "
            "lower(safe_alternatives_json) NOT LIKE '%secret%' AND lower(safe_alternatives_json) NOT LIKE '%token%' AND "
            "lower(field_confidence_json) NOT LIKE '%password%' AND lower(field_confidence_json) NOT LIKE '%account%' AND "
            "lower(field_confidence_json) NOT LIKE '%identity%' AND lower(field_confidence_json) NOT LIKE '%raw_ocr%' AND "
            "lower(field_confidence_json) NOT LIKE '%raw_text%' AND lower(field_confidence_json) NOT LIKE '%ocr_text%' AND "
            "lower(field_confidence_json) NOT LIKE '%pixels%' AND lower(field_confidence_json) NOT LIKE '%cookie%' AND "
            "lower(field_confidence_json) NOT LIKE '%secret%' AND lower(field_confidence_json) NOT LIKE '%token%'",
            name="ck_holding_import_candidates_json_sensitive_keys",
        ),
        CheckConstraint(
            "shares IS NULL OR shares BETWEEN 0 AND 1000000000",
            name="ck_holding_import_candidates_shares_bounded",
        ),
        CheckConstraint(
            "cost_price IS NULL OR cost_price BETWEEN 0 AND 1000000000",
            name="ck_holding_import_candidates_cost_bounded",
        ),
        CheckConstraint(
            "target_weight IS NULL OR target_weight BETWEEN 0 AND 1",
            name="ck_holding_import_candidates_target_weight_bounded",
        ),
        CheckConstraint(_portable_hex_check("normalized_ocr_text_hash"), name="ck_holding_import_candidates_text_hash"),
        Index("ix_holding_import_candidates_session_status", "session_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("holding_import_sessions.id", ondelete="CASCADE"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    ts_code: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(_SafeImportText(128))
    shares: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    target_weight: Mapped[float | None] = mapped_column(Float)
    user_note: Mapped[str | None] = mapped_column(_SafeImportText(OCR_MAX_NOTE_CHARS))
    match_status: Mapped[str] = mapped_column(String(24), default="unmatched", index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    action: Mapped[str] = mapped_column(String(16), default="none")
    safe_alternatives_json: Mapped[tuple[str, ...]] = mapped_column(
        _ValidatedImportJSON("alternatives"), default=tuple
    )
    field_confidence_json: Mapped[tuple[ConfidenceEntry, ...]] = mapped_column(
        _ValidatedImportJSON("confidence"), default=tuple
    )
    normalized_ocr_text_hash: Mapped[str] = mapped_column(String(64), index=True)
    selected_code: Mapped[str | None] = mapped_column(String(32))
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[HoldingImportSession] = relationship(back_populates="candidates")

    @validates("safe_alternatives_json")
    def validate_safe_alternatives(self, key: str, value: Any) -> Any:
        del key
        return _validate_import_json(value, "alternatives")

    @validates("ts_code", "selected_code")
    def validate_etf_code(self, key: str, value: str | None) -> str | None:
        del key
        if value is None:
            return None
        if not re.fullmatch(r"[0-9]{6}\.(SH|SZ|BJ)", value.strip().upper()):
            raise ValueError("holding import code must be a normalized ETF code")
        return value.strip().upper()

    @validates("name")
    def validate_name(self, key: str, value: str | None) -> str | None:
        del key
        if value is None:
            return None
        return _validate_safe_import_text(value, 128)

    @validates("field_confidence_json")
    def validate_field_confidence(self, key: str, value: Any) -> Any:
        del key
        return _validate_import_json(value, "confidence")

    @validates("user_note")
    def validate_user_note(self, key: str, value: str | None) -> str | None:
        del key
        return _validate_safe_import_text(value, OCR_MAX_NOTE_CHARS) if value is not None else None


HoldingImportCandidate.__table__.append_constraint(
    CheckConstraint(_NoBackslash("name"), name="ck_holding_import_candidates_name_no_backslash")
)
HoldingImportCandidate.__table__.append_constraint(
    CheckConstraint(_NoBackslash("user_note"), name="ck_holding_import_candidates_user_note_no_backslash")
)


@event.listens_for(HoldingImportCandidate.__table__, "after_create")
def _create_holding_import_sqlite_nul_triggers(target: Any, connection: Any, **_: Any) -> None:
    if connection.dialect.name != "sqlite":
        return
    connection.exec_driver_sql(
        """CREATE TRIGGER IF NOT EXISTS trg_holding_import_candidates_no_nul_insert
        BEFORE INSERT ON holding_import_candidates
        WHEN instr(COALESCE(NEW.name, ''), char(0)) > 0 OR instr(COALESCE(NEW.user_note, ''), char(0)) > 0
        BEGIN SELECT RAISE(ABORT, 'holding import text contains NUL'); END"""
    )
    connection.exec_driver_sql(
        """CREATE TRIGGER IF NOT EXISTS trg_holding_import_candidates_no_nul_update
        BEFORE UPDATE OF name, user_note ON holding_import_candidates
        WHEN instr(COALESCE(NEW.name, ''), char(0)) > 0 OR instr(COALESCE(NEW.user_note, ''), char(0)) > 0
        BEGIN SELECT RAISE(ABORT, 'holding import text contains NUL'); END"""
    )


@event.listens_for(HoldingImportCandidate.__table__, "before_drop")
def _drop_holding_import_sqlite_nul_triggers(target: Any, connection: Any, **_: Any) -> None:
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS trg_holding_import_candidates_no_nul_update")
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS trg_holding_import_candidates_no_nul_insert")


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    facts_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    inferences_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_flags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    affected_themes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    impact_direction: Mapped[str | None] = mapped_column(String(16))
    impact_horizon: Mapped[str | None] = mapped_column(String(16))
    impact_score: Mapped[float] = mapped_column(Float, default=0)
    llm_model: Mapped[str | None] = mapped_column(String(128))
    schema_version: Mapped[str] = mapped_column(String(32), default="news-v1")
    quality_hash: Mapped[str] = mapped_column(String(64), index=True)
    analysis_run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="RESTRICT"), index=True)
    analysis_source: Mapped[str | None] = mapped_column(String(64), index=True)
    analysis_status: Mapped[str | None] = mapped_column(String(32), index=True)
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_news_source_id"),
        Index("ix_news_published", "published_at"),
        CheckConstraint(
            "(analysis_run_id IS NULL AND analysis_source IS NULL AND analysis_status IS NULL) OR "
            "(analysis_run_id IS NULL AND analysis_source = 'heuristic' AND analysis_status = 'disabled') OR "
            "(analysis_run_id IS NOT NULL AND analysis_source IS NOT NULL AND "
            "analysis_status IN ('completed', 'analysis_unavailable', 'invalid_response', 'failed'))",
            name="ck_news_analysis_provenance_coherent",
        ),
    )


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'analysis_unavailable', 'invalid_response', 'failed')",
            name="ck_analysis_runs_status",
        ),
        CheckConstraint(
            "(status = 'completed' AND output_json IS NOT NULL AND result_hash IS NOT NULL AND failure_class IS NULL) OR "
            "(status IN ('analysis_unavailable', 'invalid_response', 'failed') AND output_json IS NULL AND "
            "result_hash IS NULL AND failure_class IS NOT NULL)",
            name="ck_analysis_runs_status_payload_coherent",
        ),
        CheckConstraint(
            _portable_hex_check("input_hash"),
            name="ck_analysis_runs_input_hash_strict",
        ),
        CheckConstraint(
            "result_hash IS NULL OR (" + _portable_hex_check("result_hash") + ")",
            name="ck_analysis_runs_result_hash_strict",
        ),
        CheckConstraint(
            f"failure_class IS NULL OR ({_portable_failure_class_check('failure_class')})",
            name="ck_analysis_runs_failure_class_strict",
        ),
        Index("ix_analysis_runs_status_created", "status", "created_at"),
        Index("ix_analysis_runs_provider_created", "provider", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), index=True)
    latency_ms: Mapped[float] = mapped_column(Float)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    prompt_version: Mapped[str] = mapped_column(String(512))
    schema_version: Mapped[str] = mapped_column(String(512))
    result_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    output_json: Mapped[str | None] = mapped_column(Text)
    failure_class: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    @validates("input_hash")
    def validate_input_hash(self, key: str, value: str) -> str:
        return _strict_sha256(value, key)

    @validates("result_hash")
    def validate_result_hash(self, key: str, value: str | None) -> str | None:
        return _strict_sha256(value, key) if value is not None else None

    @validates("failure_class")
    def validate_failure_class(self, key: str, value: str | None) -> str | None:
        return _failure_class(value)

    @validates("output_json")
    def validate_output_json(self, key: str, value: str | None) -> str | None:
        _canonical_object(value, key)
        return value

    @property
    def output_payload(self) -> Any | None:
        """Return a newly decoded payload; no mutable object is tied to persistence."""
        return canonical_loads(self.output_json, object_only=True) if self.output_json is not None else None


class AgentReviewCandidate(Base):
    __tablename__ = "agent_review_candidates"
    __table_args__ = (
        CheckConstraint(
            "runner IN ('codex_review_runner', 'claude_code_review_runner')",
            name="ck_review_candidates_runner",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'accepted', 'rejected')",
            name="ck_review_candidates_status",
        ),
        CheckConstraint(
            "(review_status = 'pending' AND accepted_at IS NULL AND rejected_at IS NULL) OR "
            "(review_status = 'accepted' AND accepted_at IS NOT NULL AND rejected_at IS NULL) OR "
            "(review_status = 'rejected' AND accepted_at IS NULL AND rejected_at IS NOT NULL)",
            name="ck_review_candidates_status_timestamps_coherent",
        ),
        CheckConstraint(
            _portable_hex_check("bundle_hash"),
            name="ck_review_candidates_bundle_hash_strict",
        ),
        CheckConstraint(
            _portable_hex_check("memo_hash"),
            name="ck_review_candidates_memo_hash_strict",
        ),
        CheckConstraint(
            f"memo_json IS NOT NULL AND length(memo_json) BETWEEN 1 AND {REVIEW_MEMO_MAX_SERIALIZED_CHARS}",
            name="ck_review_candidates_memo_json_bounded",
        ),
        CheckConstraint(
            f"review_note IS NULL OR length(review_note) <= {REVIEW_NOTE_MAX_CHARS}",
            name="ck_review_candidates_review_note_bounded",
        ),
        Index("ix_review_candidates_status_created", "review_status", "created_at"),
        Index("ix_review_candidates_runner_created", "runner", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    runner: Mapped[str] = mapped_column(String(64), index=True)
    bundle_hash: Mapped[str] = mapped_column(String(64), index=True)
    memo_hash: Mapped[str] = mapped_column(String(64), index=True)
    memo_json: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(String(2000))

    @validates("bundle_hash", "memo_hash")
    def validate_hash(self, key: str, value: str) -> str:
        return _strict_sha256(value, key)

    @validates("review_note")
    def validate_review_note(self, key: str, value: str | None) -> str | None:
        _validate_review_note(value)
        return value

    @validates("memo_json")
    def validate_memo_json(self, key: str, value: Any) -> Any:
        if value is None:
            return None
        _canonical_object(value, key)
        if len(value) > REVIEW_MEMO_MAX_SERIALIZED_CHARS:
            raise ValueError("memo_json exceeds the bounded persistence size")
        return value

    @property
    def memo_payload(self) -> Any | None:
        """Return a newly decoded memo; no mutable object is tied to persistence."""
        return canonical_loads(self.memo_json, object_only=True) if self.memo_json is not None else None


@event.listens_for(AnalysisRun, "before_update")
def _reject_analysis_run_update(mapper: Any, connection: Any, target: AnalysisRun) -> None:
    state = inspect(target)
    fields = (
        "provider",
        "model",
        "status",
        "latency_ms",
        "input_hash",
        "prompt_version",
        "schema_version",
        "result_hash",
        "output_json",
        "failure_class",
        "created_at",
    )
    if any(state.attrs[field].history.has_changes() for field in fields):
        raise ValueError("analysis runs are immutable")
    _validate_analysis_run_payload(target)


@event.listens_for(AgentReviewCandidate, "before_update")
def _reject_review_identity_update(mapper: Any, connection: Any, target: AgentReviewCandidate) -> None:
    state = inspect(target)
    fields = ("candidate_id", "runner", "bundle_hash", "memo_hash", "memo_json", "created_at")
    if any(state.attrs[field].history.has_changes() for field in fields):
        raise ValueError("review candidate identity and evidence are immutable")
    _validate_candidate_payload(target)


def _validate_analysis_run_payload(target: AnalysisRun) -> None:
    parsed = _canonical_object(target.output_json, "output_json")
    _failure_class(target.failure_class)
    if target.status not in {"completed", "analysis_unavailable", "invalid_response", "failed"}:
        raise ValueError("analysis status is invalid")
    if target.status == "completed":
        if parsed is None or target.result_hash is None or target.failure_class is not None:
            raise ValueError("completed analysis requires output/result and no failure")
        if canonical_hash_text(target.output_json) != target.result_hash:
            raise ValueError("result_hash does not match canonical output_json")
    elif parsed is not None or target.result_hash is not None or target.failure_class is None:
        raise ValueError("unavailable analysis requires failure and null output/result")


def _validate_candidate_payload(target: AgentReviewCandidate) -> None:
    parsed = _canonical_object(target.memo_json, "memo_json")
    if parsed is None:
        raise ValueError("memo_json is required")
    if not 1 <= len(target.memo_json) <= REVIEW_MEMO_MAX_SERIALIZED_CHARS:
        raise ValueError("memo_json exceeds the bounded persistence size")
    normalized = validate_review_memo_payload(parsed)
    if normalized != parsed:
        raise ValueError("memo_json must contain sanitized canonical memo text")
    if canonical_hash_text(target.memo_json) != target.memo_hash:
        raise ValueError("memo_hash does not match canonical memo_json")
    _validate_review_note(target.review_note)
    if target.review_status == "pending":
        if target.accepted_at is not None or target.rejected_at is not None:
            raise ValueError("pending review candidate cannot have terminal timestamps")
    elif target.review_status == "accepted":
        if target.accepted_at is None or target.rejected_at is not None:
            raise ValueError("accepted review candidate timestamps are incoherent")
    elif target.review_status == "rejected":
        if target.accepted_at is not None or target.rejected_at is None:
            raise ValueError("rejected review candidate timestamps are incoherent")
    else:
        raise ValueError("review status is invalid")


def _validate_review_note(value: str | None) -> None:
    if value is not None:
        if not isinstance(value, str) or len(value) > REVIEW_NOTE_MAX_CHARS:
            raise ValueError("review_note must be at most 2000 characters")
        from app.utils.canonical_json import validate_safe_text

        validate_safe_text(value)


@event.listens_for(AnalysisRun, "before_insert")
def _validate_analysis_run_insert(mapper: Any, connection: Any, target: AnalysisRun) -> None:
    _validate_analysis_run_payload(target)


@event.listens_for(AgentReviewCandidate, "before_insert")
def _validate_candidate_insert(mapper: Any, connection: Any, target: AgentReviewCandidate) -> None:
    _validate_candidate_payload(target)


@event.listens_for(AnalysisRun, "load")
def _validate_analysis_run_load(target: AnalysisRun, context: Any) -> None:
    _validate_analysis_run_payload(target)


@event.listens_for(AgentReviewCandidate, "load")
def _validate_candidate_load(target: AgentReviewCandidate, context: Any) -> None:
    _validate_candidate_payload(target)


@event.listens_for(AnalysisRun, "refresh")
def _validate_analysis_run_refresh(target: AnalysisRun, context: Any, attrs: Any) -> None:
    _validate_analysis_run_payload(target)


@event.listens_for(AgentReviewCandidate, "refresh")
def _validate_candidate_refresh(target: AgentReviewCandidate, context: Any, attrs: Any) -> None:
    _validate_candidate_payload(target)


class RuntimeSetting(Base, TimestampMixin):
    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(Text)


class TaskRun(Base):
    __tablename__ = "task_runs"
    __table_args__ = (Index("ix_task_run_name_started", "task_name", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    task_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class ProviderAudit(Base):
    __tablename__ = "provider_audits"
    __table_args__ = (Index("ix_provider_audit_time", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    operation: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32))
    latency_ms: Mapped[float | None] = mapped_column(Float)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    source_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventLog(Base):
    __tablename__ = "event_log"
    __table_args__ = (Index("ix_event_log_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_type: Mapped[str] = mapped_column(String(32), index=True)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    file_path: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
