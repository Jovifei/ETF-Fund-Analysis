"""Pure append-only replay for the selected observed-revision research dialect."""
from __future__ import annotations

from dataclasses import dataclass

from app.research.chan_contract import ChanContractError, ResearchObservation, StructureEvidence


@dataclass(frozen=True, slots=True)
class ObservedTransition:
    observation_id: str
    cutoff_bar_id: str
    structure_key: str
    status: str
    revision_id: str | None
    prior_revision_id: str | None = None
    reappearance: bool = False


class ObservedRevisionReplay:
    """In-memory reference accumulator; it never edits previously emitted records."""

    def __init__(self) -> None:
        self._observations: tuple[ResearchObservation, ...] = ()
        self._history: tuple[ObservedTransition, ...] = ()
        self._current: dict[str, StructureEvidence] = {}
        self._seen_keys: frozenset[str] = frozenset()
        self._stream_identity: tuple[str, str, str, str, str, str, str, str, str] | None = None

    @property
    def observations(self) -> tuple[ResearchObservation, ...]:
        return self._observations

    @property
    def history(self) -> tuple[ObservedTransition, ...]:
        return self._history

    def append(self, observation: ResearchObservation) -> tuple[ObservedTransition, ...]:
        if not isinstance(observation, ResearchObservation):
            raise ChanContractError("invalid_observation", "replay accepts a validated ResearchObservation")
        identity = (
            observation.instrument,
            observation.interval,
            observation.series_id,
            observation.price_basis_id,
            observation.adjustment_version,
            observation.config_id,
            observation.engine_id,
            observation.engine_version,
            observation.dialect_id,
        )
        if self._stream_identity is not None and identity != self._stream_identity:
            raise ChanContractError(
                "replay_stream_mismatch",
                "instrument, interval, series, basis, adjustment, config, engine, and dialect must not change",
            )
        if self._observations:
            previous_observation = self._observations[-1]
            if observation.cutoff < previous_observation.cutoff:
                raise ChanContractError("observation_order_reversed", "observation cutoffs must not move backward")
            if observation.cutoff_at < previous_observation.cutoff_at:
                raise ChanContractError(
                    "observation_time_reversed",
                    "observation cutoff timestamps must not move backward",
                )
            if observation.observation_id == previous_observation.observation_id:
                if observation != previous_observation:
                    raise ChanContractError(
                        "observation_id_conflict",
                        "one observation ID cannot bind different normalized evidence",
                    )
                return ()

        current: dict[str, StructureEvidence] = {}
        for structure in observation.structures:
            if structure.structure_key in current:
                raise ChanContractError("duplicate_structure_key", "an observation cannot contain duplicate structure keys")
            current[structure.structure_key] = structure

        events: list[ObservedTransition] = []
        for key in sorted(current):
            structure = current[key]
            previous = self._current.get(key)
            if previous is None:
                status = "OBSERVED_NEW"
                reappearance = key in self._seen_keys
            elif (
                previous.geometry == structure.geometry
                and previous.engine_state == structure.engine_state
            ):
                status = "OBSERVED_UNCHANGED"
                reappearance = False
            else:
                status = "OBSERVED_CHANGED"
                reappearance = False
            events.append(
                ObservedTransition(
                    observation_id=observation.observation_id,
                    cutoff_bar_id=observation.cutoff_bar_id,
                    structure_key=key,
                    status=status,
                    revision_id=structure.revision_id,
                    prior_revision_id=previous.revision_id if previous else None,
                    reappearance=reappearance,
                )
            )

        for key in sorted(self._current.keys() - current.keys()):
            prior = self._current[key]
            events.append(
                ObservedTransition(
                    observation_id=observation.observation_id,
                    cutoff_bar_id=observation.cutoff_bar_id,
                    structure_key=key,
                    status="OBSERVED_ABSENT",
                    revision_id=None,
                    prior_revision_id=prior.revision_id,
                )
            )

        # Build the full next state before committing so any validation failure
        # leaves the replay reusable and does not pin an invalid stream identity.
        next_observations = self._observations + (observation,)
        next_history = self._history + tuple(events)
        next_seen_keys = self._seen_keys | frozenset(current)
        next_stream_identity = self._stream_identity or identity
        (
            self._observations,
            self._history,
            self._current,
            self._seen_keys,
            self._stream_identity,
        ) = (next_observations, next_history, current, next_seen_keys, next_stream_identity)
        return tuple(events)
