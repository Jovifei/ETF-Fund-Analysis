"""Pure contracts and reviewed identities for the disabled R4C research dialect.

This module intentionally has no Provider, database, HTTP, or CZSC imports. It
validates already-prepared causal bars and names the evidence an adapter may
emit; it does not claim that a first observation is engine confirmation.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Any

from app.utils.hashing import stable_hash

ENGINE_ID = "czsc"
ENGINE_VERSION = "1.0.1"
ENGINE_UPSTREAM_SHA = "90372af035f01ed9f05070eadddd265b91c84d24"
DIALECT_ID = "r4c-observed-revision-v1"
SUPPORTED_INTERVALS = frozenset({"D", "W", "M"})
SUPPORTED_STRUCTURES = frozenset({"fx", "bi", "zs"})


class ChanContractError(ValueError):
    """Input or output violates the fail-closed selected dialect contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChanContractError("identity_missing", f"{field} must be a non-empty string")
    return value.strip()


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ChanContractError("invalid_bar_timestamp", "timestamp must be ISO date/time") from exc
    else:
        raise ChanContractError("invalid_bar_timestamp", "timestamp must be date, datetime, or ISO text")

    if result.tzinfo is not None:
        offset = result.utcoffset()
        if offset is None:
            raise ChanContractError("invalid_bar_timestamp", "timestamp timezone offset is unavailable")
        result = result.astimezone(UTC).replace(tzinfo=None)
    return result


