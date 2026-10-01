"""Transactional persistence for disabled R4C observed-revision research."""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import (
    ChanObservedTransition,
    ChanResearchObservation,
    ChanResearchStreamHead,
    ChanStructureRevision,
)
from app.research.chan_contract import (
    DIALECT_ID,
    ENGINE_ID,
    ENGINE_VERSION,
    ChanContractError,
    ResearchObservation,
    StructureEvidence,
)
from app.research.chan_replay import (
    ObservedStructureState,
    ObservedTransition,
    derive_observed_transitions,
)
from app.utils.hashing import stable_hash

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT_LENGTHS = {
    "instrument": 64,
    "interval": 16,
    "series_id": 256,
    "price_basis_id": 256,
    "adjustment_version": 256,
    "input_revision_id": 256,
    "settlement_status": 16,
    "config_id": 256,
    "cutoff_bar_id": 256,
    "engine_id": 64,
    "engine_version": 64,
    "dialect_id": 128,
}


@dataclass(frozen=True, slots=True)
class ObservationPublication:
    stream_id: str
    observation_id: str
    transitions: tuple[ObservedTransition, ...]
    already_published: bool = False


def _text_value(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or value.strip() != value or len(value) > maximum:
        raise ChanContractError("invalid_observation_text", f"{field} is empty or outside its stored bound")
    return value


def _datetime_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is not None:
        raise ChanContractError("invalid_observation_cutoff_time", "cutoff_at must be a normalized UTC-naive datetime")
    return value.isoformat(sep=" ", timespec="microseconds")


def _namespace(observation: ResearchObservation) -> dict[str, str]:
    return {
        "instrument": observation.instrument,
        "interval": observation.interval,
        "series_id": observation.series_id,
        "price_basis_id": observation.price_basis_id,
        "adjustment_version": observation.adjustment_version,
        "config_id": observation.config_id,
        "engine_id": observation.engine_id,
        "engine_version": observation.engine_version,
        "dialect_id": observation.dialect_id,
    }


def _stream_id(namespace: dict[str, str]) -> str:
    return stable_hash(namespace)


def _structure_payload(structure: StructureEvidence) -> dict[str, Any]:
    return {
        "kind": structure.kind,
        "direction": structure.direction,
        "mark": structure.mark,
        "source_start": structure.source_start,
        "source_end": structure.source_end,
        "source_start_bar_id": structure.source_start_bar_id,
        "source_end_bar_id": structure.source_end_bar_id,
        "geometry": structure.geometry_payload(),
        "engine_state": structure.engine_state,
        "structure_key": structure.structure_key,
        "revision_id": structure.revision_id,
    }


def _observation_payload(
    observation: ResearchObservation,
    stream_id: str,
) -> dict[str, Any]:
    return {
        "stream_id": stream_id,
        "observation_id": observation.observation_id,
        **_namespace(observation),
        "input_revision_id": observation.input_revision_id,
        "settlement_status": observation.settlement_status,
        "input_hash": observation.input_hash,
        "cutoff": observation.cutoff,
        "cutoff_bar_id": observation.cutoff_bar_id,
        "cutoff_at": _datetime_text(observation.cutoff_at),
        "engine_confirmation": observation.engine_confirmation,
        "application_observation_status": observation.application_observation_status,
        "structures": [_structure_payload(item) for item in observation.structures],
    }


def _validate_structure_identity(observation: ResearchObservation, structure: StructureEvidence) -> None:
    expected_key = stable_hash(
        {
            "instrument": observation.instrument,
            "interval": observation.interval,
            "engine_id": observation.engine_id,
            "engine_version": observation.engine_version,
            "dialect_id": observation.dialect_id,
            "config_id": observation.config_id,
            "price_basis_id": observation.price_basis_id,
            "kind": structure.kind,
            "direction": structure.direction,
            "mark": structure.mark,
            "source_start": structure.source_start,
            "source_end": structure.source_end,
            "source_start_bar_id": structure.source_start_bar_id,
            "source_end_bar_id": structure.source_end_bar_id,
        }
    )
    expected_revision = stable_hash(
        {
            "observation_id": observation.observation_id,
            "structure_key": expected_key,
            "payload": {
                "geometry": structure.geometry_payload(),
                "engine_state": structure.engine_state,
            },
        }
    )
    if structure.structure_key != expected_key or structure.revision_id != expected_revision:
        raise ChanContractError("structure_identity_mismatch", "structure key or revision does not match canonical evidence")


def _validate_observation(observation: ResearchObservation) -> tuple[str, dict[str, Any], str]:
    if not isinstance(observation, ResearchObservation):
        raise ChanContractError("invalid_observation", "publisher accepts only validated ResearchObservation records")
    for field, maximum in _MAX_TEXT_LENGTHS.items():
        _text_value(getattr(observation, field), field, maximum)
    _text_value(observation.input_revision_id, "input_revision_id", 256)
    if observation.settlement_status not in {"settled", "temporary"}:
        raise ChanContractError("invalid_settlement_status", "settlement status must be settled or temporary")
    if observation.engine_id != ENGINE_ID or observation.engine_version != ENGINE_VERSION or observation.dialect_id != DIALECT_ID:
        raise ChanContractError("unsupported_engine_namespace", "observation is outside the selected disabled engine contract")
    if observation.engine_confirmation != "unknown" or observation.application_observation_status != "observed":
        raise ChanContractError("observation_not_complete", "only complete observed records with unknown confirmation may be published")
    if isinstance(observation.cutoff, bool) or not isinstance(observation.cutoff, int) or observation.cutoff <= 0:
        raise ChanContractError("invalid_observation_cutoff", "cutoff must be a positive source-bar count")
    _datetime_text(observation.cutoff_at)
    for field in ("input_hash", "observation_id"):
        value = getattr(observation, field)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ChanContractError("invalid_observation_hash", f"{field} must be a lowercase SHA-256 digest")
    expected_observation_id = stable_hash(
        {
            "instrument": observation.instrument,
            "interval": observation.interval,
            "cutoff": observation.cutoff,
            "input_hash": observation.input_hash,
            "price_basis_id": observation.price_basis_id,
            "engine_id": observation.engine_id,
            "engine_version": observation.engine_version,
            "dialect_id": observation.dialect_id,
            "config_id": observation.config_id,
        }
    )
    if observation.observation_id != expected_observation_id:
        raise ChanContractError("observation_identity_mismatch", "observation ID does not match its canonical input identity")

    structure_keys: set[str] = set()
    for structure in observation.structures:
        if not isinstance(structure, StructureEvidence):
            raise ChanContractError("invalid_structure_evidence", "observation contains an unvalidated structure")
        if structure.structure_key in structure_keys:
            raise ChanContractError("duplicate_structure_key", "an observation cannot contain duplicate structure keys")
        structure_keys.add(structure.structure_key)
        _validate_structure_identity(observation, structure)

    namespace = _namespace(observation)
    stream_id = _stream_id(namespace)
    payload = _observation_payload(observation, stream_id)
    return stream_id, payload, stable_hash(payload)


def _stored_observation_payload(row: ChanResearchObservation) -> dict[str, Any]:
    payload = row.payload_json
    columns = {
        "stream_id": row.stream_id,
        "observation_id": row.observation_id,
        "instrument": row.instrument,
        "interval": row.interval,
        "series_id": row.series_id,
        "price_basis_id": row.price_basis_id,
        "adjustment_version": row.adjustment_version,
        "config_id": row.config_id,
        "input_revision_id": row.input_revision_id,
        "settlement_status": row.settlement_status,
        "input_hash": row.input_hash,
        "cutoff": row.cutoff,
        "cutoff_bar_id": row.cutoff_bar_id,
        "cutoff_at": row.cutoff_at,
        "engine_id": row.engine_id,
        "engine_version": row.engine_version,
        "dialect_id": row.dialect_id,
        "engine_confirmation": row.engine_confirmation,
        "application_observation_status": row.application_observation_status,
    }
    if not isinstance(payload, dict) or any(payload.get(key) != value for key, value in columns.items()):
        raise ChanContractError("persistent_evidence_corrupt", "stored observation columns do not match their immutable payload")
    if stable_hash(payload) != row.payload_hash:
        raise ChanContractError("persistent_evidence_corrupt", "stored observation payload hash does not match")
    return payload


def _stored_structure_state(
    row: ChanStructureRevision,
    observation_row: ChanResearchObservation,
) -> ObservedStructureState:
    payload = row.payload_json
    if (
        not isinstance(payload, dict)
        or payload.get("stream_id") != row.stream_id
        or payload.get("observation_id") != row.observation_id
        or payload.get("structure_key") != row.structure_key
        or payload.get("revision_id") != row.revision_id
        or stable_hash(payload) != row.payload_hash
    ):
        raise ChanContractError("persistent_evidence_corrupt", "stored structure revision does not match its immutable payload")
    geometry = payload.get("geometry")
    if not isinstance(geometry, dict):
        raise ChanContractError("persistent_evidence_corrupt", "stored structure geometry is invalid")
    observation_payload = _stored_observation_payload(observation_row)
    expected_key = stable_hash(
        {
            "instrument": observation_row.instrument,
            "interval": observation_row.interval,
            "engine_id": observation_row.engine_id,
            "engine_version": observation_row.engine_version,
            "dialect_id": observation_row.dialect_id,
            "config_id": observation_row.config_id,
            "price_basis_id": observation_row.price_basis_id,
            "kind": payload.get("kind"),
            "direction": payload.get("direction"),
            "mark": payload.get("mark"),
            "source_start": payload.get("source_start"),
            "source_end": payload.get("source_end"),
            "source_start_bar_id": payload.get("source_start_bar_id"),
            "source_end_bar_id": payload.get("source_end_bar_id"),
        }
    )
    expected_revision = stable_hash(
        {
            "observation_id": row.observation_id,
            "structure_key": expected_key,
            "payload": {"geometry": geometry, "engine_state": payload.get("engine_state")},
        }
    )
    if row.structure_key != expected_key or row.revision_id != expected_revision:
        raise ChanContractError("persistent_evidence_corrupt", "stored structure identity does not match its canonical preimage")
    del observation_payload
    return ObservedStructureState(
        geometry=tuple(sorted((str(key), float(value)) for key, value in geometry.items())),
        engine_state=payload.get("engine_state"),
        revision_id=row.revision_id,
    )


def verified_observation_payload(row: ChanResearchObservation) -> dict[str, Any]:
    """Return a detached observation payload after the canonical M3 checks pass."""

    return deepcopy(_stored_observation_payload(row))


def verified_structure_payload(
    row: ChanStructureRevision,
    observation_row: ChanResearchObservation,
) -> dict[str, Any]:
    """Return detached structure evidence only after canonical key/revision checks pass."""

    _stored_structure_state(row, observation_row)
    return deepcopy(row.payload_json)


class ChanObservationPublisher:
    """Append a complete observation and atomically move its stream head.

    The caller owns the SQLAlchemy transaction and commits only after the full
    surrounding unit succeeds. PostgreSQL advisory locking serializes competing
    publications even when a stream head has not been created yet.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def _lock_stream(self, stream_id: str) -> None:
        if self.session.get_bind().dialect.name == "postgresql":
            lock_key = int(stream_id[:16], 16)
            if lock_key >= 2**63:
                lock_key -= 2**64
            self.session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def publish(self, observation: ResearchObservation) -> ObservationPublication:
        stream_id, payload, payload_hash = _validate_observation(observation)
        self._lock_stream(stream_id)

        existing = self.session.get(ChanResearchObservation, observation.observation_id)
        if existing is not None:
            _stored_observation_payload(existing)
            if existing.stream_id != stream_id or existing.payload_hash != payload_hash:
                raise ChanContractError(
                    "observation_id_conflict",
                    "an observation ID cannot be reused for different namespace or evidence",
                )
            return ObservationPublication(stream_id, observation.observation_id, (), already_published=True)

        namespace = _namespace(observation)
        head = self.session.scalar(
            select(ChanResearchStreamHead)
            .where(ChanResearchStreamHead.stream_id == stream_id)
            .with_for_update()
        )
        sequence_number = head.latest_sequence_number + 1 if head is not None else 1
        previous_current: dict[str, ObservedStructureState] = {}
        seen_keys: frozenset[str] = frozenset()
        if head is not None:
            if any(getattr(head, key) != value for key, value in namespace.items()):
                raise ChanContractError("stream_identity_conflict", "stream hash collides with different namespace fields")
            previous_observation = self.session.get(ChanResearchObservation, head.latest_observation_id)
            if (
                previous_observation is None
                or previous_observation.stream_id != stream_id
                or previous_observation.sequence_number != head.latest_sequence_number
            ):
                raise ChanContractError("persistent_evidence_corrupt", "stream head points to a missing observation")
            _stored_observation_payload(previous_observation)
            if observation.cutoff < previous_observation.cutoff:
                raise ChanContractError("observation_order_reversed", "observation cutoffs must not move backward")
            previous_cutoff_at = datetime.fromisoformat(previous_observation.cutoff_at)
            if observation.cutoff_at < previous_cutoff_at:
                raise ChanContractError("observation_time_reversed", "observation cutoff timestamps must not move backward")

            prior_rows = list(
                self.session.scalars(
                    select(ChanStructureRevision)
                    .where(
                        ChanStructureRevision.stream_id == stream_id,
                        ChanStructureRevision.observation_id == previous_observation.observation_id,
                    )
                    .order_by(ChanStructureRevision.structure_key)
                )
            )
            previous_current = {
                row.structure_key: _stored_structure_state(row, previous_observation) for row in prior_rows
            }
            seen_keys = frozenset(
                self.session.scalars(
                    select(ChanObservedTransition.structure_key)
                    .where(
                        ChanObservedTransition.stream_id == stream_id,
                        ChanObservedTransition.revision_id.is_not(None),
                    )
                    .distinct()
                )
            )

        transitions = derive_observed_transitions(observation, previous_current, seen_keys)
        self.session.add(
            ChanResearchObservation(
                observation_id=observation.observation_id,
                stream_id=stream_id,
                sequence_number=sequence_number,
                instrument=observation.instrument,
                interval=observation.interval,
                series_id=observation.series_id,
                price_basis_id=observation.price_basis_id,
                adjustment_version=observation.adjustment_version,
                input_revision_id=observation.input_revision_id,
                settlement_status=observation.settlement_status,
                config_id=observation.config_id,
                input_hash=observation.input_hash,
                cutoff=observation.cutoff,
                cutoff_bar_id=observation.cutoff_bar_id,
                cutoff_at=payload["cutoff_at"],
                engine_id=observation.engine_id,
                engine_version=observation.engine_version,
                dialect_id=observation.dialect_id,
                engine_confirmation=observation.engine_confirmation,
                application_observation_status=observation.application_observation_status,
                payload_hash=payload_hash,
                payload_json=payload,
            )
        )
        for structure in observation.structures:
            structure_payload = _structure_payload(structure)
            structure_payload.update({"stream_id": stream_id, "observation_id": observation.observation_id})
            self.session.add(
                ChanStructureRevision(
                    revision_id=structure.revision_id,
                    stream_id=stream_id,
                    observation_id=observation.observation_id,
                    structure_key=structure.structure_key,
                    payload_hash=stable_hash(structure_payload),
                    payload_json=structure_payload,
                )
            )
        # Establish the immutable observation/revision rows before transitions
        # that carry foreign keys to those exact revision IDs.
        self.session.flush()
        for transition in transitions:
            self.session.add(
                ChanObservedTransition(
                    stream_id=stream_id,
                    observation_id=transition.observation_id,
                    structure_key=transition.structure_key,
                    cutoff_bar_id=transition.cutoff_bar_id,
                    status=transition.status,
                    revision_id=transition.revision_id,
                    prior_revision_id=transition.prior_revision_id,
                    reappearance=transition.reappearance,
                )
            )

        if head is None:
            head = ChanResearchStreamHead(
                stream_id=stream_id,
                **namespace,
                latest_sequence_number=sequence_number,
                latest_observation_id=observation.observation_id,
            )
            self.session.add(head)
        else:
            head.latest_sequence_number = sequence_number
            head.latest_observation_id = observation.observation_id
        self.session.flush()
        return ObservationPublication(stream_id, observation.observation_id, transitions)
