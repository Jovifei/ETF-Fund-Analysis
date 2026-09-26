"""New workspace acceptance contracts, written before the implementation.

These tests intentionally start red on the v0.8 baseline. No external providers,
model credentials, or live account data are used.
"""
from datetime import date, timedelta

import pandas as pd
import pytest
from app.core.config import get_settings
from app.main import app
from app.utils.indicators import calculate_indicators
from fastapi.testclient import TestClient
from pydantic import ValidationError


def test_workspace_search_is_available_bounded_and_read_only(bootstrapped):
    with TestClient(app) as client:
        response = client.get('/api/search/instruments', params={'q': 'ETF', 'limit': 5})
        assert response.status_code == 200
        payload = response.json()
        assert len(payload['items']) <= 5
        assert payload['scope'] == 'synced_catalog'
        assert payload['provider_called'] is False
        assert all(row['kind'] in ('ETF', 'LOF') for row in payload['items'])
        assert client.get('/api/search/instruments?q=ETF&limit=101').status_code == 422


def test_chart_uses_existing_python_indicator_formulas():
    from app.workspace.chart import build_indicator_series
    rows = [
        {'date': (date(2025, 1, 1) + timedelta(days=i)).isoformat(),
         'open': 3 + i / 100, 'high': 3.06 + i / 100,
         'low': 2.94 + i / 100, 'close': 3 + i / 100 + (i % 7 - 3) / 200,
         'volume': 1000 + i * 7, 'amount': 3000 + i * 21}
        for i in range(180)
    ]
    config = get_settings().load_strategy()['indicator']
    actual = build_indicator_series(rows, config)
    expected = calculate_indicators(pd.DataFrame(rows).rename(columns={'date': 'trade_date'}), config)
    assert len(actual) == len(rows)
    for i in (35, 89, 179):
        for field in ('ma20', 'macd_dif', 'macd_dea', 'macd_hist', 'kdj_k', 'kdj_d', 'kdj_j', 'rsi14'):
            assert actual[i]['indicators'][field] == pytest.approx(float(expected.frame.iloc[i][field]), abs=1e-8)
    assert actual[0]['indicators']['ma20'] is None


def test_model_result_has_no_action_or_position_authority():
    from app.workspace.protocol import ResearchResult
    payload = {
        'schema_version': 'etf-research-result-v1',
        'job_id': 'a' * 32, 'input_hash': 'b' * 64,
        'producer': 'manual', 'producer_version': 'test', 'model': 'none',
        'summary': '测试研究说明', 'facts': [], 'inferences': [],
        'risks': [], 'conflicts': [], 'limitations': ['未做实盘验证'],
        'evidence_ids': [], 'report_markdown': '仅供研究',
    }
    assert ResearchResult.model_validate(payload).summary == '测试研究说明'
    with pytest.raises(ValidationError):
        ResearchResult.model_validate({**payload, 'current_action': '可加仓'})
    with pytest.raises(ValidationError):
        ResearchResult.model_validate({**payload, 'target_weight': 1.0})


def test_workspace_unknown_api_is_not_a_successful_spa_page():
    with TestClient(app) as client:
        assert client.get('/api/workspace/does-not-exist').status_code == 404
        assert client.get('/workspace-assets/does-not-exist.js').status_code == 404


def test_detail_and_chart_errors_have_stable_reason_codes(bootstrapped):
    with TestClient(app) as client:
        missing = client.get('/api/workspace/instruments/999999.SH')
        invalid_period = client.get('/api/workspace/instruments/510300.SH/chart?interval=2h')
        pinned = client.get('/api/workspace/instruments/510300.SH/chart', params={
            'interval': '1d', 'as_of': '2026-09-23T10:00:00+08:00',
        })
        future = client.get('/api/workspace/instruments/510300.SH/chart', params={
            'interval': '1d', 'as_of': '2030-01-01T10:00:00+08:00',
        })
    assert missing.status_code == 404
    assert missing.json()['detail'] == 'instrument_not_in_catalog'
    assert invalid_period.status_code == 422
    assert invalid_period.json()['detail'] == 'unsupported_chart_interval'
    assert pinned.status_code == 200
    assert pinned.json()['as_of'] == '2026-09-23T10:00:00+08:00'
    assert future.status_code == 422
    assert future.json()['detail'] == 'as_of_in_future'
