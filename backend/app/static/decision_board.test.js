'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appPath = path.join(__dirname, 'app.js');
const htmlPath = path.join(__dirname, 'index.html');
const cssPath = path.join(__dirname, 'app.css');

function loadBoardUi() {
  const source = fs.readFileSync(appPath, 'utf8');
  const node = () => ({
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener() {}, append() {}, closest() { return null; }, focus() {},
    getBoundingClientRect() { return { width: 1200, height: 500 }; },
    setAttribute() {}, style: {}, textContent: '', value: '',
  });
  const context = {
    AbortController, Headers, URL, FormData, TextDecoder, TextEncoder,
    clearInterval, clearTimeout, console, setInterval, setTimeout,
    localStorage: { getItem() { return ''; }, removeItem() {}, setItem() {} },
    document: { addEventListener() {}, activeElement: node(), querySelector() { return node(); }, querySelectorAll() { return []; } },
    window: { addEventListener() {}, location: { origin: 'http://test.local', pathname: '/' } },
  };
  context.globalThis = context;
  vm.runInNewContext(source, context, { filename: appPath });
  return { ui: context.DecisionBoardUi, context };
}

const rows = [
  { ts_code: '510300.SH', name: '沪深300', grade: '可加仓', returns: { today: 0.0009 }, sort_keys: { rank: 2, today: 0.0009 } },
  { ts_code: '512480.SH', name: '半导体', grade: '可加仓', returns: { today: -0.0007 }, sort_keys: { rank: 2, today: -0.0007 } },
  { ts_code: '513100.SH', name: '纳指', grade: '观望', returns: { today: 0 }, sort_keys: { rank: 10, today: null } },
  { ts_code: '159915.SZ', name: '创业板', grade: '减仓', returns: { today: 0.012 }, sort_keys: { rank: null, today: null } },
];

test('decimal ratios format once and never infer percentages from magnitude', () => {
  const {ui} = loadBoardUi();
  assert.equal(ui.percent(0.0009), '+0.09%');
  assert.equal(ui.percent(-0.0007), '-0.07%');
  assert.equal(ui.percent(0), '+0.00%');
  assert.equal(ui.percent(0.012), '+1.20%');
});

test('global and grouped views retain unique rows with missing-last stable code ties', () => {
  const {ui} = loadBoardUi();
  const global = ui.visibleRows({ rows, groups: {} }, { mode: 'global', filter: '', sort: { key: 'rank', direction: 'asc' } });
  assert.equal(JSON.stringify(global.map(row => row.ts_code)), JSON.stringify(['510300.SH', '512480.SH', '513100.SH', '159915.SZ']));
  const groups = ui.groupedRows({ rows, groups: { '可加仓': rows.slice(0, 2), '观望': [rows[2]], '减仓': [rows[3]] } }, { filter: '', sort: { key: 'rank', direction: 'asc' } });
  assert.equal(JSON.stringify([...groups.values()].flat().map(row => row.ts_code)), JSON.stringify(global.map(row => row.ts_code)));
  assert.equal(new Set([...groups.values()].flat().map(row => row.ts_code)).size, rows.length);
});

test('sort headers cycle ascending, descending, then supplied default', () => {
  const {ui} = loadBoardUi();
  assert.equal(JSON.stringify(ui.nextSort({ key: 'rank', direction: 'asc' }, 'rank')), JSON.stringify({ key: 'rank', direction: 'desc' }));
  assert.equal(JSON.stringify(ui.nextSort({ key: 'rank', direction: 'desc' }, 'rank')), JSON.stringify({ key: null, direction: null }));
  assert.equal(JSON.stringify(ui.nextSort({ key: null, direction: null }, 'today')), JSON.stringify({ key: 'today', direction: 'asc' }));
});

test('row HTML is escaped, marked by health/risk and non-actionable bad data', () => {
  const {ui} = loadBoardUi();
  const html = ui.rowHtml({ ...rows[0], name: '<img src=x onerror=alert(1)>', data_status: 'mock', source_status: 'degraded', grade_reason: '<script>' }, 1);
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /decision-row--blocked/);
  assert.match(html, /health-badge--degraded/);
  assert.match(html, /risk-badge/);
});

