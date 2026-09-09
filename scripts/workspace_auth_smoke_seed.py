"""Seed only the disposable, explicitly named authentication browser fixture."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import get_settings
from app.db.session import init_db, session_scope
from app.services.auth_service import AuthService


def main():
    settings = get_settings()
    if not (settings.app_env == 'test' and settings.market_provider == 'mock' and settings.auth_enabled
            and settings.database_url.startswith('sqlite:///')
            and Path(settings.database_url.removeprefix('sqlite:///')).name == 'workspace-e2e-auth.sqlite3'):
        raise SystemExit('auth fixture requires isolated test/mock workspace-e2e-auth.sqlite3')
    database = Path(settings.database_url.removeprefix('sqlite:///'))
    for suffix in ('','-journal','-wal','-shm'):
        database.with_name(database.name + suffix).unlink(missing_ok=True)
    init_db()
    with session_scope() as db:
        # Public disposable test credential, not a deployment default.
        AuthService().create_user(db, username='browser-admin', password='test-only-browser-pass', role='admin')
    print('isolated auth browser fixture initialized; production untouched')

if __name__ == '__main__':
    main()
