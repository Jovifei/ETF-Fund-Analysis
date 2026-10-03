from fastapi.testclient import TestClient
from app.main import app

def test_detail_availability_api_contract(bootstrapped):
    with TestClient(app) as client:
        response = client.get('/api/workspace/instruments/510300.SH')
    assert response.status_code == 200
    payload = response.json()
    assert payload['availability_contract_version'] == 'detail-availability-v1'
    assert len(payload['availability']) == 9
    assert set(payload['availability']['forecasts']['by_horizon']) == {'1', '3', '5', '10'}
    assert payload['actionable'] is False