test('all approved metric headers are sortable and cells retain compact indicator detail', () => {
  const {ui} = loadBoardUi();
  const header = ui.headerHtml({ key: 'volume', direction: 'asc' });
  for (const key of ['today', 'previous_day_delta', 'week_1', 'volume', 'ma', 'macd', 'kdj', 'td', 'rsi', 'chan', 'forecast', 'grade']) {
    assert.match(header, new RegExp(`data-decision-sort="${key}"`));
  }
  const html = ui.rowHtml({
    ...rows[0],
    provisional: { status: 'computed_unverified_research_only' },
    volume: { label: '放量', ratio: 1.42 },
    ma: { label: '多头排列', arrows: [{ window: 'M5', dir: 'up' }, { window: 'M20', dir: 'down' }], values_text: 'MA5=3.12 MA20=3.00' },
    macd: { label: '金叉', dif: 0.1234, dea: 0.0111 },
    kdj: { j: 45.5, label: '健康', note: '趋势可观察', k: 42.1, d: 39.2 },
    td: { label: 'TD7', kind: 'buy' },
    rsi: { value: 58.3, label: '正常偏强' },
    chan: { label: '缠论近似', status: 'approximation', zone: { low: 2.9, high: 3.1 } },
    sector: { label: '半导体ETF池', up: 3, down: 1, flat: 2, coverage_count: 6 },
  }, 1);
  for (const marker of ['量比 1.42', '临时观测', '多头排列', 'M5↑', 'M20↓', 'DIF 0.1234', 'J 45.5', 'K/D 42.1/39.2', 'TD9 多头 · 7', 'RSI 58.3', '区间 2.9000–3.1000', '3↑ 1↓ 2平 · 覆盖 6']) assert.match(html, new RegExp(marker));
});

test('data anomaly is an explicit sixth group and grouped tables never duplicate IDs', () => {
  const {ui} = loadBoardUi();
  const anomaly = { ts_code: '159001.SZ', name: '异常ETF', grade: '数据异常', sort_keys: { grade_health: 99 } };
  const grouped = ui.groupedRows({ rows: [...rows, anomaly], groups: { '数据异常': [anomaly] } }, { filter: '', sort: { key: 'grade', direction: 'asc' } });
  assert.equal(JSON.stringify([...grouped.keys()]), JSON.stringify(['可加仓', '可入场', '可试探', '观望', '减仓', '数据异常']));
  assert.equal(grouped.get('数据异常').map(row => row.ts_code).join(','), '159001.SZ');
  const left = ui.tableHtml([rows[0]], { horizon: 1, sort: {} }, '', 'decisionBoardTable-0');
  const right = ui.tableHtml([anomaly], { horizon: 1, sort: {} }, '', 'decisionBoardTable-5');
  assert.match(left, /id="decisionBoardTable-0"/);
  assert.match(right, /id="decisionBoardTable-5"/);
  assert.notEqual(left.match(/id="[^"]+"/)[0], right.match(/id="[^"]+"/)[0]);
});

test('manual refresh queues the dedicated snapshot task instead of reading the old board', async () => {
  const {ui, context} = loadBoardUi();
  ui.state.token = 'unit-token';
  context.setTimeout = () => 0;
  const calls = [];
  context.fetch = async (path, options = {}) => {
    calls.push({path, method: options.method, body: options.body});
    return {ok: true, status: 202, statusText: 'Accepted', headers: {get: () => 'application/json'}, json: async () => ({task_id: 'refresh-1', status: 'queued'})};
  };
  await ui.requestRefresh();
  assert.equal(JSON.stringify(calls), JSON.stringify([{path: '/api/decision-board/refresh', method: 'POST', body: '{}'}]));
  assert.equal(ui.state.decisionRefreshTask.taskId, 'refresh-1');
  assert.equal(ui.state.decisionRefreshTask.status, 'queued');
});

test('auth-disabled reads bootstrap and decision snapshots without a localStorage token, while 401 leaves data empty', async () => {
  const {ui, context} = loadBoardUi();
  context.setInterval = () => 0;
  context.setTimeout = () => 0;
  const calls = [];
  const response = (payload, status = 200) => ({ok: status < 400, status, statusText: status === 401 ? 'Unauthorized' : 'OK', headers: {get: () => 'application/json'}, json: async () => payload});
  context.fetch = async (path, options = {}) => {
    calls.push({path, authorization: options.headers.get('Authorization')});
    if (path === '/api/bootstrap') return response({demo:false,summary:{instrument_count:0,live_quote_count:0,state_counts:{},market_width:{up:0,down:0,unchanged:0},provider:'test'},instruments:[],market_context:[],holdings:[],news:[],tasks:[],provider_health:[]});
    if (path === '/api/reports') return response([]);
    if (path === '/api/decision-board?horizon=1') return response({snapshot_id:'public-snapshot',groups:{},rows:[],counts:{},horizons:[1,3,5,10],selected_horizon:1});
    return response({});
  };
  await ui.loadBootstrap();
  await ui.loadDecisionBoard();
  assert.equal(ui.state.data.summary.provider, 'test');
  assert.equal(ui.state.decisionBoard.snapshot_id, 'public-snapshot');
  assert.ok(calls.some(call => call.path === '/api/bootstrap'));
  assert.ok(calls.every(call => call.authorization === null));

  const protectedRun = loadBoardUi();
  protectedRun.context.setTimeout = () => 0;
  protectedRun.context.fetch = async () => response({detail:'token required'}, 401);
  await protectedRun.ui.loadBootstrap();
  assert.equal(protectedRun.ui.state.data, null);
});

