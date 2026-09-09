"""Cache-only tasks never instantiate an upstream SDK or require credentials."""
from app.providers.base import CapabilityUnavailable, MarketProvider
from app.services.task_service import TaskService


class CacheOnlyProvider(MarketProvider):
    name = 'cache-only-no-network'

    def list_instruments(self, codes=None):
        raise CapabilityUnavailable('network_disabled_for_cache_only_task')

    def fetch_daily_bars(self, ts_code, start_date, end_date):
        raise CapabilityUnavailable('network_disabled_for_cache_only_task')

    def fetch_spot_quotes(self, codes):
        raise CapabilityUnavailable('network_disabled_for_cache_only_task')

    def fetch_news(self, since_hours=24):
        raise CapabilityUnavailable('network_disabled_for_cache_only_task')


class CacheOnlyTaskService(TaskService):
    def __init__(self, settings):
        # The worker already resolved and froze runtime configuration. Retain
        # its real provider label for historical qualification; never use Mock.
        super().__init__(settings, provider=CacheOnlyProvider())

    def _bind_runtime_provider(self, db):
        # In particular, a missing/expired Token cannot block reading old bars.
        return None
