from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from app.models import DailyBar, Instrument


@pytest.fixture
def cli():
    path = Path(__file__).resolve().parents[2] / "scripts" / "fetch_us_etf_daily.py"
    spec = importlib.util.spec_from_file_location("fetch_us_etf_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fetch_us_etf_script_dry_run(cli, db_session):
    dates = pd.to_datetime(["2026-10-27", "2026-10-28", "2026-10-29"])
    mock_df = pd.DataFrame(
        {
            "Open": [580.0, 582.0, 585.0],
            "High": [583.0, 586.0, 587.0],
            "Low": [579.0, 581.0, 584.0],
            "Close": [582.0, 584.0, 586.0],
            "Volume": [40000000, 42000000, 39000000],
        },
        index=dates,
    )

    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.return_value = mock_df
        mock_ticker.return_value = mock_instance

        res = cli.sync_us_etfs(
            db_session,
            symbols=["SPY", "QQQ"],
            start_date=date(2026, 10, 27),
            end_date=date(2026, 10, 29),
            dry_run=True,
        )
        assert res["total"] == 2
        assert set(res["synced"]) == {"SPY", "QQQ"}
        assert res["failed"] == []
        assert res["bars_count"]["SPY"] == 3
        # In dry run mode, nothing should be committed to db
        inst = db_session.query(Instrument).filter(Instrument.ts_code == "SPY.US").first()
        assert inst is None


def test_fetch_us_etf_script_persists_to_db(cli, db_session):
    dates = pd.to_datetime(["2026-10-27", "2026-10-28"])
    mock_df = pd.DataFrame(
        {
            "Open": [580.0, 582.0],
            "High": [583.0, 586.0],
            "Low": [579.0, 581.0],
            "Close": [582.0, 584.0],
            "Volume": [40000000, 42000000],
        },
        index=dates,
    )

    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.return_value = mock_df
        mock_ticker.return_value = mock_instance

        res = cli.sync_us_etfs(
            db_session,
            symbols=["GLD"],
            start_date=date(2026, 10, 27),
            end_date=date(2026, 10, 28),
            dry_run=False,
        )
        assert res["synced"] == ["GLD"]
        inst = db_session.query(Instrument).filter(Instrument.ts_code == "GLD.US").first()
        assert inst is not None
        assert inst.symbol == "GLD"
        assert inst.metadata_json.get("market") == "US"

        bars = db_session.query(DailyBar).filter(DailyBar.instrument_id == inst.id).all()
        assert len(bars) == 2
        assert bars[0].close == 582.0
        assert bars[1].close == 584.0
