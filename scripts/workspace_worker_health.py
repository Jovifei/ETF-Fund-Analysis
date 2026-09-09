"""Check the durable worker heartbeat without printing DB credentials or errors."""
from datetime import datetime, timezone
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.db.session import session_scope
from app.workspace.models import WorkspacePreference


def healthy() -> bool:
    try:
        with session_scope() as db:
            row = db.get(WorkspacePreference, 'system:workspace-worker')
            raw = (row.settings_json if row else {}).get('last_seen_at')
        if not raw:
            return False
        observed = datetime.fromisoformat(raw)
        if observed.tzinfo is None:
            return False
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        return 0 <= age < 90
    except Exception:
        return False


if __name__ == '__main__':
    raise SystemExit(0 if healthy() else 1)
