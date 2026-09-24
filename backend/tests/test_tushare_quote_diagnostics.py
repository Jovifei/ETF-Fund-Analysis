from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.providers.base import CapabilityUnavailable
from app.providers.composite import CompositeProvider
from app.providers.tushare import TushareProvider


def test_tushare_permission_failure_keeps_safe_reason_for_provider_audit():
    def denied(**_params):
        raise CapabilityUnavailable('permission_or_credentials_denied')

    provider = TushareProvider(
        Settings(_env_file=None, app_env='test', tushare_token='fixture'),
        pro_client=SimpleNamespace(rt_etf_k=denied),
    )

    with pytest.raises(CapabilityUnavailable) as failure:
        provider.fetch_current_quotes(['512480.SH'])

    assert str(failure.value) == 'permission_or_credentials_denied'
    assert failure.value.safe_code == 'PERMISSION_OR_CREDENTIALS_DENIED'


def test_composite_audit_retains_only_allowlisted_permission_code():
    def denied(**_params):
        raise CapabilityUnavailable('permission_or_credentials_denied')

    provider = TushareProvider(
        Settings(_env_file=None, app_env='test', tushare_token='fixture'),
        pro_client=SimpleNamespace(rt_etf_k=denied),
    )
    composite = CompositeProvider([provider])

    with pytest.raises(CapabilityUnavailable):
        composite.fetch_spot_quotes(['512480.SH'])

    assert composite.last_trace[0].reason == 'PERMISSION_OR_CREDENTIALS_DENIED'
