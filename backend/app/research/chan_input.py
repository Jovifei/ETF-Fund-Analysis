"""Freeze persisted daily R4A research bars into the accepted M2 input contract.

This module defines input identity only. It does not call a Provider or the Chan
engine, publish database state, or use the chart read model's content-bound ID.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import DailyBar, Instrument
from app.providers.corporate_action_contract import research_history_rows, research_price_basis
from app.providers.data_contract import DOCUMENTED_UNIT_SOURCES, finite, price_history_issue
from app.research.chan_contract import (
    DIALECT_ID,
    ENGINE_ID,
    ENGINE_UPSTREAM_SHA,
    ENGINE_VERSION,
    ChanContractError,
    PreparedResearchInput,
    prepare_research_input,
)
from app.utils.hashing import stable_hash

SERIES_CONTRACT_VERSION = "r4c-price-series-v1"
SOURCE_BAR_ID_VERSION = "r4c-source-bar-v1"
INPUT_REVISION_ID_VERSION = "r4c-input-revision-v1"
DAILY_SETTLEMENT_TIME = time(15, 15)

_CONFIG_ID = stable_hash(
    {
        "engine_id": ENGINE_ID,
        "engine_version": ENGINE_VERSION,
        "engine_upstream_sha": ENGINE_UPSTREAM_SHA,
        "dialect_id": DIALECT_ID,
        "series_contract_version": SERIES_CONTRACT_VERSION,
        "source_bar_id_version": SOURCE_BAR_ID_VERSION,
        "input_revision_id_version": INPUT_REVISION_ID_VERSION,
    }
)


@dataclass(frozen=True, slots=True)
class FrozenChanInput:
    """A validated M2 input or a fail-closed explanation for its absence.

    ``prepared`` means only that the data contract passed validation. It does
    not enable or execute the selected research engine.
    """

    status: Literal["prepared", "blocked"]
    prepared: PreparedResearchInput | None = None
    logical_series_id: str | None = None
    price_basis_id: str | None = None
    input_revision_id: str | None = None
    source_bar_ids: tuple[str, ...] = ()
    source_as_of: date | None = None
    reason_code: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"prepared", "blocked"}:
            raise ValueError("status must be prepared or blocked")
        if (self.status == "prepared") != (self.prepared is not None):
            raise ValueError("only a prepared result may contain PreparedResearchInput")


def _market_as_of(value: datetime, settings: Settings) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=settings.timezone)
    return value.astimezone(settings.timezone)


def _logical_series_id(
    instrument: str,
    interval: str,
    price_basis_id: str,
    adjustment_version: str,
) -> str:
    """Identity of the causal source series, independent of bars and indicators."""

    return stable_hash(
        {
            "series_contract_version": SERIES_CONTRACT_VERSION,
            "instrument": instrument,
            "interval": interval,
            "research_price_basis_id": price_basis_id,
            "adjustment_version": adjustment_version,
        }
    )


def _source_bar_id(
    instrument: str,
    stored: DailyBar,
    research: object,
    *,
    price_basis_id: str,
    adjustment_version: str,
) -> str:
    quality_hash = str(stored.quality_hash or "").strip()
    return stable_hash(
        {
            "source_bar_id_version": SOURCE_BAR_ID_VERSION,
            "instrument": instrument,
            "interval": "D",
            "trade_date": stored.trade_date.isoformat(),
            "stored_adjustment": stored.adjust,
            "research_price_basis_id": price_basis_id,
            "adjustment_version": adjustment_version,
            "source": stored.source,
            "quality_hash": quality_hash,
            "stored_bar": {
                "open": stored.open,
                "high": stored.high,
                "low": stored.low,
                "close": stored.close,
                "volume": stored.volume,
                "amount": stored.amount,
            },
            "research_bar": {
                "open": research.open,
                "high": research.high,
                "low": research.low,
                "close": research.close,
                "volume": research.volume,
                "amount": research.amount,
            },
        }
    )


def _blocked(
    reason_code: str,
    message: str,
    *,
    logical_series_id: str | None = None,
    price_basis_id: str | None = None,
    input_revision_id: str | None = None,
    source_bar_ids: tuple[str, ...] = (),
    source_as_of: date | None = None,
) -> FrozenChanInput:
    return FrozenChanInput(
        status="blocked",
        logical_series_id=logical_series_id,
        price_basis_id=price_basis_id,
        input_revision_id=input_revision_id,
        source_bar_ids=source_bar_ids,
        source_as_of=source_as_of,
        reason_code=reason_code,
        message=message,
    )


def freeze_chan_input(
    db: Session,
    settings: Settings,
    instrument_code: str,
    *,
    interval: str = "D",
    as_of: datetime,
) -> FrozenChanInput:
    """Build a read-only, settled daily input while keeping explicit identities.

    Price-basis selection, split research transformation and basis identity match
    the accepted R4A chart contract. Only persisted daily bars are considered;
    a same-day row enters after the 15:15 market-time settlement boundary.
    """

    normalized_interval = str(interval or "").strip().upper()
    if normalized_interval != "D":
        return _blocked("unsupported_interval", "M3B-A freezes daily (D) input only")
    if not isinstance(as_of, datetime):
        return _blocked("invalid_as_of", "as_of must be a datetime")

    code = str(instrument_code or "").strip().upper()
    if not code:
        return _blocked("instrument_missing", "instrument_code is required")
    if settings.market_provider == "mock":
        return _blocked("mock_history", "Mock history cannot enter a Chan research input")

    market_as_of = _market_as_of(as_of, settings)
    instrument = db.scalar(select(Instrument).where(Instrument.ts_code == code))
    if instrument is None:
        return _blocked("instrument_not_found", "instrument_code is not present in persisted history")

    # Match R4A's adjustment selection. Its basis descriptor uses the read date,
    # while the actual D rows are limited by the 15:15 settlement cutoff below.
    adjustments = list(
        db.scalars(
            select(DailyBar.adjust)
            .where(
                DailyBar.instrument_id == instrument.id,
                DailyBar.trade_date <= market_as_of.date(),
            )
            .distinct()
        ).all()
    )
    if not adjustments:
        return _blocked("history_missing", "no persisted daily price basis is available as of this read")
    adjustment = "none" if "none" in adjustments else adjustments[0] if len(adjustments) == 1 else None
    if adjustment is None:
        return _blocked(
            "missing_or_ambiguous_price_basis",
            "persisted daily bars contain multiple adjustment bases",
        )

    settled_through = market_as_of.date()
    if market_as_of.timetz().replace(tzinfo=None) < DAILY_SETTLEMENT_TIME:
        settled_through -= timedelta(days=1)
    stored_rows = list(
        db.scalars(
            select(DailyBar)
            .where(
                DailyBar.instrument_id == instrument.id,
                DailyBar.adjust == adjustment,
                DailyBar.trade_date <= settled_through,
            )
            .order_by(DailyBar.trade_date.asc())
        ).all()
    )
    if not stored_rows:
        return _blocked("history_missing", "no settled persisted daily bars are available as of this read")

    research_rows = (
        stored_rows
        if adjustment != "none"
        else research_history_rows(stored_rows, code)
    )
    basis = research_price_basis(
        code,
        adjustment,
        effective_through=market_as_of.date(),
        consider_corporate_actions=True,
    )
    price_basis_id = str(basis["price_basis_id"])
    adjustment_version = str(basis["adjustment_contract_version"])
    logical_series_id = _logical_series_id(code, "D", price_basis_id, adjustment_version)

    history_issue = price_history_issue(research_rows)
    if history_issue:
        return _blocked(
            history_issue,
            "R4A research history is not valid for a Chan input",
            logical_series_id=logical_series_id,
            price_basis_id=price_basis_id,
        )

    source_bar_ids: list[str] = []
    bars: list[dict[str, object]] = []
    for stored, research in zip(stored_rows, research_rows, strict=True):
        source = str(stored.source or "").strip()
        if "mock" in source.lower():
            return _blocked(
                "mock_history",
                "Mock history cannot enter a Chan research input",
                logical_series_id=logical_series_id,
                price_basis_id=price_basis_id,
            )
        if source not in DOCUMENTED_UNIT_SOURCES:
            return _blocked(
                "volume_units_unverified",
                "volume and amount units are not documented for this daily-bar source",
                logical_series_id=logical_series_id,
                price_basis_id=price_basis_id,
            )
        if not str(stored.quality_hash or "").strip():
            return _blocked(
                "source_revision_missing",
                "daily bar is missing its source quality revision hash",
                logical_series_id=logical_series_id,
                price_basis_id=price_basis_id,
            )
        if research.volume is None:
            return _blocked(
                "unknown_volume",
                "unknown volume cannot be represented by the selected M2 contract",
                logical_series_id=logical_series_id,
                price_basis_id=price_basis_id,
            )
        if research.amount is None:
            return _blocked(
                "unknown_amount",
                "unknown amount cannot be represented by the selected M2 contract",
                logical_series_id=logical_series_id,
                price_basis_id=price_basis_id,
            )
        if not finite(research.volume) or float(research.volume) < 0:
            return _blocked(
                "invalid_volume",
                "volume must be finite and non-negative",
                logical_series_id=logical_series_id,
                price_basis_id=price_basis_id,
            )
        if not finite(research.amount) or float(research.amount) < 0:
            return _blocked(
                "invalid_amount",
                "amount must be finite and non-negative",
                logical_series_id=logical_series_id,
                price_basis_id=price_basis_id,
            )

        source_bar_id = _source_bar_id(
            code,
            stored,
            research,
            price_basis_id=price_basis_id,
            adjustment_version=adjustment_version,
        )
        source_bar_ids.append(source_bar_id)
        bars.append(
            {
                "source_bar_id": source_bar_id,
                "timestamp": datetime.combine(
                    research.trade_date,
                    DAILY_SETTLEMENT_TIME,
                    tzinfo=settings.timezone,
                ),
                "open": research.open,
                "high": research.high,
                "low": research.low,
                "close": research.close,
                "volume": research.volume,
                "amount": research.amount,
            }
        )

    frozen_ids = tuple(source_bar_ids)
    input_revision_id = stable_hash(
        {
            "input_revision_id_version": INPUT_REVISION_ID_VERSION,
            "logical_series_id": logical_series_id,
            "ordered_source_bar_ids": list(frozen_ids),
        }
    )
    try:
        prepared = prepare_research_input(
            instrument=code,
            interval="D",
            series_id=logical_series_id,
            price_basis_id=price_basis_id,
            adjustment_version=adjustment_version,
            input_revision_id=input_revision_id,
            settlement_status="settled",
            config_id=_CONFIG_ID,
            bars=bars,
        )
    except ChanContractError as exc:
        return _blocked(
            exc.code,
            str(exc),
            logical_series_id=logical_series_id,
            price_basis_id=price_basis_id,
            input_revision_id=input_revision_id,
            source_bar_ids=frozen_ids,
            source_as_of=research_rows[-1].trade_date,
        )

    return FrozenChanInput(
        status="prepared",
        prepared=prepared,
        logical_series_id=logical_series_id,
        price_basis_id=price_basis_id,
        input_revision_id=input_revision_id,
        source_bar_ids=frozen_ids,
        source_as_of=research_rows[-1].trade_date,
    )
