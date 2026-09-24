import pytest
from app.core.config import Settings
from app.models import Instrument, ProviderAudit, TaskRun
from app.providers.base import CapabilityUnavailable
from app.providers.composite import CompositeProvider
from app.services.task_service import TaskExecutionError, TaskService
from sqlalchemy import select


class UnsupportedQuotes:
    name = 'fixture-provider'

    def fetch_spot_quotes(self, codes):
        del codes
        raise CapabilityUnavailable('quotes_unavailable')


def test_failed_quote_task_persists_sanitized_provider_trace_after_rollback(db_session):
    code = 'R2TEST.SH'
    db_session.add(Instrument(ts_code=code, symbol='R2TEST', name='fixture', kind='ETF', enabled=True))
    db_session.flush()
    settings = Settings(_env_file=None, app_env='test', auth_enabled=False, market_provider='mock')
    provider = CompositeProvider([UnsupportedQuotes()])
    run_id = 'r2-failed-quotes-audit'

    with pytest.raises(TaskExecutionError):
        TaskService(settings, provider=provider).run(
            db_session, 'refresh_quotes', run_id=run_id, codes=[code],
        )

    task = db_session.scalar(select(TaskRun).where(TaskRun.run_id == run_id))
    audits = list(db_session.scalars(select(ProviderAudit).where(ProviderAudit.run_id == run_id)))
    assert task is not None and task.status == 'failed'
    assert task.error == 'app.providers.base.CapabilityUnavailable'
    assert [(item.provider, item.operation, item.status, item.reason) for item in audits] == [
        ('fixture-provider', 'fetch_spot_quotes', 'unsupported', 'CapabilityUnavailable'),
    ]
    assert 'quotes_unavailable' not in task.error
