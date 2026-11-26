"""Main-table levels/forecast surfacing for the strategy email renderer.

The per-row decision table (逐标的决策点) must show, for every row that has
the data: nearest support/resistance zones and the next-day forecast, so a
reader sees levels and expected move without jumping to the later sections.
Missing data must degrade to an empty/placeholder cell, never raise.
"""
import importlib.util
import json
import subprocess
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


@pytest.mark.parametrize("bad", [None, "false", 1, False])
@pytest.mark.parametrize("slot", ["11:40", "14:30", "14:45"])
def test_strategy_renderer_refuses_incomplete_or_untyped_gate(mod, monkeypatch, tmp_path, bad, slot):
    gates = {f"G{i}": {"pass": True} for i in range(1, 8)}
    if bad is None:
        del gates["G7"]
    else:
        gates["G7"]["pass"] = bad
    gate_path = tmp_path / "gates.json"
    gate_path.write_text(json.dumps(gates), encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(mod, "setup_matplotlib", lambda: pytest.fail("strategy must be rejected before rendering"))
    monkeypatch.setattr(sys, "argv", [
        "render_strategy_email.py", "--input", str(tmp_path / "unused.json"),
        "--date", "2026-11-26", "--slot", slot, "--gates", str(gate_path),
        "--out", str(out), "--attach-dir", str(tmp_path / "png"),
    ])

    mod.main()

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["variant"] == "not_ready"
    assert manifest["attachments"] == []


@pytest.mark.parametrize("gate_text", [None, "{", "{}"])
def test_close_renderer_refuses_unreadable_or_empty_gate_report(mod, monkeypatch, tmp_path, gate_text):
    gate_path = tmp_path / "gates.json"
    if gate_text is not None:
        gate_path.write_text(gate_text, encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", [
        "render_strategy_email.py", "--input", str(tmp_path / "unused.json"),
        "--date", "2026-11-26", "--slot", "收盘复核", "--gates", str(gate_path),
        "--out", str(out), "--attach-dir", str(tmp_path / "png"),
    ])

    mod.main()

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["variant"] == "not_ready"
    assert manifest["attachments"] == []


def test_extract_cli_preserves_structure_into_rendered_rows(mod, tmp_path):
    matching_date = '2026-11-26'
    structure = {
        'schema_version': 'structure_v1',
        'as_of': matching_date,
        'wyckoff_phase': 'accumulation',
        'dow_phase': 'uptrend',
        'atr_risk_bucket': 'high',
        'atr14': 0.3,
    }
    codes = ('510300.SH', '512480.SH', '159915.SZ', '512000.SH', '510500.SH')
    rows = [
        {**ROW, 'ts_code': code, 'support_resistance': {
            'snapshot_as_of_date': matching_date, 'atr14': 0.2,
        }}
        for code in codes
    ]
    rows[0]['structure_v1'] = structure
    bundle = tmp_path / 'bundle.json'
    bundle.write_text(json.dumps({
        'manifest': {'sequence': 42},
        'parts': {
            'overview': {'rows': rows},
            'details': {
                codes[0]: {'structure_v1': {**structure, 'atr_risk_bucket': 'low'}},
                codes[1]: {'structure_v1': structure},
            },
        },
    }), encoding='utf-8')
    sidecar = tmp_path / 'sidecar.json'
    sidecar.write_text(json.dumps([
        {**structure, 'ts_code': codes[2], 'as_of': '2026-11-25'},
        {**structure, 'ts_code': codes[4], 'as_of': None},
        {**structure, 'ts_code': codes[3]},
    ]), encoding='utf-8')

    result = subprocess.run(
        [sys.executable, '-I', '-B', '-X', 'utf8', str(_RENDERER.with_name('extract_slim.py')),
         str(bundle), '--structure-sidecar', str(sidecar)],
        check=True, capture_output=True,
    )
    slim = json.loads(result.stdout)
    assert slim['manifest']['sequence'] == 42
    for i in (0, 1, 3):
        assert slim['rows'][i]['structure_v1']['atr_risk_bucket'] == 'high'
        assert slim['rows'][i]['structure_v1']['atr14'] == 0.3
        assert slim['rows'][i]['atr14'] == 0.2
    for i in (2, 4):
        assert 'structure_v1' not in slim['rows'][i]
    assert slim['rows'][0]['structure_v1']['research_only'] is True
    html = mod.render_html(_ctx(mod, slim['rows']), [])
    assert all(label in html for label in ('吸筹', '上升趋势', '高波'))
