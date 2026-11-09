"""Main-table structure columns contract for the static decision board.

The three structure columns （威科夫结构 / 道氏趋势 / ATR 波动风险） must sit in the
main table after the existing technical indicators, render real structure_v1
values when a bundle row carries them, and render the missing marker when a
historical bundle has none — never a fabricated neutral/low-risk label.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_structure_columns_headers_and_rendering() -> None:
    static = Path(__file__).parents[1] / "app" / "static" / "app.js"
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const node = () => ({
  textContent: '', value: '', disabled: false, className: '',
  classList: {add(){}, remove(){}, toggle(){}},
  setAttribute(){}, focus(){}, getBoundingClientRect(){return {width:800,height:400}},
});
const context = {
  console, setTimeout, clearTimeout, setInterval, clearInterval, URL,
  Headers, AbortController, FormData, TextEncoder, TextDecoder,
  document: {querySelector:()=>node(), querySelectorAll:()=>[], addEventListener(){}, activeElement:node()},
  window: {devicePixelRatio:1, location:{origin:'http://test.local'}, addEventListener(){}, removeEventListener(){}},
  localStorage: {getItem(){return 'unit-token'}, setItem(){}, removeItem(){}},
  confirm:()=>true,
  fetch: async () => ({ok:true, status:200, statusText:'OK', headers:{get:()=> 'application/json'}, json:async()=>({})}),
};
context.globalThis = context;
vm.runInNewContext(source + '\nthis.__test={DECISION_COLUMNS, decisionRowHtml};', context, {filename: process.argv[1]});
const t = context.__test;
const labels = Object.fromEntries(t.DECISION_COLUMNS);
const order = t.DECISION_COLUMNS.map(([key]) => key);
const withStructure = {
  ts_code: '510300.SH', name: '300ETF', grade: '观望', grade_reason: '健康',
  returns: {}, forecasts: {'1': {q50: 0.001}},
  structure_v1: {schema_version: 'structure_v1', ts_code: '510300.SH', as_of: '2026-11-06',
    wyckoff_phase: 'markup', dow_phase: 'uptrend',
    atr14: 0.096, atr_pct: 0.0221, atr_risk_bucket: 'high', research_only: true},
};
const withoutStructure = {
  ts_code: '510300.SH', name: '300ETF', grade: '观望', grade_reason: '健康',
  returns: {}, forecasts: {'1': {q50: 0.001}},
};
process.stdout.write(JSON.stringify({
  labels, order,
  withHtml: t.decisionRowHtml(withStructure, 0, 1),
  withoutHtml: t.decisionRowHtml(withoutStructure, 0, 1),
}));
"""
    result = subprocess.run(
        ["node", "-e", harness, str(static)],
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    labels, order = payload["labels"], payload["order"]
    # Exact audit-specified column titles, not bare abbreviations.
    assert labels["wyckoff"] == "威科夫结构"
    assert labels["dow"] == "道氏趋势"
    assert labels["atr_bucket"] == "ATR 波动风险"
    # After the existing technical indicators / forecast, before the grade.
    assert order.index("chan") < order.index("wyckoff") < order.index("grade")
    assert order.index("forecast") < order.index("wyckoff")
    assert order.index("wyckoff") < order.index("dow") < order.index("atr_bucket")
    with_html = payload["withHtml"]
    assert "拉升" in with_html and "上升趋势" in with_html and "高波" in with_html
    # ATR cell exposes the underlying values (ATR14 and ATR% as a percent).
    assert "2.21%" in with_html
    without_html = payload["withoutHtml"]
    assert "拉升" not in without_html and "高波" not in without_html
    assert "—" in without_html
