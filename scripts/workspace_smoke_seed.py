"""Seed only an explicitly isolated mock browser-test database; never production."""
from __future__ import annotations
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import get_settings
from app.db.session import init_db, session_scope
from app.services.task_service import TaskService
from app.services.decision_board_service import DecisionBoardService


def main():
    settings = get_settings()
    if not (settings.app_env == 'test' and settings.market_provider == 'mock' and not settings.auth_enabled and 'workspace-e2e' in settings.database_url and settings.database_url.startswith('sqlite:')):
        raise SystemExit('browser seed requires isolated test/mock SQLite workspace-e2e database')
    database = Path(settings.database_url.removeprefix('sqlite:///'))
    # Every Playwright run must start from a new isolated fixture.  Without
    # this guard a rerun inherits a prior test's watchlist/holding revisions
    # and makes later tests fail for stateful reasons.
    for suffix in ('', '-journal', '-wal', '-shm'):
        database.with_name(database.name + suffix).unlink(missing_ok=True)
    init_db()
    with session_scope() as db:
        service = TaskService(settings)
        try:
            service.run(db, 'bootstrap', lookback_days=420, report=False)
            service.run(db, 'refresh_index_history', lookback_days=420, report=False)
            DecisionBoardService(settings).refresh(db)
        finally:
            service.close()
    print('isolated mock browser fixture ready; real-market qualification unchanged')

if __name__ == '__main__':
    main()
