from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.base import Base
from app.providers.base import CapabilityUnavailable
from app.services.task_service import TaskService
from app.workspace.offline_tasks import CacheOnlyTaskService


def test_offline_tasks_do_not_construct_or_rebind_upstream_without_credentials(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('upstream factory must not be called')
    monkeypatch.setattr('app.services.task_service.create_provider', forbidden)
    settings = get_settings().model_copy(update={'market_provider':'tushare','tushare_token':None})
    task = CacheOnlyTaskService(settings)
    assert task.settings.market_provider == 'tushare'
    task._bind_runtime_provider(None)
    with pytest.raises(CapabilityUnavailable):
        task.provider.fetch_daily_bars('510300.SH', date(2025,1,1), date(2025,2,1))
    task.close()


def test_first_index_history_task_initializes_registry_without_quote_dependency():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            task = TaskService(get_settings())  # explicitly mock test environment
            result = task.run(db, 'refresh_index_history', lookback_days=100)
            assert result['instruments'] == 3 and result['requested'] == 3
            from app.workspace.index_history import read
            assert read(db,get_settings(),'cn-csi300')['available'] is True
            task.close()
    finally:
        engine.dispose()
