"""Simplified Chan structures are drawable research geometry, not CZSC."""
from datetime import date, timedelta

from app.utils.chan_structure import build_chan_structure


def _zigzag():
    centers = [
        10, 12, 14, 16, 18, 20, 22,
        20, 18, 16, 14, 12, 10,
        12, 14, 16, 18, 20, 22, 24,
        22, 20, 18, 16, 14, 12,
        14, 16, 18, 20, 22, 24, 26,
        24, 22, 20, 18,
    ]
    start = date(2026, 1, 1)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "open": center,
            "high": center + 0.4,
            "low": center - 0.4,
            "close": center,
        }
        for index, center in enumerate(centers)
    ]


def test_short_history_is_explicitly_unavailable():
    result = build_chan_structure([{"date": "2026-01-01", "high": 2, "low": 1}])
    assert result["available"] is False
    assert result["actionable"] is False
    assert result["qualified"] is False
    assert result["bi"] == []
    assert result["segments"] == []
    assert result["zhongshu"] == []
    assert "简化" in result["disclaimer"]


def test_zigzag_draws_alternating_bi_one_segment_and_a_pivot_zone():
    bars = _zigzag()
    result = build_chan_structure(bars)

    assert result["available"] is True
    assert result["actionable"] is False
    assert result["qualified"] is False
    assert result["algorithm"] == "chan-structure-simplified-v1"
    assert "CZSC" in result["disclaimer"]

    strokes = result["bi"]
    assert len(strokes) == 4
    assert [item["direction"] for item in strokes] == ["down", "up", "down", "up"]
    assert strokes[0]["start_price"] == 22.4
    assert strokes[0]["end_price"] == 9.6
    assert strokes[0]["start_date"] == bars[6]["date"]
    assert strokes[0]["end_date"] == bars[12]["date"]
    assert all(strokes[index]["end_date"] == strokes[index + 1]["start_date"] for index in range(3))

    assert len(result["segments"]) == 1
    assert result["segments"][0]["direction"] == "down"
    assert result["segments"][0]["bi_count"] == 3

    zones = result["zhongshu"]
    assert len(zones) == 1
    assert zones[0]["source"] == "bi"
    assert zones[0]["zd"] == 11.6
    assert zones[0]["zg"] == 22.4
    assert zones[0]["zd"] < zones[0]["zg"]
