"""Execute bounded internal Chan jobs through the accepted freeze/adapter/publisher contracts."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.session import session_scope
from app.models import Instrument
from app.research.chan_adapter import ChanAdapter, ChanAdapterError
from app.research.chan_contract import ChanContractError
from app.research.chan_input import BLOCKED_REASON_CODES, FrozenChanInput, freeze_chan_input
from app.services.chan_observation_service import ChanObservationPublisher
from app.workspace.protocol import ChanStructuresJobRequest

_REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_STRUCTURE_KINDS = ("fx", "bi", "zs")
_SERVICE_BLOCKED_REASON_CODES = BLOCKED_REASON_CODES | {"unsupported_instrument_type"}


class ChanStructureService:
    """Run each instrument independently with no database transaction around CZSC."""

    def __init__(self, settings: Settings | None = None, *, adapter: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.adapter = adapter if adapter is not None else ChanAdapter()

    @staticmethod
    def _reason_code(error: BaseException, *, fallback: str = "processing_failed") -> str:
        code = getattr(error, "code", None)
        if isinstance(error, ChanAdapterError) and code in {
            "engine_dependency_missing",
            "unsupported_engine_version",
            "engine_import_failed",
            "engine_binding_invalid",
            "source_endpoint_invalid",
            "unsupported_interval",
            "unprepared_input",
        }:
            return code
        if isinstance(error, ChanContractError) and isinstance(code, str) and _REASON_CODE.fullmatch(code):
            return code
        return fallback

    @staticmethod
    def _structure_counts(observation: Any) -> dict[str, int]:
        counts = Counter(
            structure.kind for structure in observation.structures if structure.kind in _STRUCTURE_KINDS
        )
        return {kind: int(counts.get(kind, 0)) for kind in _STRUCTURE_KINDS}

    def _freeze(self, code: str, interval: str, as_of) -> FrozenChanInput:
        with session_scope() as db:
            instrument = db.scalar(select(Instrument).where(Instrument.ts_code == code))
            if instrument is None:
                return FrozenChanInput(status="blocked", reason_code="instrument_missing")
            if instrument.kind not in {"ETF", "LOF"}:
                return FrozenChanInput(status="blocked", reason_code="unsupported_instrument_type")
            return freeze_chan_input(
                db,
                self.settings,
                code,
                interval=interval,
                as_of=as_of,
            )

    def _publish(self, observation) -> tuple[bool, int]:
        from app.models.entities import ChanResearchObservation

        with session_scope() as db:
            publication = ChanObservationPublisher(db).publish(observation)
            stored = db.get(ChanResearchObservation, observation.observation_id)
            if stored is None or not isinstance(stored.sequence_number, int):
                raise ChanContractError("persistent_evidence_corrupt", "published observation sequence is missing")
            return publication.already_published, stored.sequence_number

    def run(self, request: ChanStructuresJobRequest) -> tuple[str, dict[str, Any]]:
        canonical = ChanStructuresJobRequest.model_validate(request)
        outcomes: list[dict[str, Any]] = []

        for code in canonical.codes:
            try:
                frozen = self._freeze(code, canonical.interval, canonical.as_of)
            except Exception as error:
                outcomes.append(
                    {
                        "ts_code": code,
                        "interval": canonical.interval,
                        "status": "failed",
                        "reason_code": self._reason_code(error),
                    }
                )
                continue

            if frozen.status == "blocked":
                reason = (
                    frozen.reason_code
                    if frozen.reason_code in _SERVICE_BLOCKED_REASON_CODES
                    else "history_qualification_blocked"
                )
                outcomes.append(
                    {
                        "ts_code": code,
                        "interval": canonical.interval,
                        "status": "blocked",
                        "reason_code": reason,
                    }
                )
                continue

            try:
                observation = self.adapter.observe(frozen.prepared)
            except Exception as error:
                outcomes.append(
                    {
                        "ts_code": code,
                        "interval": canonical.interval,
                        "status": "failed",
                        "reason_code": self._reason_code(error),
                    }
                )
                continue

            try:
                already_published, sequence = self._publish(observation)
            except Exception as error:
                outcomes.append(
                    {
                        "ts_code": code,
                        "interval": canonical.interval,
                        "status": "failed",
                        "reason_code": self._reason_code(error, fallback="publication_failed"),
                    }
                )
                continue

            outcomes.append(
                {
                    "ts_code": code,
                    "interval": canonical.interval,
                    "status": "idempotent" if already_published else "published",
                    "observation_id": observation.observation_id,
                    "input_hash": observation.input_hash,
                    "publication_sequence": sequence,
                    "already_published": already_published,
                    "structure_counts": self._structure_counts(observation),
                }
            )

        success_count = sum(item["status"] in {"published", "idempotent"} for item in outcomes)
        all_blocked = bool(outcomes) and all(item["status"] == "blocked" for item in outcomes)
        if success_count == len(outcomes):
            job_status = "succeeded"
        elif success_count or all_blocked:
            job_status = "partial"
        else:
            job_status = "failed"

        return job_status, {
            "items": outcomes,
            "provider_called": False,
            "models_called": False,
            "qualification_changed": False,
            "actionable": False,
        }
