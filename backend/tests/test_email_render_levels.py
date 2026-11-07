"""Main-table levels/forecast surfacing for the strategy email renderer.

The per-row decision table (逐标的决策点) must show, for every row that has
the data: nearest support/resistance zones and the next-day forecast, so a
reader sees levels and expected move without jumping to the later sections.
Missing data must degrade to an empty/placeholder cell, never raise.
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

_RENDERER = (
    Path(__file__).resolve().parents[2]
    / "research" / "etf_structure_features" / "email_render" / "render_strategy_email.py"
)


@pytest.fixture(scope="module")
def mod():
    # market_summary is a workstation-only sibling module (the Bot host
    # provides it at send time); stub it so the renderer imports standalone.
    stub = types.ModuleType("market_summary")
    stub.format_market_summary_text = lambda ms: []
    stub.format_market_summary_html = lambda *a, **k: ""
    stub.build_market_summary = lambda *a, **k: None
    sys.modules.setdefault("market_summary", stub)
    spec = importlib.util.spec_from_file_location("render_strategy_email", _RENDERER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROW = {
    "ts_code": "510300.SH", "name": "沪深300ETF", "grade": "观望",
    "grade_reason": "测试理由", "price": 3.95, "return_1d": 0.005, "return_5d": -0.01,
    "theme_l1": "宽基", "theme_l2": "沪深300",
    "nearest_support": {"zone_low": 3.80, "zone_high": 3.85, "distance_pct": -2.1,
                        "methods": ["fractal"]},
    "nearest_resistance": {"zone_low": 4.08, "zone_high": 4.12, "distance_pct": 3.8,
                           "methods": ["box"]},
    "fc": {"1": {"expected_return": 0.012, "p_up": 0.6, "as_of_date": "2026-11-06"}},
}


def _ctx(mod, rows):
    data = {"rows": rows, "manifest": {}, "overview": {}, "sector_timing": None}
    return mod.build_context(data, "14:45", "2026-11-07", None, "", None, "bundle", "1")


def test_levels_cell_parts_from_near_zones(mod):
    parts = mod.levels_cell_parts(ROW)
    assert [p[0] for p in parts] == ["支", "压"]
    assert "3.8" in parts[0][1] and "%" in (parts[0][2] or "")
    assert "4.1" in parts[1][1] and "%" in (parts[1][2] or "")


def test_levels_cell_parts_zone_dict_fallback(mod):
    row = {"support_zone": {"low": 3.70, "high": 3.75}}
    parts = mod.levels_cell_parts(row)
    assert len(parts) == 1 and parts[0][0] == "支" and "3.7" in parts[0][1]


def test_levels_cell_parts_empty(mod):
    assert mod.levels_cell_parts({}) == []
    assert mod.levels_cell_parts({"nearest_support": None, "support_zone": None}) == []


def test_next_day_forecast_fc_and_legacy(mod):
    assert mod.next_day_forecast(ROW)["expected_return"] == 0.012
    legacy = {"fc1": {"expected_return": -0.004, "p_up": 0.4}}
    assert mod.next_day_forecast(legacy)["expected_return"] == -0.004
    assert mod.next_day_forecast({}) is None


def test_render_html_main_table_surfaces_levels_and_forecast(mod):
    html = mod.render_html(_ctx(mod, [ROW]), [])
    assert "支撑/压力" in html
    assert "明日预期" in html
    assert 'colspan="9"' in html
    assert "3.8" in html and "4.1" in html


def test_render_html_missing_data_still_renders(mod):
    bare = {"ts_code": "159915.SZ", "name": "创业板ETF", "grade": "观望", "price": 2.1}
    html = mod.render_html(_ctx(mod, [bare]), [])
    assert "创业板ETF" in html


def test_render_text_row_surfaces_levels_and_forecast(mod):
    text = mod.render_text(_ctx(mod, [ROW]), {})
    assert "明日预期" in text
    assert "3.8" in text
