"""Chart payload tags research layers and can draw a box without a saved snapshot."""
from datetime import date, timedelta

from app.utils.prior_range import prior_high_low_range
from app.workspace import candle_periods
from app.workspace.candle_periods import chart_studies, transform_chart


def _bars(count=8):
    start = date(2026, 1, 1)
    rows = []
    for index in range(count):
        close = 10 + index
        rows.append({
            "date": (start + timedelta(days=index)).isoformat(),
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 100,
            "amount": 1000,
            "source": "fixture",
            "is_partial": False,
        })
    return rows


def test_prior_high_low_uses_the_recent_window_and_stays_non_actionable():
    bars = _bars(8)
    result = prior_high_low_range(bars, window=5)

    assert result["persisted"] is False
    assert result["qualified"] is False
    assert result["actionable"] is False
    assert result["kind"] == "prior_high_low"
    assert result["window"] == 5
    assert result["upper"] == 18
    assert result["lower"] == 12
    assert result["origin_at"] == bars[3]["date"]
    assert result["valid_until"] == bars[7]["date"]
    assert prior_high_low_range(bars[:4]) is None


def test_chart_studies_group_methods_and_attach_chan_geometry(monkeypatch):
    def fake(_frame):
        return {
            "levels": [
                {"methods": ["MA20", "布林下轨"], "category": "mixed_reference", "price": 1},
                {"methods": ["MACD确认拐点", "确认分形低点"], "category": "price_structure", "price": 2},
                {"methods": ["Fibonacci 0.618"], "price": 3},
            ],
            "trend_lines": [],
        }

    monkeypatch.setattr(candle_periods, "build_support_resistance", fake)
    result = chart_studies(_bars(), {}, "1d")

    assert result["levels"][0]["groups"] == ["MA", "BOLL"]
    assert result["levels"][1]["groups"] == ["MACD", "PIVOT"]
    assert result["levels"][2]["groups"] == ["FIB"]
    assert result["chan_structure"]["actionable"] is False
    assert result["chan_structure"]["qualified"] is False
    assert isinstance(result["chan_structure"]["bi"], list)


def test_missing_snapshot_attaches_live_prior_range_without_replacing_a_saved_box():
    bars = _bars(8)
    missing = {"qualified": False, "reason": "snapshot_missing_requires_task", "boxes": [], "actionable": False, "interval": "1d"}
    saved = {"qualified": True, "reason": None, "boxes": [{"structure_id": "saved"}], "actionable": False, "interval": "1d"}
    hidden = {"qualified": False, "reason": "price_basis_mismatch", "boxes": [], "actionable": False, "interval": "1d"}

    live = transform_chart({"bars": bars, "research_bars": bars, "raw_overlay_allowed": True, "price_structures": missing, "research_price_structures": dict(missing)}, "1d", {}, 500)
    kept = transform_chart({"bars": bars, "research_bars": bars, "raw_overlay_allowed": True, "price_structures": saved, "research_price_structures": dict(saved)}, "1d", {}, 500)
    suppressed = transform_chart({"bars": bars, "research_bars": bars, "raw_overlay_allowed": True, "price_structures": hidden, "research_price_structures": dict(hidden)}, "1d", {}, 500)

    prior = live["price_structures"]["live_prior_range"]
    assert prior["upper"] == 18
    assert prior["lower"] == 9
    assert prior["actionable"] is False
    assert live["price_structures"]["reason"] == "snapshot_missing_requires_task"
    assert live["actionable"] is False
    assert "chan_structure" in live["studies"]
    assert "live_prior_range" not in kept["price_structures"]
    assert kept["price_structures"]["boxes"][0]["structure_id"] == "saved"
    assert "live_prior_range" not in suppressed["price_structures"]
    weekly = transform_chart({"bars": bars, "research_bars": bars, "raw_overlay_allowed": True, "price_structures": missing, "research_price_structures": dict(missing)}, "1w", {}, 500)
    assert weekly["price_structures"]["reason"] == "interval_unsupported"
