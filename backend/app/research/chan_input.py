"""Freeze persisted daily R4A research bars into the accepted M2 input contract.

This module defines input identity only. It does not call a Provider or the Chan
engine, publish database state, or use the chart read model's content-bound ID.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
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
PERIOD_INPUT_CONTRACT_VERSION = "r4c-calendar-period-v1"
PERIOD_SOURCE_BAR_ID_VERSION = "r4c-period-source-bar-v1"
BLOCKED_REASON_CODES = frozenset(
    {
        "instrument_missing",
        "unsupported_interval",
        "history_missing",
        "ambiguous_price_basis",
        "history_qualification_blocked",
        "source_identity_missing",
        "unknown_volume",
        "unknown_amount",
        "invalid_ohlc",
        "mock_history",
        "volume_units_unverified",
        "invalid_volume",
        "invalid_amount",
        "invalid_as_of",
    }
)
PRICE_HISTORY_DETAIL_CODES = frozenset(
    {
        "history_missing",
        "unknown_price_basis",
        "ambiguous_price_basis",
        "invalid_ohlc",
        "invalid_history_date",
        "duplicate_or_unordered_history",
        "unexplained_price_discontinuity",
    }
)

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
    constituent_source_bar_ids: tuple[tuple[str, ...], ...] = ()
    source_as_of: date | None = None
    reason_code: str | None = None
    detail_code: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"prepared", "blocked"}:
            raise ValueError("status must be prepared or blocked")
        if (self.status == "prepared") != (self.prepared is not None):
            raise ValueError("only a prepared result may contain PreparedResearchInput")
        if self.prepared is not None:
            if self.prepared.interval == "D" and self.constituent_source_bar_ids:
                raise ValueError("daily inputs use period-only lineage")
            if self.prepared.interval in {"W", "M"} and (
                len(self.constituent_source_bar_ids) != len(self.prepared.bars)
                or any(not source_ids for source_ids in self.constituent_source_bar_ids)
            ):
                raise ValueError("period inputs require ordered daily constituent lineage")


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


def _period_source_bar_id(
    instrument: str,
    interval: str,
    price_basis_id: str,
    adjustment_version: str,
    period_config_id: str,
    aggregate: dict[str, object],
    constituent_source_bar_ids: tuple[str, ...],
) -> str:
    return stable_hash(
        {
            "period_source_bar_id_version": PERIOD_SOURCE_BAR_ID_VERSION,
            "period_input_contract_version": PERIOD_INPUT_CONTRACT_VERSION,
            "instrument": instrument,
            "interval": interval,
            "price_basis_id": price_basis_id,
            "adjustment_version": adjustment_version,
            "period_config_id": period_config_id,
            "period_start": aggregate["period_start"],
            "period_end": aggregate["period_end"],
            "last_observed_constituent_timestamp": aggregate["date"],
            "ordered_constituent_source_bar_ids": list(constituent_source_bar_ids),
            "aggregate_ohlcva": {
                field: aggregate[field]
                for field in ("open", "high", "low", "close", "volume", "amount")
            },
        }
    )


def _blocked(
    reason_code: str,
    message: str,
    *,
    detail_code: str | None = None,
    logical_series_id: str | None = None,
    price_basis_id: str | None = None,
    input_revision_id: str | None = None,
    source_bar_ids: tuple[str, ...] = (),
    source_as_of: date | None = None,
) -> FrozenChanInput:
    return FrozenChanInput(
        status="blocked",
        reason_code=reason_code if reason_code in BLOCKED_REASON_CODES else "history_qualification_blocked",
        detail_code=detail_code if detail_code in PRICE_HISTORY_DETAIL_CODES else None,
        logical_series_id=logical_series_id,
        price_basis_id=price_basis_id,
        input_revision_id=input_revision_id,
        source_bar_ids=source_bar_ids,
        source_as_of=source_as_of,
        message=message,
    )


def _freeze_period_chan_input(
    db: Session,
    settings: Settings,
    instrument_code: str,
    *,
    interval: str,
    as_of: datetime,
) -> FrozenChanInput:
    daily = freeze_chan_input(db, settings, instrument_code, interval="D", as_of=as_of)
    if daily.status != "prepared" or daily.prepared is None:
        return _blocked(
            daily.reason_code or "history_qualification_blocked",
            "accepted daily Chan research input is unavailable for period aggregation",
            detail_code=daily.detail_code,
            price_basis_id=daily.price_basis_id,
            source_as_of=daily.source_as_of,
        )

    from app.workspace.candle_periods import aggregate_bars

    market_as_of = _market_as_of(as_of, settings)
    daily_rows = []
    for bar in daily.prepared.bars:
        market_timestamp = bar.timestamp.replace(tzinfo=UTC).astimezone(settings.timezone)
        daily_rows.append(
            {
                "date": market_timestamp.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "amount": bar.amount,
                "source": "accepted_m3b_a_daily_research",
            }
        )

    calendar_period = "1w" if interval == "W" else "1mo"
    aggregates = aggregate_bars(daily_rows, calendar_period, now=market_as_of)
    if not aggregates:
        return _blocked(
            "history_missing",
            "no calendar-period aggregate is available from the accepted daily input",
            logical_series_id=daily.logical_series_id,
            price_basis_id=daily.price_basis_id,
            source_bar_ids=daily.source_bar_ids,
            source_as_of=daily.source_as_of,
        )

    period_config_id = stable_hash(
        {
            "base_config_id": daily.prepared.config_id,
            "period_input_contract_version": PERIOD_INPUT_CONTRACT_VERSION,
        }
    )
    logical_series_id = _logical_series_id(
        daily.prepared.instrument,
        interval,
        daily.prepared.price_basis_id,
        daily.prepared.adjustment_version,
    )

    prepared_bars: list[dict[str, object]] = []
    period_source_bar_ids: list[str] = []
    constituent_source_bar_ids: list[tuple[str, ...]] = []
    cursor = 0
    for aggregate in aggregates:
        count = aggregate.get("source_bar_count")
        if not isinstance(count, int) or count <= 0 or cursor + count > daily.prepared.cutoff:
            return _blocked(
                "history_qualification_blocked",
                "calendar aggregate does not map to the accepted daily source bars",
                logical_series_id=logical_series_id,
                price_basis_id=daily.prepared.price_basis_id,
            )
        constituents = tuple(
            daily.prepared.bars[index].source_bar_id
            for index in range(cursor, cursor + count)
        )
        cursor += count
        source_bar_id = _period_source_bar_id(
            daily.prepared.instrument,
            interval,
            daily.prepared.price_basis_id,
            daily.prepared.adjustment_version,
            period_config_id,
            aggregate,
            constituents,
        )
        period_source_bar_ids.append(source_bar_id)
        constituent_source_bar_ids.append(constituents)
        prepared_bars.append(
            {
                "source_bar_id": source_bar_id,
                "timestamp": aggregate["date"],
                "open": aggregate["open"],
                "high": aggregate["high"],
                "low": aggregate["low"],
                "close": aggregate["close"],
                "volume": aggregate["volume"],
                "amount": aggregate["amount"],
            }
        )
    if cursor != daily.prepared.cutoff:
        return _blocked(
            "history_qualification_blocked",
            "calendar aggregation omitted accepted daily source bars",
            logical_series_id=logical_series_id,
            price_basis_id=daily.prepared.price_basis_id,
        )

    frozen_ids = tuple(period_source_bar_ids)
    input_revision_id = stable_hash(
        {
            "input_revision_id_version": INPUT_REVISION_ID_VERSION,
            "logical_series_id": logical_series_id,
            "ordered_source_bar_ids": list(frozen_ids),
        }
    )
    settlement_status = "temporary" if bool(aggregates[-1].get("is_partial")) else "settled"
    try:
        prepared = prepare_research_input(
            instrument=daily.prepared.instrument,
            interval=interval,
            series_id=logical_series_id,
            price_basis_id=daily.prepared.price_basis_id,
            adjustment_version=daily.prepared.adjustment_version,
            input_revision_id=input_revision_id,
            settlement_status=settlement_status,
            config_id=period_config_id,
            bars=prepared_bars,
        )
    except ChanContractError as exc:
        return _blocked(
            "history_qualification_blocked",
            "M2 input validation rejected the frozen calendar-period research history",
            detail_code=exc.code if exc.code in PRICE_HISTORY_DETAIL_CODES else None,
            logical_series_id=logical_series_id,
            price_basis_id=daily.prepared.price_basis_id,
            input_revision_id=input_revision_id,
            source_bar_ids=frozen_ids,
            source_as_of=date.fromisoformat(str(aggregates[-1]["date"])[:10]),
        )

    return FrozenChanInput(
        status="prepared",
        prepared=prepared,
        logical_series_id=logical_series_id,
        price_basis_id=daily.prepared.price_basis_id,
        input_revision_id=input_revision_id,
        source_bar_ids=frozen_ids,
        constituent_source_bar_ids=tuple(constituent_source_bar_ids),
        source_as_of=date.fromisoformat(str(aggregates[-1]["date"])[:10]),
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
    if normalized_interval not in {"D", "W", "M"}:
        return _blocked("unsupported_interval", "Chan inputs support daily (D), weekly (W), and monthly (M) periods")
    if not isinstance(as_of, datetime):
        return _blocked("invalid_as_of", "as_of must be a datetime")
    if normalized_interval in {"W", "M"}:
        return _freeze_period_chan_input(
            db,
            settings,
            instrument_code,
            interval=normalized_interval,
            as_of=as_of,
        )

    code = str(instrument_code or "").strip().upper()
    if not code:
        return _blocked("instrument_missing", "instrument_code is required")
    if settings.market_provider == "mock":
        return _blocked("mock_history", "Mock history cannot enter a Chan research input")

    market_as_of = _market_as_of(as_of, settings)
    instrument = db.scalar(select(Instrument).where(Instrument.ts_code == code))
    if instrument is None:
        return _blocked("instrument_missing", "instrument_code is not present in persisted history")

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
            "ambiguous_price_basis",
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
        else research_history_rows(
            stored_rows,
            code,
            effective_through=market_as_of.date(),
        )
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
        reason_code = "history_qualification_blocked"
        detail_code = history_issue
        if history_issue == "history_missing":
            reason_code = "history_missing"
        elif history_issue in {"unknown_price_basis", "ambiguous_price_basis"}:
            reason_code = "ambiguous_price_basis"
        elif history_issue == "invalid_ohlc":
            reason_code = "invalid_ohlc"
        return _blocked(
            reason_code,
            "R4A research history is not valid for a Chan input",
            detail_code=detail_code,
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
                "source_identity_missing",
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
        if exc.code in {"unknown_volume", "unknown_amount", "invalid_ohlc"}:
            reason_code = exc.code
        elif exc.code in {"identity_missing", "duplicate_source_bar_id"}:
            reason_code = "source_identity_missing"
        else:
            reason_code = "history_qualification_blocked"
        return _blocked(
            reason_code,
            "M2 input validation rejected the frozen daily research history",
            detail_code=exc.code if exc.code in PRICE_HISTORY_DETAIL_CODES else None,
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