test('snapshot detail exposes persisted candles, forecast boundary, levels, indicators and escapes hostile text', () => {
  const {ui} = loadBoardUi();
  const html = ui.detailHtml({
    snapshot_id: 'snap-1', ts_code: '510300.SH', name: '<img src=x>',
    history: [{ date: '2026-09-01', open: 3, high: 3.2, low: 2.9, close: 3.1, volume: 100 }],
    forecast_scenario: Array.from({ length: 10 }, (_, index) => ({ day: index + 1, close: 3.1 + index / 100, is_forecast: true, not_actual: true })),
    forecast: { expected_return: 0.01, q10: -0.02, q50: 0.01, q90: 0.03, p_up: 0.6, calibration_status: 'not_calibrated' },
    support_resistance: { nearest_support: { price: 2.9 }, nearest_resistance: { price: 3.2 }, chan_zone_approx: { lower: 2.95, upper: 3.15 } },
    chan: { label: '缠论近似', detail: '<script>' }, indicator: { version: 'indicator-v1', as_of_date: '2026-09-01' },
    quote: { source: 'saved', source_time: '2026-09-01T14:30:00', timestamp_verified: false }, provisional: { status: 'computed_unverified_research_only' },
  });
  for (const marker of ['历史K线 1 根', '预测情景 10 根 · 非实际结果', '支撑 2.9000', '压力 3.2000', 'q10', 'indicator-v1', '临时观测']) assert.match(html, new RegExp(marker));
  assert.doesNotMatch(html, /<script>|<img/);
});

test('snapshot detail renders all forecast horizons while emphasizing the selected horizon', () => {
  const {ui} = loadBoardUi();
  const html = ui.detailHtml({
    snapshot_id: 'snap-forecast-grid', ts_code: '510300.SH', name: '沪深300', selected_horizon: 5,
    forecasts: {
      1: { horizon: 1, expected_return: 0.001, p_up: 0.51, q10: -0.01, q50: 0.001, q90: 0.02, confidence: 31, calibration_status: 'not_calibrated' },
      3: { horizon: 3, expected_return: 0.003, p_up: 0.53, q10: -0.02, q50: 0.003, q90: 0.03, confidence: 32, calibration_status: 'not_calibrated' },
      5: { horizon: 5, expected_return: 0.005, p_up: 0.55, q10: -0.03, q50: 0.005, q90: 0.04, confidence: 33, calibration_status: 'not_calibrated' },
      10: { horizon: 10, expected_return: 0.01, p_up: 0.6, q10: -0.04, q50: 0.01, q90: 0.06, confidence: 34, calibration_status: 'not_calibrated' },
    },
  });
  for (const marker of ['1 日预测', '3 日预测', '5 日预测', '10 日预测', '期望收益', '上涨概率', 'q10/q50/q90', '置信度', 'not_calibrated', '研究情景 · 非实际结果']) assert.match(html, new RegExp(marker));
  assert.match(html, /detail-forecast-card--selected[\s\S]*5 日预测/);
  assert.equal((html.match(/<article class="detail-forecast-card(?: |")/g) || []).length, 4);
  assert.doesNotMatch(html, /准确率/);
});

test('wide table contract supplies sticky edges and horizontal behavior at 1440, 1024, and 390', () => {
  const html = fs.readFileSync(htmlPath, 'utf8');
  const script = fs.readFileSync(appPath, 'utf8');
  const css = fs.readFileSync(cssPath, 'utf8');
  for (const marker of ['decisionBoard', 'decisionModeGlobal', 'decisionSearch', 'decisionHorizon']) assert.match(html, new RegExp(marker));
  for (const marker of ['marketContextSection', 'marketContextCards', '市场环境（观察）']) assert.ok(html.includes(marker), `${marker} missing`);
  assert.doesNotMatch(html, /data-tab="grade"/);
  assert.doesNotMatch(html, /id="view-grade"/);
  assert.match(script, /decisionBoardTable/);
  assert.match(script, /renderMarketContext\(\)/);
  assert.match(script, /state\.activeTab === 'dashboard' && state\.decisionBoard/);
  assert.match(script, /chartCanvas.*classList\.add\('hidden'\)/);
  assert.match(script, /snapshot_id=/);
  assert.match(script, /api\('\/api\/decision-board\/refresh'/);
  assert.match(script, /drawDecisionSnapshotChart/);
  for (const marker of ['decision-table-wrap', 'decision-sticky-first', 'decision-sticky-last', '@media (max-width:1024px)', '@media (max-width:390px)']) assert.ok(css.includes(marker), `${marker} missing`);
});