def _finite_number(value: Any, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or value is None:
        raise ChanContractError(f"{field}_missing", f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ChanContractError(f"{field}_invalid", f"{field} must be a finite number") from exc
    if not math.isfinite(number) or (positive and number <= 0) or (not positive and number < 0):
        raise ChanContractError(f"{field}_invalid", f"{field} is outside the accepted range")
    return number


@dataclass(frozen=True, slots=True)
class ResearchBar:
    source_bar_id: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float

    def input_payload(self) -> dict[str, Any]:
        return {
            "source_bar_id": self.source_bar_id,
            "timestamp": self.timestamp.isoformat(sep=" "),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
        }


@dataclass(frozen=True, slots=True, init=False)
class PreparedResearchInput:
    instrument: str
    interval: str
    series_id: str
    price_basis_id: str
    adjustment_version: str
    input_revision_id: str
    settlement_status: str
    config_id: str
    bars: tuple[ResearchBar, ...]
    input_hash: str
    _endpoint_index: Mapping[str, tuple[str, int]] = field(repr=False, compare=False, hash=False)

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("use prepare_research_input to create a validated input")

    @property
    def cutoff(self) -> int:
        return len(self.bars)

    @property
    def cutoff_bar_id(self) -> str:
        return self.bars[-1].source_bar_id

    @property
    def cutoff_at(self) -> datetime:
        return self.bars[-1].timestamp


@dataclass(frozen=True, slots=True, init=False)
class StructureEvidence:
    kind: str
    direction: str | None
    mark: str | None
    source_start: str
    source_end: str
    source_start_bar_id: str
    source_end_bar_id: str
    geometry: tuple[tuple[str, float], ...]
    engine_state: str | None
    structure_key: str
    revision_id: str

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("use build_structure_evidence to create validated structure evidence")

    def geometry_payload(self) -> dict[str, float]:
        return dict(self.geometry)


@dataclass(frozen=True, slots=True, init=False)
class ResearchObservation:
    observation_id: str
    instrument: str
    interval: str
    series_id: str
    price_basis_id: str
    adjustment_version: str
    input_revision_id: str
    settlement_status: str
    config_id: str
    input_hash: str
    cutoff: int
    cutoff_bar_id: str
    cutoff_at: datetime
    engine_id: str
    engine_version: str
    dialect_id: str
    engine_confirmation: str
    application_observation_status: str
    structures: tuple[StructureEvidence, ...]

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("use make_observation to create a validated research observation")


def _create_validated_record(record_type: type[Any], values: Mapping[str, Any]) -> Any:
    record = object.__new__(record_type)
    for name, value in values.items():
        object.__setattr__(record, name, value)
    return record

def prepare_research_input(
    *,
    instrument: str,
    interval: str,
    series_id: str,
    price_basis_id: str,
    adjustment_version: str,
    input_revision_id: str,
    settlement_status: str,
    config_id: str,
    bars: Sequence[Mapping[str, Any]],
) -> PreparedResearchInput:
    instrument = _required_text(instrument, "instrument")
    interval = _required_text(interval, "interval").upper()
    if interval not in SUPPORTED_INTERVALS:
        raise ChanContractError("unsupported_interval", f"unsupported interval: {interval}")
    series_id = _required_text(series_id, "series_id")
    price_basis_id = _required_text(price_basis_id, "price_basis_id")
    adjustment_version = _required_text(adjustment_version, "adjustment_version")
    input_revision_id = _required_text(input_revision_id, "input_revision_id")
    config_id = _required_text(config_id, "config_id")
    settlement_status = _required_text(settlement_status, "settlement_status")
    if settlement_status not in {"settled", "temporary"}:
        raise ChanContractError("invalid_settlement_status", "settlement_status must be settled or temporary")
    if not bars:
        raise ChanContractError("history_missing", "at least one prepared research bar is required")

    normalized: list[ResearchBar] = []
    ids: set[str] = set()
    endpoint_index: dict[str, tuple[str, int]] = {}
    prior_timestamp: datetime | None = None
    for index, row in enumerate(bars):
        if not isinstance(row, Mapping):
            raise ChanContractError("invalid_bar", f"bar at index {index} must be a mapping")
        source_bar_id = _required_text(row.get("source_bar_id"), "source_bar_id")
        if source_bar_id in ids:
            raise ChanContractError("duplicate_source_bar_id", f"duplicate source_bar_id: {source_bar_id}")
        ids.add(source_bar_id)

        timestamp = _timestamp(row.get("timestamp"))
        if prior_timestamp is not None and timestamp <= prior_timestamp:
            raise ChanContractError("unordered_source_bars", "source bars must be strictly increasing by timestamp")
        prior_timestamp = timestamp
        endpoint_index[timestamp.isoformat(sep=" ")] = (source_bar_id, index)

        # CZSC RawBar requires numeric quantities. Unknown values are never coerced to zero.
        if row.get("volume") is None:
            raise ChanContractError("unknown_volume", "unknown volume cannot be represented by CZSC")
        if row.get("amount") is None:
            raise ChanContractError("unknown_amount", "unknown amount cannot be represented by CZSC")
        open_price = _finite_number(row.get("open"), "open", positive=True)
        high = _finite_number(row.get("high"), "high", positive=True)
        low = _finite_number(row.get("low"), "low", positive=True)
        close = _finite_number(row.get("close"), "close", positive=True)
        if not low <= min(open_price, close) <= max(open_price, close) <= high:
            raise ChanContractError("invalid_ohlc", "bar OHLC values are inconsistent")
        volume = _finite_number(row.get("volume"), "volume")
        amount = _finite_number(row.get("amount"), "amount")
        normalized.append(
            ResearchBar(
                source_bar_id=source_bar_id,
                timestamp=timestamp,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                amount=amount,
            )
        )

    input_hash = stable_hash(
        {
            "instrument": instrument,
            "interval": interval,
            "series_id": series_id,
            "price_basis_id": price_basis_id,
            "adjustment_version": adjustment_version,
            "input_revision_id": input_revision_id,
            "settlement_status": settlement_status,
            "bars": [bar.input_payload() for bar in normalized],
        }
    )
    return _create_validated_record(
        PreparedResearchInput,
        {
            "instrument": instrument,
            "interval": interval,
            "series_id": series_id,
            "price_basis_id": price_basis_id,
            "adjustment_version": adjustment_version,
            "input_revision_id": input_revision_id,
            "settlement_status": settlement_status,
            "config_id": config_id,
            "bars": tuple(normalized),
            "input_hash": input_hash,
            "_endpoint_index": MappingProxyType(endpoint_index),
        },
    )


def build_observation_id(prepared: PreparedResearchInput) -> str:
    return stable_hash(
        {
            "instrument": prepared.instrument,
            "interval": prepared.interval,
            "cutoff": prepared.cutoff,
            "input_hash": prepared.input_hash,
            "price_basis_id": prepared.price_basis_id,
            "engine_id": ENGINE_ID,
            "engine_version": ENGINE_VERSION,
            "dialect_id": DIALECT_ID,
            "config_id": prepared.config_id,
        }
    )


def build_structure_key(
    prepared: PreparedResearchInput,
    *,
    kind: str,
    direction: str | None,
    mark: str | None,
    source_start: str,
    source_end: str,
    source_start_bar_id: str,
    source_end_bar_id: str,
) -> str:
    if kind not in SUPPORTED_STRUCTURES:
        raise ChanContractError("unsupported_structure", f"unsupported structure kind: {kind}")
    return stable_hash(
        {
            "instrument": prepared.instrument,
            "interval": prepared.interval,
            "engine_id": ENGINE_ID,
            "engine_version": ENGINE_VERSION,
            "dialect_id": DIALECT_ID,
            "config_id": prepared.config_id,
            "price_basis_id": prepared.price_basis_id,
            "kind": kind,
            "direction": direction,
            "mark": mark,
            "source_start": source_start,
            "source_end": source_end,
            "source_start_bar_id": source_start_bar_id,
            "source_end_bar_id": source_end_bar_id,
        }
    )


def build_revision_id(
    observation_id: str,
    structure_key: str,
    geometry: Mapping[str, float],
    engine_state: str | None,
) -> str:
    return stable_hash(
        {
            "observation_id": observation_id,
            "structure_key": structure_key,
            "payload": {
                "geometry": dict(geometry),
                "engine_state": engine_state,
            },
        }
    )


def build_structure_evidence(
    prepared: PreparedResearchInput,
    *,
    observation_id: str,
    kind: str,
    direction: str | None,
    mark: str | None,
    source_start: str,
    source_end: str,
    source_start_bar_id: str,
    source_end_bar_id: str,
    geometry: Mapping[str, Any],
    engine_state: str | None,
) -> StructureEvidence:
    source_start = _timestamp(_required_text(source_start, "source_start")).isoformat(sep=" ")
    source_end = _timestamp(_required_text(source_end, "source_end")).isoformat(sep=" ")
    source_start_bar_id = _required_text(source_start_bar_id, "source_start_bar_id")
    source_end_bar_id = _required_text(source_end_bar_id, "source_end_bar_id")
    start_identity = prepared._endpoint_index.get(source_start)
    end_identity = prepared._endpoint_index.get(source_end)
    if start_identity is None or end_identity is None:
        raise ChanContractError("source_endpoint_missing", "structure endpoint is outside the prepared input")
    if start_identity[0] != source_start_bar_id or end_identity[0] != source_end_bar_id:
        raise ChanContractError("source_endpoint_mismatch", "source bar IDs must match the structure endpoint timestamps")
    if start_identity[1] > end_identity[1]:
        raise ChanContractError("source_endpoint_order_invalid", "structure source endpoints must be chronological")
    if kind not in SUPPORTED_STRUCTURES:
        raise ChanContractError("unsupported_structure", f"unsupported structure kind: {kind}")
    if not geometry:
        raise ChanContractError("geometry_missing", "normalized structure geometry is required")
    required_geometry = {"fx": {"high", "low"}, "bi": {"high", "low"}, "zs": {"zg", "zd"}}[kind]
    if not required_geometry.issubset(geometry):
        raise ChanContractError("geometry_incomplete", f"{kind} requires geometry fields {sorted(required_geometry)}")
    normalized_geometry = tuple(
        sorted((str(key), _finite_number(value, "geometry", positive=False)) for key, value in geometry.items())
    )
    geometry_payload = dict(normalized_geometry)
    key = build_structure_key(
        prepared,
        kind=kind,
        direction=direction,
        mark=mark,
        source_start=source_start,
        source_end=source_end,
        source_start_bar_id=source_start_bar_id,
        source_end_bar_id=source_end_bar_id,
    )
    revision = build_revision_id(observation_id, key, geometry_payload, engine_state)
    return _create_validated_record(
        StructureEvidence,
        {
            "kind": kind,
            "direction": direction,
            "mark": mark,
            "source_start": source_start,
            "source_end": source_end,
            "source_start_bar_id": source_start_bar_id,
            "source_end_bar_id": source_end_bar_id,
            "geometry": normalized_geometry,
            "engine_state": engine_state,
            "structure_key": key,
            "revision_id": revision,
        },
    )


def make_observation(
    prepared: PreparedResearchInput,
    structures: Sequence[StructureEvidence],
) -> ResearchObservation:
    observation = build_observation_id(prepared)
    if any(not isinstance(structure, StructureEvidence) for structure in structures):
        raise ChanContractError("invalid_structure_evidence", "observations require validated structure evidence records")
    if any(structure.revision_id != build_revision_id(
        observation,
        structure.structure_key,
        structure.geometry_payload(),
        structure.engine_state,
    ) for structure in structures):
        raise ChanContractError("observation_revision_mismatch", "structure revisions must bind this observation")
    return _create_validated_record(
        ResearchObservation,
        {
            "observation_id": observation,
            "instrument": prepared.instrument,
            "interval": prepared.interval,
            "series_id": prepared.series_id,
            "price_basis_id": prepared.price_basis_id,
            "adjustment_version": prepared.adjustment_version,
            "input_revision_id": prepared.input_revision_id,
            "settlement_status": prepared.settlement_status,
            "config_id": prepared.config_id,
            "input_hash": prepared.input_hash,
            "cutoff": prepared.cutoff,
            "cutoff_bar_id": prepared.cutoff_bar_id,
            "cutoff_at": prepared.cutoff_at,
            "engine_id": ENGINE_ID,
            "engine_version": ENGINE_VERSION,
            "dialect_id": DIALECT_ID,
            "engine_confirmation": "unknown",
            "application_observation_status": "observed",
            "structures": tuple(structures),
        },
    )
