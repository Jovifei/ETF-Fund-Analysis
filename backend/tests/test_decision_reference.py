from app.utils.decision_reference import entry_exit_reference, theme_relative_ranks


def test_entry_exit_reference_uses_clustered_zones_not_a_single_tick() -> None:
    ref = entry_exit_reference(
        {
            "current_price": 2.05,
            "nearest_support": {"price": 2.0, "zone_low": 1.98, "zone_high": 2.02},
            "nearest_resistance": {"price": 2.2, "zone_low": 2.18, "zone_high": 2.22},
        }
    )
    assert ref["actionable"] is False
    assert ref["position"] == "inside_band"
    assert ref["support_zone"] == {"low": 1.98, "high": 2.02, "mid": 2.0}
    assert ref["resistance_zone"]["low"] == 2.18


def test_entry_exit_reference_stays_unknown_without_levels() -> None:
    ref = entry_exit_reference({}, current_price=1.5)
    assert ref["support_zone"] is None
    assert ref["position"] == "unknown"
    assert ref["actionable"] is False


def test_theme_relative_ranks_skip_missing_returns_and_do_not_invent_peers() -> None:
    ranked = theme_relative_ranks(
        [
            {"ts_code": "510300.SH", "theme_l1": "宽基", "return_5d": 0.02},
            {"ts_code": "510500.SH", "theme_l1": "宽基", "return_5d": 0.05},
            {"ts_code": "512480.SH", "theme_l1": "半导体", "return_5d": None},
            {"ts_code": "588000.SH", "theme_l1": "半导体", "return_5d": 0.01},
        ]
    )
    assert ranked["510500.SH"]["rank"] == 1
    assert ranked["510300.SH"]["rank"] == 2
    assert ranked["510500.SH"]["peer_count"] == 2
    assert "512480.SH" not in ranked
    assert ranked["588000.SH"]["peer_count"] == 1
    assert ranked["588000.SH"]["actionable"] is False
