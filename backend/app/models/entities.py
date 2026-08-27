from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


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

    holding: Mapped["Holding | None"] = relationship(back_populates="instrument", uselist=False)


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


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_news_source_id"),
        Index("ix_news_published", "published_at"),
    )

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
