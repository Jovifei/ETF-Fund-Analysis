"""Verified, read-only projection of the latest persisted R4C observation."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import (
    ChanObservedTransition,
    ChanResearchObservation,
    ChanResearchStreamHead,
    ChanStructureRevision,
)
from app.research.chan_contract import DIALECT_ID, ENGINE_ID, ENGINE_VERSION, ChanContractError
from app.services.chan_observation_service import (
    verified_observation_payload,
    verified_structure_payload,
)

_INTERVALS = frozenset({"D", "W", "M"})
_STRUCTURE_KINDS = frozenset({"fx", "bi", "zs"})
_TRANSITION_STATUSES = frozenset(
    {"OBSERVED_NEW", "OBSERVED_CHANGED", "OBSERVED_UNCHANGED", "OBSERVED_ABSENT"}
)
_VIEW_SEMANTICS = "latest_persisted_observed_revision_not_historical_pit"


def _unavailable(code: str, interval: str, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason_code": reason,
        "ts_code": code,
        "interval": interval,
        "view_semantics": _VIEW_SEMANTICS,
        "provider_called": False,
        "engine_called": False,
        "models_called": False,
        "qualification_changed": False,
        "actionable": False,
    }


def _cutoff_rank(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ChanContractError("persistent_evidence_corrupt", "stored cutoff_at is not text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ChanContractError("persistent_evidence_corrupt", "stored cutoff_at is invalid") from exc
    if parsed.tzinfo is not None:
        raise ChanContractError("persistent_evidence_corrupt", "stored cutoff_at must use normalized UTC-naive form")
    return parsed.replace(tzinfo=UTC)


def _verify_head(db: Session, head: ChanResearchStreamHead) -> tuple[ChanResearchObservation, dict[str, Any], datetime]:
    observation = db.get(ChanResearchObservation, head.latest_observation_id)
    if observation is None:
        raise ChanContractError("persistent_evidence_corrupt", "stream head points to a missing observation")

    head_columns = (
        "stream_id",
        "instrument",
        "interval",
        "series_id",
        "price_basis_id",
        "adjustment_version",
        "config_id",
        "engine_id",
        "engine_version",
        "dialect_id",
    )
    if (
        head.latest_observation_id != observation.observation_id
        or head.latest_sequence_number != observation.sequence_number
        or any(getattr(head, name) != getattr(observation, name) for name in head_columns)
    ):
        raise ChanContractError("persistent_evidence_corrupt", "stream head columns do not match its latest observation")

    payload = verified_observation_payload(observation)
    if not isinstance(payload.get("structures"), list):
        raise ChanContractError("persistent_evidence_corrupt", "observation structures payload is invalid")
    return observation, payload, _cutoff_rank(observation.cutoff_at)


def _verified_structures(
    db: Session,
    observation: ChanResearchObservation,
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    expected_items = payload.get("structures")
    if not isinstance(expected_items, list):
        raise ChanContractError("persistent_evidence_corrupt", "observation structures payload is invalid")

    expected_by_key: dict[str, dict[str, Any]] = {}
    for item in expected_items:
        if not isinstance(item, dict):
            raise ChanContractError("persistent_evidence_corrupt", "observation structure entry is invalid")
        key = item.get("structure_key")
        if not isinstance(key, str) or key in expected_by_key:
            raise ChanContractError("persistent_evidence_corrupt", "observation structure keys are invalid")
        if item.get("kind") not in _STRUCTURE_KINDS:
            raise ChanContractError("persistent_evidence_corrupt", "observation structure kind is invalid")
        expected_by_key[key] = item

    rows = list(
        db.scalars(
            select(ChanStructureRevision)
            .where(ChanStructureRevision.observation_id == observation.observation_id)
            .order_by(ChanStructureRevision.structure_key)
        )
    )
    actual_by_key: dict[str, dict[str, Any]] = {}
    output: list[dict[str, Any]] = []
    returned_fields = (
        "kind",
        "direction",
        "mark",
        "source_start",
        "source_end",
        "source_start_bar_id",
        "source_end_bar_id",
        "geometry",
        "engine_state",
        "structure_key",
        "revision_id",
    )

    for row in rows:
        if row.stream_id != observation.stream_id or row.observation_id != observation.observation_id:
            raise ChanContractError("persistent_evidence_corrupt", "structure revision is bound to the wrong observation")
        structure = verified_structure_payload(row, observation)
        expected = expected_by_key.get(row.structure_key)
        if expected is None or any(structure.get(name) != expected.get(name) for name in returned_fields):
            raise ChanContractError("persistent_evidence_corrupt", "revision set does not match observation structures")
        if row.structure_key in actual_by_key:
            raise ChanContractError("persistent_evidence_corrupt", "duplicate structure revision key")
        actual_by_key[row.structure_key] = structure
        output.append({name: structure.get(name) for name in returned_fields})

    if set(actual_by_key) != set(expected_by_key):
        raise ChanContractError("persistent_evidence_corrupt", "revision set does not match observation structures")
    return output, actual_by_key


def _previous_structures(
    db: Session,
    observation: ChanResearchObservation,
) -> dict[str, dict[str, Any]]:
    if observation.sequence_number == 1:
        return {}

    previous = db.scalar(
        select(ChanResearchObservation).where(
            ChanResearchObservation.stream_id == observation.stream_id,
            ChanResearchObservation.sequence_number == observation.sequence_number - 1,
        )
    )
    if previous is None:
        raise ChanContractError("persistent_evidence_corrupt", "previous stream observation is missing")
    namespace_columns = (
        "stream_id",
        "instrument",
        "interval",
        "series_id",
        "price_basis_id",
        "adjustment_version",
        "config_id",
        "engine_id",
        "engine_version",
        "dialect_id",
    )
    if any(getattr(previous, name) != getattr(observation, name) for name in namespace_columns):
        raise ChanContractError("persistent_evidence_corrupt", "previous observation belongs to a different namespace")
    if (
        previous.cutoff > observation.cutoff
        or _cutoff_rank(previous.cutoff_at) > _cutoff_rank(observation.cutoff_at)
    ):
        raise ChanContractError("persistent_evidence_corrupt", "previous observation chronology moves backward")

    payload = verified_observation_payload(previous)
    if not isinstance(payload.get("structures"), list):
        raise ChanContractError("persistent_evidence_corrupt", "previous observation structures payload is invalid")
    _, structures = _verified_structures(db, previous, payload)
    return structures


def _has_prior_revision_witness(
    db: Session,
    observation: ChanResearchObservation,
    structure_key: str,
) -> bool:
    witness = db.execute(
        select(ChanObservedTransition, ChanResearchObservation)
        .join(
            ChanResearchObservation,
            and_(
                ChanResearchObservation.stream_id == ChanObservedTransition.stream_id,
                ChanResearchObservation.observation_id == ChanObservedTransition.observation_id,
            ),
        )
        .where(
            ChanObservedTransition.stream_id == observation.stream_id,
            ChanObservedTransition.structure_key == structure_key,
            ChanObservedTransition.revision_id.is_not(None),
            ChanResearchObservation.sequence_number < observation.sequence_number,
        )
        .order_by(ChanResearchObservation.sequence_number.desc())
        .limit(1)
    ).first()
    if witness is None:
        return False

    transition, witness_observation = witness
    namespace_columns = (
        "stream_id",
        "instrument",
        "interval",
        "series_id",
        "price_basis_id",
        "adjustment_version",
        "config_id",
        "engine_id",
        "engine_version",
        "dialect_id",
    )
    if (
        any(getattr(witness_observation, name) != getattr(observation, name) for name in namespace_columns)
        or transition.stream_id != witness_observation.stream_id
        or transition.observation_id != witness_observation.observation_id
        or transition.cutoff_bar_id != witness_observation.cutoff_bar_id
        or transition.status not in {"OBSERVED_NEW", "OBSERVED_CHANGED", "OBSERVED_UNCHANGED"}
    ):
        raise ChanContractError("persistent_evidence_corrupt", "historical transition witness is inconsistent")

    payload = verified_observation_payload(witness_observation)
    if not isinstance(payload.get("structures"), list):
        raise ChanContractError("persistent_evidence_corrupt", "historical witness observation payload is invalid")
    _, structures = _verified_structures(db, witness_observation, payload)
    verified = structures.get(structure_key)
    if verified is None or verified.get("revision_id") != transition.revision_id:
        raise ChanContractError("persistent_evidence_corrupt", "historical transition witness references another revision")
    return True


def _verified_transitions(
    db: Session,
    observation: ChanResearchObservation,
    current_structures: dict[str, dict[str, Any]],
    previous_structures: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    expected: dict[str, tuple[str, str | None, str | None, bool]] = {}
    for key, current in current_structures.items():
        previous = previous_structures.get(key)
        if previous is None:
            expected[key] = (
                "OBSERVED_NEW",
                current["revision_id"],
                None,
                _has_prior_revision_witness(db, observation, key),
            )
        elif (
            previous.get("geometry") == current.get("geometry")
            and previous.get("engine_state") == current.get("engine_state")
        ):
            expected[key] = (
                "OBSERVED_UNCHANGED",
                current["revision_id"],
                previous["revision_id"],
                False,
            )
        else:
            expected[key] = (
                "OBSERVED_CHANGED",
                current["revision_id"],
                previous["revision_id"],
                False,
            )

    for key, previous in previous_structures.items():
        if key not in current_structures:
            expected[key] = ("OBSERVED_ABSENT", None, previous["revision_id"], False)

    rows = list(
        db.scalars(
            select(ChanObservedTransition)
            .where(ChanObservedTransition.observation_id == observation.observation_id)
            .order_by(ChanObservedTransition.structure_key)
        )
    )
    if len(rows) != len(expected) or {row.structure_key for row in rows} != set(expected):
        raise ChanContractError("persistent_evidence_corrupt", "stored transition set does not match replay")

    output: list[dict[str, Any]] = []
    for row in rows:
        status, revision_id, prior_revision_id, reappearance = expected[row.structure_key]
        if (
            row.stream_id != observation.stream_id
            or row.cutoff_bar_id != observation.cutoff_bar_id
            or row.status != status
            or row.revision_id != revision_id
            or row.prior_revision_id != prior_revision_id
            or row.reappearance is not reappearance
        ):
            raise ChanContractError("persistent_evidence_corrupt", "stored transition does not match replay")
        output.append(
            {
                "structure_key": row.structure_key,
                "status": status,
                "revision_id": revision_id,
                "prior_revision_id": prior_revision_id,
                "reappearance": reappearance,
            }
        )
    return output


def read_latest(db: Session, code: str, interval: str) -> dict[str, Any]:
    """Read the latest verified persisted revision; this is not a historical PIT view."""
    normalized_code = str(code or "").strip().upper()
    normalized_interval = str(interval or "").strip().upper()
    if normalized_interval not in _INTERVALS:
        return _unavailable(normalized_code, normalized_interval, "unsupported_interval")

    heads = list(
        db.scalars(
            select(ChanResearchStreamHead)
            .where(
                ChanResearchStreamHead.instrument == normalized_code,
                ChanResearchStreamHead.interval == normalized_interval,
                ChanResearchStreamHead.engine_id == ENGINE_ID,
                ChanResearchStreamHead.engine_version == ENGINE_VERSION,
                ChanResearchStreamHead.dialect_id == DIALECT_ID,
            )
            .order_by(ChanResearchStreamHead.stream_id)
        )
    )
    if not heads:
        return _unavailable(normalized_code, normalized_interval, "snapshot_missing")

    try:
        candidates = [(head, *_verify_head(db, head)) for head in heads]
        latest_cutoff = max(candidate[3] for candidate in candidates)
        latest = [candidate for candidate in candidates if candidate[3] == latest_cutoff]
        if len(latest) != 1:
            return _unavailable(normalized_code, normalized_interval, "ambiguous_stream_head")

        head, observation, payload, _ = latest[0]
        structures, structures_by_key = _verified_structures(db, observation, payload)
        previous_structures = _previous_structures(db, observation)
        transitions = _verified_transitions(db, observation, structures_by_key, previous_structures)
        transition_by_key = {item["structure_key"]: item for item in transitions}
        for structure in structures:
            transition = transition_by_key[structure["structure_key"]]
            structure["transition_status"] = transition["status"]
            structure["reappearance"] = transition["reappearance"]
    except ChanContractError:
        return _unavailable(normalized_code, normalized_interval, "persistent_evidence_corrupt")
    except (AttributeError, KeyError, TypeError, ValueError):
        return _unavailable(normalized_code, normalized_interval, "persistent_evidence_corrupt")

    counts = Counter(item["kind"] for item in structures)
    return {
        "available": True,
        "reason_code": None,
        "ts_code": normalized_code,
        "interval": normalized_interval,
        "view_semantics": _VIEW_SEMANTICS,
        "stream_id": head.stream_id,
        "observation_id": observation.observation_id,
        "sequence_number": observation.sequence_number,
        "series_id": observation.series_id,
        "price_basis_id": observation.price_basis_id,
        "adjustment_version": observation.adjustment_version,
        "config_id": observation.config_id,
        "input_revision_id": observation.input_revision_id,
        "input_hash": observation.input_hash,
        "settlement_status": observation.settlement_status,
        "cutoff": observation.cutoff,
        "cutoff_bar_id": observation.cutoff_bar_id,
        "cutoff_at": observation.cutoff_at,
        "engine_id": observation.engine_id,
        "engine_version": observation.engine_version,
        "dialect_id": observation.dialect_id,
        "engine_confirmation": observation.engine_confirmation,
        "application_observation_status": observation.application_observation_status,
        "counts": {kind: int(counts.get(kind, 0)) for kind in ("fx", "bi", "zs")},
        "structures": structures,
        "transitions": transitions,
        "source": "persisted_r4c_observed_revision",
        "provider_called": False,
        "engine_called": False,
        "models_called": False,
        "qualification_changed": False,
        "actionable": False,
    }
