from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DecisionBoardSnapshot, Instrument, SignalSnapshot
from app.utils.current_decision import resolve_current_decision


class CurrentDecisionService:
    """Read the single current ETF decision contract for compatibility consumers.

    Precedence is intentionally identical to Signal Center:
    DecisionBoardSnapshot -> SignalGradeService -> SignalSnapshot last-resort audit.
    No consumer-specific score is allowed to create another current action.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @staticmethod
    def latest_board_rows(db: Session) -> tuple[str | None, dict[str, dict[str, Any]]]:
        snapshot = db.scalar(
            select(DecisionBoardSnapshot)
            .order_by(DecisionBoardSnapshot.generated_at.desc(), DecisionBoardSnapshot.id.desc())
            .limit(1)
        )
        if snapshot is None:
            return None, {}
        payload = snapshot.payload_json if isinstance(snapshot.payload_json, dict) else {}
        mapped: dict[str, dict[str, Any]] = {}
        for row in payload.get("rows", []) or []:
            if not isinstance(row, dict):
                continue
            code = str(row.get("ts_code") or "").strip().upper()
            if code:
                mapped[code] = row
        return snapshot.snapshot_id, mapped

    def resolve_many(
        self,
        db: Session,
        instruments: list[Instrument],
    ) -> tuple[str | None, dict[str, dict[str, Any]]]:
        snapshot_id, board_rows = self.latest_board_rows(db)
        codes = {str(item.ts_code).strip().upper() for item in instruments}
        missing = {code for code in codes if not (board_rows.get(code) or {}).get("grade")}

        # SignalGradeService imports KlineStabilizationService for indicator helpers.
        # Kline compatibility also imports this resolver. Keep the dependency lazy
        # so module initialization remains acyclic while the runtime precedence is
        # still exactly DecisionBoard -> SignalGrade -> SignalSnapshot.
        if missing:
            from app.services.signal_grade_service import SignalGradeService

            grade_payload = SignalGradeService(self.settings).build(db)
        else:
            grade_payload = {}
        grade_rows = {
            str(row.get("ts_code") or "").strip().upper(): row
            for row in grade_payload.get("rows", [])
            if str(row.get("ts_code") or "").strip().upper() in missing
        }

        latest_signals: dict[int, SignalSnapshot] = {}
        for snapshot in db.scalars(
            select(SignalSnapshot).order_by(SignalSnapshot.as_of_time.asc())
        ).all():
            latest_signals[snapshot.instrument_id] = snapshot

        result: dict[str, dict[str, Any]] = {}
        for instrument in instruments:
            code = str(instrument.ts_code).strip().upper()
            board = board_rows.get(code)
            fallback = grade_rows.get(code)
            production = latest_signals.get(instrument.id)
            resolved = resolve_current_decision(
                decision_board_grade=(board or {}).get("grade"),
                signal_grade_fallback=(fallback or {}).get("grade"),
                production_signal_state=production.state if production is not None else None,
            )
            result[code] = {
                "state": resolved.state if resolved is not None else "数据异常",
                "source": resolved.source if resolved is not None else "unavailable",
                "canonical": resolved.canonical if resolved is not None else False,
                "decision_board_grade": (board or {}).get("grade"),
                "signal_grade_fallback": (fallback or {}).get("grade"),
                "production_signal_state": production.state if production is not None else None,
            }
        return snapshot_id, result
