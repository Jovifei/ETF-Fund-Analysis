"""Price-only outlook guards; no Provider or language-model calls."""
import pandas as pd
import pytest
from app.core.config import get_settings
from app.workspace import research_outlook


def prices(count=270):
    days = pd.bdate_range('2024-01-02', periods=count)
    return [dict(date=d.date().isoformat(), open=2+i*.001, high=2.1+i*.001,
                 low=1.9+i*.001, close=2+i*.001, adjust='none', source='akshare:em:v101')
            for i, d in enumerate(days)]


def test_discontinuity_is_rejected_before_forecast(monkeypatch):
    rows = prices()
    for row in rows[180:]:
        for field in ('open','high','low','close'):
            row[field] /= 3
    monkeypatch.setattr(research_outlook, 'similarity_forecast', lambda *a, **k: pytest.fail('forecast must not run'))
    with pytest.raises(ValueError, match='unexplained_price_discontinuity'):
        research_outlook.compute(rows, get_settings())


def test_unknown_price_basis_is_rejected():
    with pytest.raises(ValueError, match='unknown_price_basis'):
        research_outlook.compute([dict(row, adjust='invented') for row in prices()], get_settings())


def test_unknown_volume_does_not_become_zero(monkeypatch):
    original = research_outlook.build_feature_frame
    def checked(frame, config):
        assert frame['volume'].isna().all()
        assert frame['amount'].isna().all()
        return original(frame, config)
    monkeypatch.setattr(research_outlook, 'build_feature_frame', checked)
    result = research_outlook.compute(prices(), get_settings())
    assert result['status'] == 'research' and result['config_hash']
    assert result['actionable'] is False
