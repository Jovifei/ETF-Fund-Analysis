from __future__ import annotations

from pathlib import Path

import pytest


def test_local_initializer_environment_is_real_provider_only_and_does_not_take_token(tmp_path: Path):
    from scripts.initialize_local_market_data import local_runtime_environment

    env = local_runtime_environment("sqlite:///" + (tmp_path / "market.sqlite3").as_posix(), "akshare")

    assert env["MARKET_PROVIDER"] == "akshare"
    assert env["ALLOW_MOCK_FALLBACK"] == "false"
    assert env["ANALYSIS_ENABLED"] == "false"
    assert env["LLM_ENABLED"] == "false"
    assert "TUSHARE_TOKEN" not in env


def test_local_initializer_rejects_mock_and_repository_database(tmp_path: Path):
    from scripts.initialize_local_market_data import validate_database_url, validate_provider

    with pytest.raises(ValueError, match="mock"):
        validate_provider("mock")
    with pytest.raises(ValueError, match="repository"):
        validate_database_url("sqlite:///./fund_decision.sqlite3", Path.cwd())
    assert validate_database_url("sqlite:///" + (tmp_path / "market.sqlite3").as_posix(), Path.cwd())


def test_onboard_sequence_is_limited_to_the_requested_instrument_data():
    from app.workspace.worker import task_sequence

    steps = [name for name, _ in task_sequence("onboard", {"codes": ["510300.SH"], "lookback_days": 420})]

    assert steps == [
        "refresh_bars",
        "refresh_indicators",
        "refresh_forecasts",
        "refresh_quotes",
        "refresh_signals",
        "refresh_decision_board",
    ]
    assert not {"refresh_sector_snapshots", "refresh_market_context", "refresh_news"}.intersection(steps)
