from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import EventLog


def emit_event(db: Session, event_type: str, payload: dict[str, Any] | None = None) -> EventLog:
    event = EventLog(event_type=event_type, payload_json=payload or {})
    db.add(event)
    db.flush()
    return event
