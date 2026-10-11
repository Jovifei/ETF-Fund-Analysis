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


def test_provider_boundary_admits_akshare_and_tushare():
    # akshare is valid
    res_ak = validate_provider_admission(market_provider="akshare", profile="live")
    assert res_ak["admitted"] is True
    assert res_ak["adjustment_policy"] == "qfq"
    assert res_ak["actionable"] is False

    # tushare is valid
    res_tu = validate_provider_admission(market_provider="tushare", profile="live")
    assert res_tu["admitted"] is True
    assert res_tu["adjustment_policy"] == "qfq"
    assert res_tu["actionable"] is False


def test_provider_boundary_redacts_secrets_in_summary(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "secret_token_1234567890abcdef")
    res = validate_provider_admission(market_provider="tushare", profile="live")
    summary_str = str(res)
    assert "secret_token_1234567890abcdef" not in summary_str
