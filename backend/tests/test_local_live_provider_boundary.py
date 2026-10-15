from pathlib import Path
import pytest
from app.workspace.local_compute import (
    local_settings,
    validate_provider_admission,
)


def test_provider_boundary_rejects_mock_in_live(tmp_path):
    root = tmp_path / "etf_root"
    root.mkdir()
    (root / ".local-live").touch()
    db_file = root / "research.sqlite3"
    db_file.touch()

    # Rejects mock provider in live profile
    with pytest.raises(ValueError, match="mock provider not permitted"):
        validate_provider_admission(market_provider="mock", profile="live")


def test_provider_name_alone_is_not_permission_or_quality_evidence():
    res_ak = validate_provider_admission(market_provider="akshare", profile="live")
    assert res_ak["admitted"] is False
    assert res_ak["source_timestamp_quality"] == "UNKNOWN"
    assert res_ak["actionable"] is False

    res_tu = validate_provider_admission(market_provider="tushare", profile="live")
    assert res_tu["admitted"] is False
    assert res_tu["license_status"] == "UNKNOWN"
    assert res_tu["actionable"] is False


def test_provider_boundary_redacts_secrets_in_summary(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "secret_token_1234567890abcdef")
    res = validate_provider_admission(market_provider="tushare", profile="live")
    summary_str = str(res)
    assert "secret_token_1234567890abcdef" not in summary_str
