"""F0 capability boundary receipt: no credentials, network or provider activation."""
from datetime import date
from types import SimpleNamespace
import pytest
from app.providers.base import CapabilityUnavailable
from app.providers.tushare import TushareProvider

@pytest.mark.parametrize('interval', ['5m', '15m'])
def test_f0_tushare_required_intervals_are_currently_disabled_before_transport(interval):
    provider = object.__new__(TushareProvider)
    def forbidden(**kwargs):
        raise AssertionError('probe must not contact upstream')
    provider.pro = SimpleNamespace(etf_mins=forbidden)
    with pytest.raises(CapabilityUnavailable, match='minute_interval_not_enabled'):
        provider.fetch_minute_bars('510300.SH', interval, date(2026, 9, 1), date(2026, 9, 25))
