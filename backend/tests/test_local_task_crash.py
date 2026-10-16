"""A local process death must not strand a separately committed board TaskRun."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.models import TaskRun
from app.services.task_service import TaskService
from app.workspace.local_compute import compute_local, compute_board_only


@pytest.mark.parametrize('mode', ['full', 'board_only'])
def test_local_board_transaction_rolls_back_savepoint_on_process_death(tmp_path, monkeypatch, mode):
    settings = Settings(_env_file=None, market_provider='public_composite',
                        database_url=f'sqlite:///{tmp_path / "research.sqlite3"}')
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    def execute(self, db, task_name, run_id, **kwargs):
        if task_name == 'refresh_decision_board':
            raise SystemExit('simulated process death after board savepoint')
        return {'status': 'succeeded'}
    monkeypatch.setattr(TaskService, '_execute', execute)
    monkeypatch.setattr('app.services.settlement.stamp_output_completion', lambda db, cfg, task, result, *a, **k: result)
    with pytest.raises(SystemExit):
        if mode == 'full':
            compute_local(settings, private_research=True)
        else:
            compute_board_only(settings)
    with Session(engine) as db:
        assert db.scalar(select(TaskRun).where(TaskRun.task_name == 'refresh_decision_board',
                                               TaskRun.status == 'running')) is None
    engine.dispose()
