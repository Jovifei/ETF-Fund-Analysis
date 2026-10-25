from __future__ import annotations

import json
from pathlib import Path
import pytest


def test_us_etf_empirical_metrics_validity():
    worktree_root = Path(__file__).resolve().parents[2]
    json_path = worktree_root / "research" / "calc_decision" / "out" / "us_etf_empirical_metrics.json"

    assert json_path.exists(), f"Missing US ETF output: {json_path}"
    data = json.loads(json_path.read_text(encoding="utf-8"))

    assert "513100.SH" in data
    nasdaq = data["513100.SH"]
    assert nasdaq["bars"] > 2000
    assert "tsmom_12m" in nasdaq["factors"]
    assert "turtle_20_10" in nasdaq["factors"]

    # Donchian channel on Nasdaq 100 ETF should exhibit positive Sharpe and expectancy
    turtle = nasdaq["factors"]["turtle_20_10"]
    assert turtle["net_sharpe"] > 0.50
    assert turtle["trade_stats"]["net_win_rate"] > 50.0
    assert turtle["trade_stats"]["net_expectancy_bps"] > 100.0

    # TSMOM 12m on Nasdaq 100 ETF should also show positive expectancy
    tsmom = nasdaq["factors"]["tsmom_12m"]
    assert tsmom["net_sharpe"] > 0.20
    assert tsmom["trade_stats"]["net_expectancy_bps"] > 500.0
