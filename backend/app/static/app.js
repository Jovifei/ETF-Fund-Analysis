'use strict';

const qs = (selector, root = document) => root.querySelector(selector);
const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {
  sessionActive: false,
  auth: {identifier: null, role: null},
  adminUsers: [],
  data: null,
  settings: null,
  reports: [],
  signalCenter: null,
  signalGrade: null,
  boards: null,
  boardKind: 'industry',
  signalFrontTab: 'opportunity',
  signalCenterLoading: false,
  coefficientTimer: null,
  eventAbort: null,
  eventRetry: null,
  refreshTimer: null,
  activeTab: 'dashboard',
  modalReturnFocus: null,
  detailCode: null,
  detailRequestController: null,
  detailRequestToken: 0,
  resizeTimer: null,
  holdingImport: null,
  importGeneration: 0,
  importControllers: new Set(),
  pendingSaveTimers: new Map(),
  inflightSavePromises: new Map(),
  sessionSaveQueue: Promise.resolve(),
  sessionQueuedVersions: new Map(),
  importSaveVersions: new Map(),
  importSaveErrors: new Map(),
  authRequestGeneration: 0,
  bootstrapController: null,
  settingsController: null,
  cancelController: null,
  cancelPromise: null,
  cloudReviewEnabled: false,
  demoMode: false,
  modeGeneration: 0,
  modeTransition: null,
  demoBootstrapController: null,
  formalMutationCount: 0,
  renderOverride: null,
  eventsRestartOverride: null,
  decisionBoard: null,
  decisionBoardController: null,
  decisionStatusTimer: null,
  decisionRefreshTask: null,
  decisionUi: {
    mode: 'grouped', filter: '', sort: {key: null, direction: null}, horizon: 1,
    scrollPositions: [], openDetailCode: null, openDetailSnapshotId: null,
  },
};

const DEFAULT_MARKET_CONTEXT = Object.freeze([
  {context_id: "china-sector-breadth", label: "中国行业/板块广度与轮动", region: "China", context_kind: "sector_breadth", source_symbol: null, display_code: null, enabled: false, display_order: 1, verification_status: "unverified", is_tradable_proxy: false},
  {context_id: "us-sp500", label: "S&P 500", region: "United States", context_kind: "index", source_symbol: null, display_code: null, enabled: false, display_order: 2, verification_status: "unverified", is_tradable_proxy: false},
  {context_id: "us-nasdaq-composite", label: "Nasdaq Composite", region: "United States", context_kind: "index", source_symbol: null, display_code: null, enabled: false, display_order: 3, verification_status: "unverified", is_tradable_proxy: false},
  {context_id: "us-nasdaq-100", label: "Nasdaq-100", region: "United States", context_kind: "index", source_symbol: null, display_code: null, enabled: false, display_order: 4, verification_status: "unverified", is_tradable_proxy: false},
  {context_id: "china-semiconductor-etf", label: "中国半导体可交易 ETF 代理", region: "China", context_kind: "tradable_proxy", source_symbol: null, display_code: null, enabled: false, display_order: 5, verification_status: "unverified", is_tradable_proxy: true},
  {context_id: "korea-semiconductor-etf", label: "韩国半导体可交易 ETF 代理", region: "Korea", context_kind: "tradable_proxy", source_symbol: null, display_code: null, enabled: false, display_order: 6, verification_status: "unverified", is_tradable_proxy: true},
]);

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
function displayIdentity(code, name) {
  const parts = [code, name]
    .map(value => String(value ?? '').trim())
    .filter(Boolean);
  return parts.length ? parts.map(escapeHtml).join(' · ') : '未知标的';
}
function numericValue(value) {
  return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
}
function fmt(value, digits = 2, fallback = '—') {
  if (!numericValue(value)) return fallback;
  return Number(value).toFixed(digits);
}
function pct(value, digits = 2, ratio = false) {
  if (!numericValue(value)) return '—';
  const n = Number(value) * (ratio ? 100 : 1);
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`;
}

// Decision-board values are API decimal ratios.  This intentionally has no
// magnitude heuristic: 0.0009 means +0.09%, not +0.0009% or +0.9%.
function decisionPercent(value, digits = 2) {
  if (!numericValue(value)) return '—';
  const n = Number(value) * 100;
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`;
}
const DECISION_GROUPS = Object.freeze(['可加仓', '可入场', '可试探', '观望', '减仓', '数据异常']);
const DECISION_COLUMNS = Object.freeze([
  ['instrument', '标的'], ['theme', '分类'], ['today', '今日'], ['previous_day_delta', '较昨日'], ['week_1', '近1周'],
  ['volume', '量能'], ['ma', '均线'], ['macd', 'MACD'], ['kdj', 'KDJ'], ['td', '九转'], ['rsi', 'RSI'], ['chan', '缠论'],
  ['sector', '板块'], ['forecast', '预测'], ['grade', '分级'], ['health', '数据状态'], ['reason', '理由 / 风险'],
]);
const DECISION_SORTABLE = Object.freeze(new Set(['today', 'previous_day_delta', 'week_1', 'volume', 'ma', 'macd', 'kdj', 'td', 'rsi', 'chan', 'forecast', 'grade']));
const DECISION_SORT_KEY = Object.freeze({grade: 'grade_health'});

function decisionRows(payload) {
  const byCode = new Map();
  const add = row => { if (row && row.ts_code && !byCode.has(String(row.ts_code))) byCode.set(String(row.ts_code), row); };
  (payload?.rows || []).forEach(add);
  Object.values(payload?.groups || {}).forEach(rows => (rows || []).forEach(add));
  return [...byCode.values()];
}
function decisionValue(row, key) {
  const supplied = row?.sort_keys?.[DECISION_SORT_KEY[key] || key];
  if (supplied !== null && supplied !== undefined && supplied !== '') return supplied;
  if (key in (row?.returns || {})) return row.returns[key];
  return row?.[key];
}
function decisionCompareValue(left, right) {
  const leftMissing = left === null || left === undefined || left === '';
  const rightMissing = right === null || right === undefined || right === '';
  if (leftMissing || rightMissing) return leftMissing === rightMissing ? 0 : leftMissing ? 1 : -1;
  if (Array.isArray(left) || Array.isArray(right)) {
    const a = Array.isArray(left) ? left : [left], b = Array.isArray(right) ? right : [right];
    for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
      const result = decisionCompareValue(a[index], b[index]);
      if (result) return result;
    }
    return 0;
  }
  if (numericValue(left) && numericValue(right)) return Number(left) - Number(right);
  return String(left).localeCompare(String(right), 'zh-CN');
}
function decisionHealthPriority(row) { return row?.sort_keys?.grade_health ?? row?.sort_keys?.health_priority ?? null; }
function decisionSorted(rows, sort) {
  if (!sort?.key || !sort?.direction) return [...rows];
  const sign = sort.direction === 'desc' ? -1 : 1;
  return [...rows].sort((a, b) => {
    const result = decisionCompareValue(decisionValue(a, sort.key), decisionValue(b, sort.key));
    if (result) return result * sign;
    const healthResult = decisionCompareValue(decisionHealthPriority(a), decisionHealthPriority(b));
    if (healthResult) return healthResult;
    return String(a?.ts_code || '').localeCompare(String(b?.ts_code || ''), 'en');
  });
}
function decisionMatches(row, filter) {
  const query = String(filter || '').trim().toLowerCase();
  if (!query) return true;
  return [row?.ts_code, row?.name, row?.theme_l1, row?.theme_l2, row?.grade, row?.sector?.label]
    .filter(value => value !== null && value !== undefined).join(' ').toLowerCase().includes(query);
}
function decisionVisibleRows(payload, ui) { return decisionSorted(decisionRows(payload).filter(row => decisionMatches(row, ui?.filter)), ui?.sort); }
function decisionGroupedRows(payload, ui) {
  const rows = decisionVisibleRows(payload, ui);
  const membership = new Map();
  for (const [group, members] of Object.entries(payload?.groups || {})) for (const row of members || []) if (row?.ts_code && !membership.has(String(row.ts_code))) membership.set(String(row.ts_code), group);
  const grouped = new Map(DECISION_GROUPS.map(group => [group, []]));
  for (const row of rows) {
    const requested = membership.get(String(row.ts_code)) || row.grade;
    const group = DECISION_GROUPS.includes(requested) ? requested : '数据异常';
    grouped.get(group).push(row);
  }
  return grouped;
}
function decisionNextSort(current, key) {
  if (current?.key !== key) return {key, direction: 'asc'};
  if (current.direction === 'asc') return {key, direction: 'desc'};
  return {key: null, direction: null};
}
function decisionForecast(row, horizon) {
  const forecast = row?.forecast || {};
  const item = forecast[String(horizon)] || forecast[horizon] || forecast;
  if (numericValue(item)) return Number(item);
  return item?.expected_return ?? item?.return ?? item?.median_return ?? item?.q50_return ?? null;
}
function decisionBlocked(row) {
  const values = [row?.data_status, row?.source_status, row?.indicator_basis?.status, row?.indicator_basis?.verification_status]
    .filter(Boolean).map(value => typeof value === 'object' ? JSON.stringify(value) : String(value)).join(' ').toLowerCase();
  return /(mock|degraded|unverified|unavailable|stale|missing)/.test(values);
}
function decisionHealthText(row) { return [row?.data_status, row?.source_status].filter(Boolean).map(value => typeof value === 'string' ? value : value?.label || value?.status).filter(Boolean).join(' · ') || '未验证'; }
function decisionCellText(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'object') return value.label || value.text || value.status || fallback;
  return String(value);
}
function decisionMetricHtml(primary, lines = []) {
  return `<div class="decision-metric"><strong>${escapeHtml(primary)}</strong>${lines.filter(Boolean).map(line => `<span>${escapeHtml(line)}</span>`).join('')}</div>`;
}
function decisionVolumeHtml(volume, provisional) {
  const ratio = numericValue(volume?.ratio) ? `量比 ${fmt(volume.ratio, 2)}` : '量比 —';
  const status = String(provisional?.status || 'confirmed_snapshot');
  const provisionalLine = /provisional|computed|unverified|research_only/i.test(status) ? `临时观测 · ${status}` : '确认快照';
  return decisionMetricHtml(decisionCellText(volume), [ratio, provisionalLine]);
}
function decisionMaHtml(ma) {
  const arrows = Array.isArray(ma?.arrows) ? ma.arrows.map(item => `${item?.window || 'M?'}${item?.dir === 'up' ? '↑' : item?.dir === 'down' ? '↓' : '·'}`).join(' ') : '—';
  return decisionMetricHtml(decisionCellText(ma), [arrows, decisionCellText(ma?.values_text, '')]);
}
function decisionMacdHtml(macd) { return decisionMetricHtml(decisionCellText(macd), [`DIF ${fmt(macd?.dif, 4)} · DEA ${fmt(macd?.dea, 4)}`]); }
function decisionKdjHtml(kdj) { return decisionMetricHtml(`J ${fmt(kdj?.j, 1)} · ${decisionCellText(kdj)}`, [decisionCellText(kdj?.note, ''), `K/D ${fmt(kdj?.k, 1)}/${fmt(kdj?.d, 1)}`]); }
function decisionTdHtml(td) {
  const count = String(td?.label || '').match(/(\d+)$/)?.[1] || '—';
  const direction = td?.kind === 'buy' ? '多头' : td?.kind === 'sell' ? '空头' : '中性';
  return decisionMetricHtml(`TD9 ${direction} · ${count}`, [decisionCellText(td)]);
}
function decisionRsiHtml(rsi) { return decisionMetricHtml(`RSI ${fmt(rsi?.value, 1)}`, [decisionCellText(rsi)]); }
function decisionChanRange(zone) {
  const low = Array.isArray(zone) ? zone[0] : zone?.low ?? zone?.lower ?? zone?.start;
  const high = Array.isArray(zone) ? zone[1] : zone?.high ?? zone?.upper ?? zone?.end;
  return numericValue(low) && numericValue(high) ? `区间 ${fmt(low, 4)}–${fmt(high, 4)}` : '区间 —';
}
function decisionChanHtml(chan) { return decisionMetricHtml(decisionCellText(chan), [decisionCellText(chan?.status, ''), decisionChanRange(chan?.zone)]); }
function decisionSectorHtml(sector) {
  const count = value => numericValue(value) ? String(Number(value)) : '—';
  const coverage = sector?.coverage_count ?? sector?.coverage ?? sector?.fund_count;
  return decisionMetricHtml(decisionCellText(sector), [`${count(sector?.up)}↑ ${count(sector?.down)}↓ ${count(sector?.flat)}平 · 覆盖 ${count(coverage)}`, decisionCellText(sector?.note, '')]);
}
function decisionRowHtml(row, index, horizon = 1) {
  const returns = row?.returns || {}, blocked = decisionBlocked(row), health = decisionHealthText(row);
  const forecast = decisionForecast(row, horizon), healthClass = blocked ? 'health-badge--degraded' : 'health-badge--verified';
  const metric = (value, fallback = '—') => decisionMetricHtml(decisionCellText(value, fallback));
  return `<tr class="decision-row ${blocked ? 'decision-row--blocked' : ''}" data-decision-code="${escapeHtml(row?.ts_code || '')}" tabindex="0" aria-label="查看 ${escapeHtml(row?.name || row?.ts_code || 'ETF')} 详情">
    <td class="decision-sticky-first"><div class="instrument-name">${escapeHtml(row?.name || row?.ts_code || '未知标的')}</div><div class="instrument-meta">${escapeHtml(row?.ts_code || '—')}</div></td>
    <td>${metric(`${decisionCellText(row?.theme_l1)}/${decisionCellText(row?.theme_l2)}`)}</td>
    <td class="${escapeHtml(colorClass(returns.today))}">${escapeHtml(decisionPercent(returns.today))}</td>
    <td class="${escapeHtml(colorClass(returns.previous_day_delta))}">${escapeHtml(decisionPercent(returns.previous_day_delta))}</td>
    <td class="${escapeHtml(colorClass(returns.week_1))}">${escapeHtml(decisionPercent(returns.week_1))}</td>
    <td>${decisionVolumeHtml(row?.volume, row?.provisional)}</td><td>${decisionMaHtml(row?.ma)}</td><td>${decisionMacdHtml(row?.macd)}</td><td>${decisionKdjHtml(row?.kdj)}</td><td>${decisionTdHtml(row?.td)}</td><td>${decisionRsiHtml(row?.rsi)}</td><td>${decisionChanHtml(row?.chan)}</td><td>${decisionSectorHtml(row?.sector)}</td>
    <td class="${escapeHtml(colorClass(forecast))}"><div>${escapeHtml(decisionPercent(forecast))}</div><div class="forecast-flag">${horizon} 日 · 研究情景</div></td>
    <td><span class="badge ${escapeHtml(stateClass(row?.grade))}">${escapeHtml(row?.grade || '—')}</span>${blocked ? '<div class="decision-block-note">已阻断</div>' : ''}</td>
    <td><span class="health-badge ${healthClass}">${escapeHtml(health)}</span></td>
    <td class="decision-sticky-last"><div class="decision-reason">${escapeHtml(row?.grade_reason || '—')}</div><span class="risk-badge">${blocked ? '不可操作' : '研究提示'}</span></td>
  </tr>`;
}
function decisionHeaderHtml(sort) {
  return `<thead><tr>${DECISION_COLUMNS.map(([key, label], index) => {
    const direction = sort?.key === key ? (sort.direction === 'asc' ? ' ↑' : ' ↓') : '';
    const sticky = index === 0 ? ' decision-sticky-first' : index === DECISION_COLUMNS.length - 1 ? ' decision-sticky-last' : '';
    const sortable = DECISION_SORTABLE.has(key);
    return `<th class="${sticky}"${sortable ? `><button type="button" class="decision-sort" data-decision-sort="${key}">${escapeHtml(label)}${direction}</button>` : `>${escapeHtml(label)}`}</th>`;
  }).join('')}</tr></thead>`;
}
function decisionTableHtml(rows, ui, label = '', tableId = 'decisionBoardTable-global') {
  const empty = rows.length ? rows.map((row, index) => decisionRowHtml(row, index, ui.horizon)).join('') : `<tr><td colspan="${DECISION_COLUMNS.length}" class="loading-row">无符合条件的 ETF</td></tr>`;
  return `${label}<div class="decision-table-wrap"><table id="${escapeHtml(tableId)}" class="decision-table">${decisionHeaderHtml(ui.sort)}<tbody>${empty}</tbody></table></div>`;
}
function colorClass(value) { return !numericValue(value) ? 'neutral' : Number(value) >= 0 ? 'up' : 'down'; }
function safeHttpUrl(value) {
  if (!value) return '';
  try {
    const parsed = new URL(String(value), window.location.origin);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : '';
  } catch (_) { return ''; }
}
function timeText(value) {
  if (!value) return '—';
  const text = String(value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const d = new Date(text);
  return Number.isNaN(d.getTime()) ? text : `${d.toLocaleString('zh-CN', {hour12:false, timeZone:'Asia/Shanghai'})} · Asia/Shanghai`;
}
function amountText(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  if (n === 0) return '0';
  if (n >= 1e8) return `${(n / 1e8).toFixed(2)}亿`;
  if (n >= 1e4) return `${(n / 1e4).toFixed(1)}万`;
  return n.toFixed(0);
}
function holdingPnlPercent(holding) {
  if (!numericValue(holding?.cost_price) || Number(holding.cost_price) <= 0 || !numericValue(holding?.pnl_pct)) return '—';
  return pct(holding.pnl_pct);
}
function stateClass(label) {
  if (['可入场'].includes(label)) return 'entry';
  if (['可试探'].includes(label)) return 'probe';
  if (['可加仓', '加仓', '小幅加仓'].includes(label)) return 'add-pos';
  if (['持有', '观察'].includes(label)) return 'hold';
  if (['观望'].includes(label)) return 'watch';
  if (['减仓', '风险观察'].includes(label)) return 'reduce';
  return 'anomaly';
}
function toast(message, timeout = 2600) {
  const node = qs('#toast');
  node.textContent = message;
  node.classList.remove('hidden');
  clearTimeout(node._timer);
  node._timer = setTimeout(() => node.classList.add('hidden'), timeout);
}
function blockFormalMutation(action = '此操作') {
  if (!state.demoMode && !state.modeTransition) return false;
  toast(`演示模式已禁用${action}；退出演示后可操作`);
  return true;
}

function rememberDecisionScroll() {
  state.decisionUi.scrollPositions = qsa('.decision-table-wrap').map(wrap => ({left: wrap.scrollLeft, top: wrap.scrollTop}));
}
function restoreDecisionScroll() {
  qsa('.decision-table-wrap').forEach((wrap, index) => {
    const saved = state.decisionUi.scrollPositions[index];
    if (saved) { wrap.scrollLeft = saved.left; wrap.scrollTop = saved.top; }
  });
}
function decisionRefreshLabel(payload = state.decisionBoard) {
  const pending = state.decisionRefreshTask;
  if (pending) return `刷新任务 ${pending.status || 'queued'} · 等待新快照`;
  return payload?.refresh_state || '只读快照';
}
function syncDecisionRefreshButton() {
  const button = qs('#refreshButton');
  if (!button) return;
  const pending = state.decisionRefreshTask;
  button.disabled = Boolean(pending?.status === 'queued' || pending?.status === 'running');
  button.textContent = pending ? `刷新 ${pending.status || 'queued'}` : '刷新';
}
function renderDecisionBoard() {
  const area = qs('#decisionTableArea'), payload = state.decisionBoard;
  if (!area) return;
  if (!payload) { area.innerHTML = '<div class="empty-state">正在读取只读决策快照…</div>'; return; }
  rememberDecisionScroll();
  const ui = state.decisionUi, counts = payload.counts || {}, grouped = decisionGroupedRows(payload, ui);
  const countEl = qs('#decisionCounts');
  if (countEl) countEl.innerHTML = DECISION_GROUPS.map(group => `<button type="button" class="decision-count ${group === '数据异常' ? 'decision-count--anomaly' : ''}" data-decision-group="${escapeHtml(group)}"><strong>${escapeHtml(group)}</strong><span>${escapeHtml(String(counts[group] ?? grouped.get(group)?.length ?? 0))}</span></button>`).join('');
  const meta = qs('#decisionSnapshotMeta');
  if (meta) meta.textContent = `快照 ${payload.snapshot_id || '—'} · 生成 ${timeText(payload.generated_at)} · 下次 ${timeText(payload.next_refresh_at)} · ${decisionRefreshLabel(payload)}`;
  syncDecisionRefreshButton();
  const warning = qs('#decisionWarning');
  const hasBlocked = decisionRows(payload).some(decisionBlocked);
  if (warning) { warning.classList.toggle('hidden', !hasBlocked); warning.textContent = hasBlocked ? '存在 Mock、退化、未验证或缺失状态：表格仍可阅读，但所有操作级呈现已阻断。' : ''; }
  if (ui.mode === 'global') area.innerHTML = decisionTableHtml(decisionVisibleRows(payload, ui), ui, '<div class="decision-global-label">全局排名 · 使用服务端提供的 sort_keys</div>', 'decisionBoardTable-global');
  else {
    area.innerHTML = [...grouped.entries()].map(([group, rows], index) => `<section class="decision-group decision-group--${group === '数据异常' ? 'anomaly' : 'normal'}"><div class="decision-group-head"><span class="badge ${escapeHtml(stateClass(group))}">${escapeHtml(group)}</span><span>${escapeHtml(String(rows.length))} 个标的</span></div>${decisionTableHtml(rows, ui, '', `decisionBoardTable-${index}`)}</section>`).join('');
  }
  const horizon = qs('#decisionHorizon'); if (horizon) horizon.value = String(ui.horizon);
  qs('#decisionModeGrouped')?.classList.toggle('active', ui.mode === 'grouped'); qs('#decisionModeGlobal')?.classList.toggle('active', ui.mode === 'global');
  qsa('[data-decision-sort]').forEach(button => button.addEventListener('click', () => { state.decisionUi.sort = decisionNextSort(state.decisionUi.sort, button.dataset.decisionSort); renderDecisionBoard(); }));
  qsa('[data-decision-code]').forEach(row => {
    row.addEventListener('click', () => openDecisionDetail(row.dataset.decisionCode));
    row.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openDecisionDetail(row.dataset.decisionCode); } });
  });
  qsa('[data-decision-group]').forEach(button => button.addEventListener('click', () => { state.decisionUi.filter = button.dataset.decisionGroup; const search = qs('#decisionSearch'); if (search) search.value = state.decisionUi.filter; renderDecisionBoard(); }));
  restoreDecisionScroll();
}
async function loadDecisionBoard(silent = false) {
  if (state.demoMode || state.modeTransition) return;
  const controller = new AbortController();
  state.decisionBoardController?.abort(); state.decisionBoardController = controller;
  try {
    const horizon = Number(state.decisionUi.horizon || 1);
    const payload = await api(`/api/decision-board?horizon=${encodeURIComponent(horizon)}`, {signal: controller.signal});
    if (controller.signal.aborted) return;
    const selectedHorizon = Number(payload.selected_horizon ?? payload.selected_forecast_horizon ?? horizon);
    if ([1, 3, 5, 10].includes(selectedHorizon)) state.decisionUi.horizon = selectedHorizon;
    const changed = !state.decisionBoard || payload.snapshot_id !== state.decisionBoard.snapshot_id;
    state.decisionBoard = payload;
    if (changed && state.decisionRefreshTask) state.decisionRefreshTask = null;
    else if (state.decisionRefreshTask && payload.refresh_state) state.decisionRefreshTask.status = payload.refresh_state;
    renderDecisionBoard();
    if (changed && state.decisionUi.openDetailCode) openDecisionDetail(state.decisionUi.openDetailCode, true);
  } catch (error) {
    if (!silent && error.name !== 'AbortError' && error.message !== 'unauthorized') toast(`决策快照读取失败：${error.message}`, 5000);
  } finally { if (state.decisionBoardController === controller) state.decisionBoardController = null; }
}
function scheduleDecisionStatusPoll() {
  clearInterval(state.decisionStatusTimer);
  state.decisionStatusTimer = setInterval(() => loadDecisionBoard(true), 30 * 1000);
}
async function requestDecisionBoardRefresh() {
  if (blockFormalMutation('决策快照刷新')) return;
  if (state.decisionRefreshTask?.status === 'queued' || state.decisionRefreshTask?.status === 'running') return;
  try {
    const result = await api('/api/decision-board/refresh', {method: 'POST', body: JSON.stringify({})});
    state.decisionRefreshTask = {taskId: result.task_id || result.run_id || '—', status: result.status || 'queued'};
    syncDecisionRefreshButton();
    renderDecisionBoard();
    toast(`决策快照刷新已排队：${state.decisionRefreshTask.taskId}`);
  } catch (error) {
    toast(`快照刷新请求失败：${error.message}`, 5000);
  }
}
function decisionDetailLevel(level) { return numericValue(level?.price ?? level) ? fmt(level?.price ?? level, 4) : '—'; }
function decisionDetailHtml(detail) {
  const history = Array.isArray(detail?.history) ? detail.history : [];
  const scenario = Array.isArray(detail?.forecast_scenario) ? detail.forecast_scenario : [];
  const metric = (label, value) => `<div class="detail-metric" aria-label="${escapeHtml(`${label} ${value}`)}"><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></div>`;
  const selectedHorizon = [1, 3, 5, 10].includes(Number(detail?.selected_horizon)) ? Number(detail.selected_horizon) : 1;
  const forecasts = detail?.forecasts && typeof detail.forecasts === 'object' ? detail.forecasts : {};
  const selectedForecast = detail?.forecast && typeof detail.forecast === 'object' ? detail.forecast : {};
  const forecastCards = [1, 3, 5, 10].map(horizon => {
    const forecast = forecasts[String(horizon)] || forecasts[horizon] || (horizon === selectedHorizon ? selectedForecast : {});
    const selectedClass = horizon === selectedHorizon ? ' detail-forecast-card--selected' : '';
    return `<article class="detail-forecast-card${selectedClass}" aria-label="${escapeHtml(`${horizon} 日预测`)}">
      <div class="forecast-label">FORECAST · 非实际结果 · 仅供研究</div><h4>${escapeHtml(`${horizon} 日预测`)}</h4>
      <div class="detail-forecast-card-grid">${[
        ['期望收益', decisionPercent(forecast?.expected_return)], ['上涨概率', decisionPercent(forecast?.p_up)], ['q10/q50/q90', `${decisionPercent(forecast?.q10)} / ${decisionPercent(forecast?.q50)} / ${decisionPercent(forecast?.q90)}`], ['置信度', fmt(forecast?.confidence, 0)], ['校准状态', decisionCellText(forecast?.calibration_status)],
      ].map(([label, value]) => metric(label, value)).join('')}</div>
      <div class="forecast-card-disclaimer">研究情景 · 非实际结果 · 不构成投资建议</div></article>`;
  }).join('');
  const levels = detail?.support_resistance || detail?.support_resistance_levels || {};
  const quote = detail?.quote || {}, provisional = detail?.provisional || {}, indicator = detail?.indicator || {}, chan = detail?.chan || {};
  const indicatorText = [
    `量能 ${decisionCellText(detail?.volume)} / 量比 ${fmt(detail?.volume?.ratio, 2)}`,
    `均线 ${decisionCellText(detail?.ma)} / ${decisionCellText(detail?.ma?.values_text, '—')}`,
    `MACD ${decisionCellText(detail?.macd)} / DIF ${fmt(detail?.macd?.dif, 4)} DEA ${fmt(detail?.macd?.dea, 4)}`,
    `KDJ J ${fmt(detail?.kdj?.j, 1)} K ${fmt(detail?.kdj?.k, 1)} D ${fmt(detail?.kdj?.d, 1)}`,
    `TD9 ${decisionCellText(detail?.td)} / RSI ${fmt(detail?.rsi?.value, 1)}`,
  ].join(' · ');
  const levelText = levels => (Array.isArray(levels) ? levels : []).slice(0, 3).map(level => `${decisionDetailLevel(level)} ${decisionCellText(level?.label, '')}`.trim()).join(' / ') || '—';
  return `<div class="eyebrow">DECISION SNAPSHOT · ${escapeHtml(detail?.snapshot_id || '—')}</div>
    <h2>${escapeHtml(detail?.name || detail?.ts_code || 'ETF')} · ${escapeHtml(detail?.ts_code || '—')}</h2>
    <div class="detail-grid">${[
      ['数据状态', decisionCellText(detail?.data_status)], ['来源状态', decisionCellText(detail?.source_status)],
      ['历史K线', `${history.length} 根`], ['预测情景', `${scenario.length} 根 · 非实际结果`],
      ['指标版本', decisionCellText(indicator?.version)], ['指标日期', decisionCellText(indicator?.as_of_date)],
      ['来源时间', timeText(quote?.source_time)], ['临时观测', decisionCellText(provisional?.status)], ['临时观测时间', timeText(provisional?.observed_at || provisional?.source_time)],
    ].map(([label, value]) => metric(label, value)).join('')}</div>
    <section class="detail-forecast forecast-surface"><div class="forecast-label">FORECAST · 非实际结果 · 仅供研究</div><h3>1 / 3 / 5 / 10 日预测 · 当前 ${escapeHtml(String(selectedHorizon))} 日</h3>
      <div class="detail-forecast-grid detail-forecast-cards">${forecastCards}</div></section>
    <div class="detail-chart-note">历史K线 ${history.length} 根 → 预测情景 ${scenario.length} 根 · 边界后的紫色虚线蜡烛均为非实际结果。</div>
    <section class="reason-box"><strong>支撑 / 压力 / 缠论近似</strong><br>支撑 ${escapeHtml(decisionDetailLevel(levels?.nearest_support))} · 压力 ${escapeHtml(decisionDetailLevel(levels?.nearest_resistance))} · ${escapeHtml(decisionChanRange(chan?.zone || levels?.chan_zone_approx))}<br>支撑层级 ${escapeHtml(levelText(levels?.support_levels))}<br>压力层级 ${escapeHtml(levelText(levels?.resistance_levels))}<br>${escapeHtml(decisionCellText(chan?.label))} · ${escapeHtml(decisionCellText(chan?.detail))}</section>
    <section class="reason-box"><strong>指标与来源</strong><br>${escapeHtml(indicatorText)}<br>来源 ${escapeHtml(decisionCellText(quote?.source))} · 时间已验证 ${escapeHtml(String(Boolean(quote?.timestamp_verified)))} · 临时来源 ${escapeHtml(decisionCellText(provisional?.source))}</section>`;
}
function drawDecisionSnapshotChart(history, forecastScenario) {
  const canvas = qs('#chartCanvas');
  const ctx = canvas?.getContext?.('2d');
  if (!canvas || !ctx) return;
  const historical = (Array.isArray(history) ? history : []).filter(item => numericValue(item?.close));
  const forecast = (Array.isArray(forecastScenario) ? forecastScenario : []).filter(item => numericValue(item?.close));
  const data = [...historical, ...forecast];
  if (!data.length) { canvas.classList.add('hidden'); return; }
  canvas.classList.remove('hidden');
  const rect = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  const width = Math.max(360, rect.width || 720), height = 290;
  canvas.width = width * dpr; canvas.height = height * dpr;
  if (typeof ctx.setTransform === 'function') ctx.setTransform(dpr, 0, 0, dpr, 0, 0); else ctx.scale?.(dpr, dpr);
  ctx.clearRect(0, 0, width, height);
  const candles = data.map(item => ({open: Number(item.open ?? item.close), high: Number(item.high ?? item.close), low: Number(item.low ?? item.close), close: Number(item.close), forecast: Boolean(item.is_forecast || item.not_actual)}));
  const high = Math.max(...candles.map(item => item.high)), low = Math.min(...candles.map(item => item.low)), range = high - low || 1;
  const left = 43, right = 15, top = 25, bottom = height - 30, step = (width - left - right) / Math.max(candles.length, 1);
  const y = value => top + (high - value) / range * (bottom - top);
  ctx.font = '10px system-ui'; ctx.strokeStyle = '#2a3545'; ctx.fillStyle = '#94a5b8';
  for (let index = 0; index <= 4; index += 1) { const yy = top + (bottom - top) * index / 4; ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(width - right, yy); ctx.stroke(); ctx.fillText((high - range * index / 4).toFixed(3), 2, yy + 3); }
  candles.forEach((item, index) => {
    const x = left + step * (index + .5), forecastCandle = index >= historical.length || item.forecast;
    ctx.strokeStyle = forecastCandle ? '#b283ff' : item.close >= item.open ? '#ff766e' : '#5bd0a5';
    if (ctx.setLineDash) ctx.setLineDash(forecastCandle ? [3, 2] : []);
    ctx.beginPath(); ctx.moveTo(x, y(item.high)); ctx.lineTo(x, y(item.low)); ctx.stroke();
    ctx.fillStyle = ctx.strokeStyle; ctx.fillRect(x - Math.max(1, step * .25), Math.min(y(item.open), y(item.close)), Math.max(2, step * .5), Math.max(1, Math.abs(y(item.open) - y(item.close))));
  });
  if (ctx.setLineDash) ctx.setLineDash([]);
  if (forecast.length) { const boundary = left + step * historical.length; ctx.strokeStyle = '#b283ff'; ctx.setLineDash?.([4, 3]); ctx.beginPath(); ctx.moveTo(boundary, top); ctx.lineTo(boundary, bottom); ctx.stroke(); ctx.setLineDash?.([]); ctx.fillStyle = '#d6c2ff'; ctx.fillText('预测情景 · 非实际结果', Math.min(boundary + 5, width - 115), 16); }
  ctx.fillStyle = '#9dafc1'; ctx.fillText(`历史 ${historical.length} 根`, left, height - 9); ctx.fillText(`预测 ${forecast.length} 根`, width - 75, height - 9);
}
async function openDecisionDetail(code, preserve = false) {
  if (!code || !state.decisionBoard) return;
  const snapshotId = String(state.decisionBoard.snapshot_id || '');
  state.decisionUi.openDetailCode = code;
  state.decisionUi.openDetailSnapshotId = snapshotId;
  state.detailCode = code;
  qs('#chartCanvas')?.classList.add('hidden');
  try {
    const detail = await api(`/api/decision-board/${encodeURIComponent(code)}?horizon=${encodeURIComponent(state.decisionUi.horizon)}&snapshot_id=${encodeURIComponent(snapshotId)}`);
    if (state.decisionUi.openDetailCode !== code || state.decisionUi.openDetailSnapshotId !== snapshotId) return;
    if (detail.snapshot_id && snapshotId && detail.snapshot_id !== snapshotId) throw new Error('详情快照与当前表格不一致');
    qs('#detailContent').innerHTML = decisionDetailHtml(detail);
    drawDecisionSnapshotChart(detail.history, detail.forecast_scenario);
    if (!preserve) openModal('detailOverlay');
  } catch (error) { if (!preserve) toast(`详情读取失败：${error.message}`, 5000); }
}
function handleDecisionBoardRoute() {
  if (window.location.pathname === '/workbench/1430') window.history?.replaceState?.(null, '', '/');
}

function renderCurrentView() {
  if (typeof state.renderOverride === 'function') return state.renderOverride();
  return renderAll();
}

function restartFormalEvents() {
  if (typeof state.eventsRestartOverride === 'function') return state.eventsRestartOverride();
  return connectEvents();
}

function modeRequestCurrent(generation, expectedDemo) {
  if (generation !== state.modeGeneration || state.demoMode !== expectedDemo) return false;
  const transitionTarget = state.modeTransition?.target;
  return !transitionTarget || transitionTarget === (expectedDemo ? 'demo' : 'formal');
}

function beginModeTransition(target) {
  if (state.modeTransition) return null;
  if (state.formalMutationCount > 0) {
    toast('当前有正式写操作进行中，完成后再切换模式');
    return null;
  }
  state.modeGeneration += 1;
  state.modeTransition = {target, generation: state.modeGeneration};
  state.bootstrapController?.abort();
  state.demoBootstrapController?.abort();
  state.settingsController?.abort();
  state.decisionBoardController?.abort();
  clearInterval(state.decisionStatusTimer);
  cancelDetailRequest();
  state.eventAbort?.abort();
  clearTimeout(state.eventRetry);
  clearInterval(state.refreshTimer);
  abortImportRequests();
  if (state.holdingImport) {
    closeModal('portfolioConfirmOverlay');
    closeModal('portfolioImportOverlay');
    resetImportWorkflow({advance: false});
  }
  renderSourceBadge(state.data || {});
  return state.modeGeneration;
}

function endModeTransition(generation) {
  if (state.modeTransition?.generation !== generation) return false;
  state.modeTransition = null;
  renderSourceBadge(state.data || {});
  return true;
}

async function api(path, options = {}) {
  const {authGeneration = state.authRequestGeneration, ...requestOptions} = options;
  const method = String(requestOptions.method || 'GET').toUpperCase();
  const formalMutation = method !== 'GET' && !String(path).startsWith('/api/demo/');
  if (formalMutation) {
    if (blockFormalMutation('正式写操作')) {
      const blocked = new Error('formal mutation blocked during demo mode transition');
      blocked.code = 'FORMAL_MUTATION_BLOCKED';
      throw blocked;
    }
    state.formalMutationCount += 1;
  }
  const headers = new Headers(requestOptions.headers || {});
  if (method !== 'GET' && method !== 'HEAD' && !headers.has('X-CSRF-Token')) {
    const csrf = String(document.cookie || '').split('; ').find(value => value.startsWith('__Host-fund-csrf=') || value.startsWith('fund-csrf='))?.split('=').slice(1).join('');
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf));
  }
  if (requestOptions.body instanceof FormData) {
    headers.delete('Content-Type');
    for (const name of [...headers.keys()]) if (name.toLowerCase() === 'content-type') headers.delete(name);
  } else if (requestOptions.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  try {
    const response = await fetch(path, {...requestOptions, headers, credentials:'same-origin'});
    if (response.status === 401) {
      if (authGeneration === state.authRequestGeneration) { state.sessionActive=false; showAuth('会话已失效，请重新登录'); }
      throw new Error('unauthorized');
    }
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try { const payload = await response.json(); detail = payload.detail || detail; } catch (_) {}
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    const type = response.headers.get('content-type') || '';
    return type.includes('application/json') ? response.json() : response.text();
  } finally {
    if (formalMutation) state.formalMutationCount = Math.max(0, state.formalMutationCount - 1);
  }
}

const IMPORT_STATUS_CLASS_ALLOWLIST = Object.freeze({matched:'matched', ambiguous:'ambiguous', unmatched:'unmatched', low_confidence:'low_confidence', duplicate:'duplicate', rejected:'rejected', pending:'pending', reviewed:'reviewed', confirmed:'confirmed'});
const IMPORT_DECIMAL_CONTRACTS = Object.freeze({shares:{maximum:'1000000000', scale:4}, cost_price:{maximum:'1000000000', scale:6}, target_weight:{maximum:'1', scale:6}});
function isImportCurrent(generation, sessionId = '') {
  return generation === state.importGeneration && (!sessionId || state.holdingImport?.sessionId === sessionId);
}
function trackImportController(controller) { state.importControllers.add(controller); return controller; }
function untrackImportController(controller) { state.importControllers.delete(controller); }
function abortImportRequests() {
  for (const controller of state.importControllers) controller.abort();
  state.importControllers.clear();
  for (const record of state.pendingSaveTimers.values()) clearTimeout(record.timer);
  state.pendingSaveTimers.clear();
  state.importSaveVersions.clear();
  state.importSaveErrors.clear();
  state.inflightSavePromises.clear();
  state.sessionQueuedVersions.clear();
  state.sessionSaveQueue = Promise.resolve();
}
function newImportGeneration() {
  state.importGeneration += 1;
  abortImportRequests();
  return state.importGeneration;
}
function isEnrolledAdmin() {
  return state.sessionActive && state.auth.identifier !== null && state.auth.role === 'admin';
}
function setAdminAccountStatus(message = '', isError = false) {
  const status = qs('#adminAccountStatus');
  if (!status) return;
  status.textContent = message;
  status.classList.toggle('error-text', isError);
}
function renderAdminAccounts() {
  const panel = qs('#adminAccountsPanel');
  if (!panel) return;
  const allowed = isEnrolledAdmin();
  panel.hidden = !allowed;
  panel.classList.toggle('hidden', !allowed);
  if (!allowed) {
    state.adminUsers = [];
    qs('#adminUserList')?.replaceChildren();
    qs('#adminResetPasswordForm')?.classList.add('hidden');
    setAdminAccountStatus();
    return;
  }
  const list = qs('#adminUserList');
  if (!list) return;
  const activeAdminCount = state.adminUsers.filter(user => user.role === 'admin' && user.status === 'active').length;
  list.innerHTML = state.adminUsers.length ? state.adminUsers.map(user => {
    const current = user.username === state.auth.identifier;
    const lifecycle = user.status === 'active' ? '停用' : '重新启用';
    const lifecycleAction = user.status === 'active' ? 'disable' : 'reactivate';
    const canDisableCurrentAdmin = current && user.role === 'admin' && activeAdminCount > 1;
    const lifecycleControl = current && lifecycleAction === 'disable' && !canDisableCurrentAdmin
      ? '<span class="muted">当前账户（唯一启用管理员不可停用）</span>'
      : `<button class="ghost" type="button" data-admin-action="${lifecycleAction}" data-user-id="${escapeHtml(user.id)}">${lifecycle}</button>`;
    return `<article class="admin-user-row"><div class="admin-user-meta"><strong>${escapeHtml(user.username)}</strong><span>${escapeHtml(user.role === 'admin' ? '管理员' : '成员')} · ${escapeHtml(user.status === 'active' ? '启用' : '已停用')}${user.email ? ` · ${escapeHtml(user.email)}` : ''}</span></div><div class="admin-user-actions">${lifecycleControl}<button class="ghost" type="button" data-admin-action="reset" data-user-id="${escapeHtml(user.id)}">重置密码</button></div></article>`;
  }).join('') : '<div class="loading-row">暂无账户</div>';
}
function renderAuthIdentity() {
  const identity = qs('#accountIdentity');
  if (identity) {
    const visible = state.sessionActive && state.auth.identifier !== null && state.auth.role !== null;
    identity.textContent = visible ? `${state.auth.identifier} · ${state.auth.role === 'admin' ? '管理员' : '成员'}` : '';
    identity.classList.toggle('hidden', !visible);
  }
  renderAdminAccounts();
}
async function refreshAuthIdentity() {
  const response = await fetch('/api/auth/me', {credentials:'same-origin'});
  const auth = response.ok ? await response.json() : {authenticated:false};
  state.sessionActive = Boolean(auth.authenticated);
  state.auth = {
    identifier: typeof auth.identifier === 'string' && auth.identifier ? auth.identifier : null,
    role: auth.role === 'admin' || auth.role === 'member' ? auth.role : null,
  };
  renderAuthIdentity();
  return auth;
}
async function loadAdminUsers() {
  if (!isEnrolledAdmin()) return;
  try {
    state.adminUsers = await api('/api/admin/users');
    renderAdminAccounts();
  } catch (error) {
    if (error.message !== 'unauthorized') setAdminAccountStatus(`读取账户失败：${error.message}`, true);
  }
}
function openAdminPasswordReset(userId) {
  if (!isEnrolledAdmin()) return;
  const user = state.adminUsers.find(item => Number(item.id) === Number(userId));
  if (!user) return;
  setAdminAccountStatus();
  qs('#adminResetUserId').value = String(user.id);
  qs('#adminResetTarget').textContent = `重置 ${user.username} 的密码`;
  const form = qs('#adminResetPasswordForm');
  form.reset();
  qs('#adminResetUserId').value = String(user.id);
  form.classList.remove('hidden');
  qs('input[name="password"]', form).focus();
}
async function submitAdminCreate(event) {
  event.preventDefault();
  if (!isEnrolledAdmin()) return;
  setAdminAccountStatus();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  if (!payload.email) payload.email = null;
  try {
    await api('/api/admin/users', {method:'POST', body:JSON.stringify(payload)});
    form.reset();
    setAdminAccountStatus('账户已创建。');
    await loadAdminUsers();
  } catch (error) { setAdminAccountStatus(`创建账户失败：${error.message}`, true); }
}
async function submitAdminPasswordReset(event) {
  event.preventDefault();
  if (!isEnrolledAdmin()) return;
  setAdminAccountStatus();
  const form = event.currentTarget;
  const userId = Number(qs('#adminResetUserId').value);
  const password = String(new FormData(form).get('password') || '');
  if (!Number.isInteger(userId) || !password) return;
  try {
    await api(`/api/admin/users/${encodeURIComponent(userId)}/reset-password`, {method:'POST', body:JSON.stringify({password})});
    form.reset(); form.classList.add('hidden');
    setAdminAccountStatus('密码已重置；该账户需要重新登录。');
    await loadAdminUsers();
  } catch (error) { setAdminAccountStatus(`重置密码失败：${error.message}`, true); }
}
async function runAdminLifecycleAction(event) {
  const control = event.target.closest('[data-admin-action]');
  if (!control || !isEnrolledAdmin()) return;
  const userId = Number(control.dataset.userId);
  const action = control.dataset.adminAction;
  if (!Number.isInteger(userId) || !['disable', 'reactivate'].includes(action)) return;
  const selfDisable = action === 'disable' && state.adminUsers.some(user => Number(user.id) === userId && user.username === state.auth.identifier);
  setAdminAccountStatus(); control.disabled = true;
  try {
    await api(`/api/admin/users/${encodeURIComponent(userId)}/${action}`, {method:'POST', body:JSON.stringify({})});
    if (selfDisable) {
      state.sessionActive = false;
      advanceAuthRequestGeneration();
      showAuth('当前账户已停用，登录会话已失效。');
      return;
    }
    setAdminAccountStatus(action === 'disable' ? '账户已停用，现有会话已撤销。' : '账户已重新启用；需重新登录。');
    await loadAdminUsers();
  } catch (error) { setAdminAccountStatus(`账户操作失败：${error.message}`, true); }
  finally { control.disabled = false; }
}
function parseImportDecimal(value, contract) {
  const text = value === null || value === undefined ? '' : String(value).trim();
  if (!text) return {valid:false, reason:'必填数值不能为空'};
  const rule = contract || {maximum:'1000000000', scale:6};
  if (!/^\d+(?:\.\d+)?$/.test(text)) return {valid:false, reason:'只能填写非负十进制数字'};
  const [wholePart, fractionPart = ''] = text.split('.');
  if (fractionPart.length > rule.scale) return {valid:false, reason:`最多 ${rule.scale} 位小数`};
  const factor = 10n ** BigInt(rule.scale);
  const whole = BigInt(wholePart);
  const fraction = BigInt((fractionPart || '').padEnd(rule.scale, '0') || '0');
  const scaled = whole * factor + fraction;
  const maximumParts = String(rule.maximum).split('.');
  const maximum = BigInt(maximumParts.join('')) * (10n ** BigInt(rule.scale - (maximumParts[1]?.length || 0)));
  if (scaled > maximum) return {valid:false, reason:`不能超过 ${rule.maximum}`};
  return {valid:true, value:text};
}
function importCandidateValidation(candidate) {
  const reasons = [];
  if (!candidate.selected_code) reasons.push('请选择已配置代码');
  for (const [field, contract] of Object.entries(IMPORT_DECIMAL_CONTRACTS)) {
    const value = candidate[field];
    if (field === 'target_weight' && (value === null || value === undefined || value === '')) continue;
    const result = parseImportDecimal(value, contract);
    if (!result.valid) reasons.push(`${IMPORT_FIELD_LABELS[field] || field}：${result.reason}`);
  }
  return reasons;
}
function importWorkflowHasPendingSaves() {
  return state.pendingSaveTimers.size > 0 || state.inflightSavePromises.size > 0 || state.importSaveErrors.size > 0;
}
function validateImportPayload(payload) {
  const reasons = [];
  for (const [field, contract] of Object.entries(IMPORT_DECIMAL_CONTRACTS)) {
    const value = payload[field];
    if (field === 'target_weight' && (value === null || value === undefined || value === '')) continue;
    const result = parseImportDecimal(value, contract);
    if (!result.valid) reasons.push(`${IMPORT_FIELD_LABELS[field] || field}：${result.reason}`);
  }
  return reasons;
}
function authRequestGeneration() { return state.authRequestGeneration; }
function abortAuthRequests() {
  state.bootstrapController?.abort(); state.bootstrapController = null;
  state.settingsController?.abort(); state.settingsController = null;
  state.eventAbort?.abort(); state.eventAbort = null; clearTimeout(state.eventRetry); state.eventRetry = null;
}
function advanceAuthRequestGeneration() {
  state.authRequestGeneration += 1;
  abortAuthRequests();
  newImportGeneration();
  resetImportWorkflow({advance:false});
  return state.authRequestGeneration;
}
function resetImportWorkflow({advance = true} = {}) {
  if (advance) newImportGeneration(); else abortImportRequests();
  state.holdingImport = null;
  qs('#portfolioImportCandidates')?.replaceChildren(); qs('#portfolioImportReview')?.classList.add('hidden');
  qs('#portfolioImportProgress')?.classList.add('hidden'); qs('#portfolioImportError').textContent = '';
  qs('#portfolioConfirmError').textContent = ''; qs('#portfolioImportFile').value = '';
  qs('#portfolioImportStatus').textContent = '等待选择截图'; qs('#portfolioImportUploadButton').disabled = false;
  qs('#portfolioCancelButton').disabled = false; qs('#portfolioConfirmButton').disabled = true; qs('#portfolioConfirmButton').setAttribute('aria-disabled', 'true');
  qs('#portfolioConfirmYes').disabled = false; renderCloudReview();
}
function setImportInteractionDisabled(disabled) {
  qs('#portfolioImportUploadButton').disabled = disabled;
  qs('#portfolioCancelButton').disabled = disabled;
  qs('#portfolioConfirmButton').disabled = disabled || qs('#portfolioConfirmButton').disabled;
  qsa('#portfolioImportCandidates [data-import-field], #portfolioImportCandidates .import-reject').forEach(control => { control.disabled = disabled; });
}

function showAuth(error = '') {
  if (!state.sessionActive) {
    state.auth = {identifier: null, role: null};
    renderAuthIdentity();
  }
  qs('#authOverlay').classList.remove('hidden');
  qs('#authError').textContent = error;
  qs('#passwordInput').value = '';
  setTimeout(() => qs('#identifierInput').focus(), 30);
}
function hideAuth() { qs('#authOverlay').classList.add('hidden'); }
function openModal(id, focusSelector = '.modal-close') {
  const overlay = qs(`#${id}`);
  state.modalReturnFocus = document.activeElement;
  overlay.classList.remove('hidden');
  const focusTarget = qs(focusSelector, overlay) || qs('.modal-close', overlay);
  if (focusTarget) focusTarget.focus();
}
function closeModal(id) {
  qs(`#${id}`)?.classList.add('hidden');
  if (id === 'detailOverlay') { cancelDetailRequest(); state.decisionUi.openDetailCode = null; state.decisionUi.openDetailSnapshotId = null; }
  if (state.modalReturnFocus && typeof state.modalReturnFocus.focus === 'function') state.modalReturnFocus.focus();
  state.modalReturnFocus = null;
}

function cancelDetailRequest() {
  state.detailRequestToken += 1;
  if (state.detailRequestController) state.detailRequestController.abort();
  state.detailRequestController = null;
  clearTimeout(state.resizeTimer);
}

function requestDetailBars(code) {
  if (state.demoMode || state.modeTransition) return;
  if (!code || qs('#detailOverlay').classList.contains('hidden')) return;
  cancelDetailRequest();
  const requestToken = state.detailRequestToken;
  const modeGeneration = state.modeGeneration;
  const controller = new AbortController();
  state.detailRequestController = controller;
  api(`/api/instruments/${encodeURIComponent(code)}/bars?limit=220`, {signal: controller.signal})
    .then(bars => {
      if (requestToken === state.detailRequestToken && modeGeneration === state.modeGeneration && !state.modeTransition && state.detailCode === code && !qs('#detailOverlay').classList.contains('hidden')) drawChart(bars);
    })
    .catch(error => {
      if (error.name !== 'AbortError' && requestToken === state.detailRequestToken && modeGeneration === state.modeGeneration && !state.modeTransition) toast(`K线加载失败：${error.message}`);
    });
}

function scheduleDetailBars(code, delay = 120) {
  clearTimeout(state.resizeTimer);
  state.resizeTimer = setTimeout(() => requestDetailBars(code), delay);
}

function trapModalFocus(event) {
  if (event.key !== 'Tab' || event.currentTarget.classList.contains('hidden')) return;
  const focusable = qsa('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', event.currentTarget);
  if (!focusable.length) return;
  const first = focusable[0], last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

async function loadBootstrap(silent = false) {
  if (state.modeTransition && !(state.modeTransition.target === 'formal' && !state.demoMode)) return;
  if (state.demoMode) return loadDemoBootstrap(silent);
  const requestGeneration = authRequestGeneration(), sessionActive = state.sessionActive, controller = new AbortController();
  const modeGeneration = state.modeGeneration;
  state.bootstrapController?.abort(); state.bootstrapController = controller;
  if (!silent) qs('#refreshButton').disabled = true;
  try {
    const bootstrap = await api('/api/bootstrap', {signal:controller.signal, authGeneration:requestGeneration});
    let reports = [];
    try {
      reports = await api('/api/reports', {signal:controller.signal, authGeneration:requestGeneration});
    } catch (reportError) {
      console.warn('report list unavailable', reportError);
    }
    if (requestGeneration !== authRequestGeneration() || sessionActive !== state.sessionActive || controller.signal.aborted || !modeRequestCurrent(modeGeneration, false)) return;
    state.data = bootstrap;
    state.reports = reports;
    state.signalGrade = null;
    state.boards = null;
    hideAuth();
    renderAll();
    loadDecisionBoard(true);
    scheduleDecisionStatusPoll();
    scheduleBrowserRefresh();
  } catch (error) {
    if (error.name !== 'AbortError' && requestGeneration === authRequestGeneration() && sessionActive === state.sessionActive && modeRequestCurrent(modeGeneration, false)) toast(`刷新失败：${error.message}`, 5000);
  } finally {
    if (state.bootstrapController === controller) { state.bootstrapController = null; syncDecisionRefreshButton(); }
  }
}

async function loadDemoBootstrap(silent = false) {
  if (state.modeTransition && state.modeTransition.target !== 'demo') return;
  const requestGeneration = authRequestGeneration(), sessionActive = state.sessionActive;
  const modeGeneration = state.modeGeneration, controller = new AbortController();
  state.demoBootstrapController?.abort(); state.demoBootstrapController = controller;
  if (!silent) qs('#refreshButton').disabled = true;
  try {
    const bootstrap = await api('/api/demo/bootstrap', {authGeneration: requestGeneration, signal: controller.signal});
    if (requestGeneration !== authRequestGeneration() || sessionActive !== state.sessionActive || !modeRequestCurrent(modeGeneration, true)) return;
    state.data = bootstrap;
    state.reports = [];
    state.signalGrade = bootstrap.signal_grade || null;
    state.boards = bootstrap.boards || null;
    hideAuth();
    renderCurrentView();
  } catch (error) {
    if (error.name !== 'AbortError' && error.message !== 'unauthorized' && modeRequestCurrent(modeGeneration, true)) toast(`演示数据刷新失败：${error.message}`, 5000);
  } finally { if (state.demoBootstrapController === controller) state.demoBootstrapController = null; if (!silent) qs('#refreshButton').disabled = false; }
}

async function enterDemoMode() {
  const generation = beginModeTransition('demo');
  if (generation == null) return;
  let succeeded = false;
  try {
    const result = await api('/api/demo/load', {method:'POST', body:JSON.stringify({})});
    if (generation !== state.modeGeneration || state.modeTransition?.target !== 'demo') return;
    state.demoMode = true;
    const demoRadio = qs('input[name="market_data_tier"][value="demo"]');
    if (demoRadio) demoRadio.checked = true;
    state.data = result;
    state.decisionBoard = null;
    state.reports = [];
    state.signalGrade = result.signal_grade || null;
    state.boards = result.boards || null;
    renderCurrentView();
    succeeded = true;
    toast('演示数据已加载：不访问外网、不写生产数据库');
  } catch (error) {
    if (generation === state.modeGeneration) toast(`加载演示失败：${error.message}`, 5000);
  } finally {
    if (generation === state.modeGeneration) {
      if (!succeeded) {
        state.demoMode = false;
        scheduleBrowserRefresh();
      }
      endModeTransition(generation);
      renderSourceBadge(state.data || {});
      if (!succeeded) restartFormalEvents();
    }
  }
}

async function resetDemoMode() {
  const generation = beginModeTransition('demo');
  if (generation == null) return;
  try {
    const result = await api('/api/demo/reset', {method:'POST', body:JSON.stringify({})});
    if (generation !== state.modeGeneration || state.modeTransition?.target !== 'demo') return;
    state.demoMode = true;
    const demoRadio = qs('input[name="market_data_tier"][value="demo"]');
    if (demoRadio) demoRadio.checked = true;
    state.data = result;
    state.reports = [];
    state.signalGrade = result.signal_grade || null;
    state.boards = result.boards || null;
      renderCurrentView();
    toast('演示数据已重置');
  } catch (error) {
    if (generation === state.modeGeneration) toast(`重置演示失败：${error.message}`, 5000);
  } finally {
    if (generation === state.modeGeneration) endModeTransition(generation);
  }
}

async function exitDemoMode() {
  const generation = beginModeTransition('formal');
  if (generation == null) return;
  try {
    await api('/api/demo/reset', {method:'POST', body:JSON.stringify({})});
    if (generation !== state.modeGeneration) return;
    state.demoMode = false;
    state.signalGrade = null;
    state.boards = null;
    // Refresh the formal tier after leaving DEMO while the transition lock is
    // still active. A failed read never re-enters DEMO.
    await loadSettings();
    if (state.settings) applyMarketSettings(state.settings);
    await loadBootstrap();
    if (state.data?.demo === true) throw new Error('正式看板加载未完成');
    if (generation === state.modeGeneration) toast('已退出演示，已恢复正式数据');
  } catch (error) {
    // Keep the already-loaded DEMO view coherent if reset or formal reload fails.
    if (generation === state.modeGeneration) {
      state.demoMode = true;
      state.signalGrade = state.data?.signal_grade || null;
      state.boards = state.data?.boards || null;
      toast(`退出演示失败：${error.message}`, 5000);
    }
  } finally {
    if (generation === state.modeGeneration) {
      if (state.demoMode) renderCurrentView();
      endModeTransition(generation);
      renderSourceBadge(state.data || {});
      if (!state.demoMode) {
        scheduleBrowserRefresh();
        restartFormalEvents();
      }
    }
  }
}

function scheduleBrowserRefresh() {
  clearInterval(state.refreshTimer);
  const minutes = Number(state.settings?.quote_refresh_minutes || 3);
  state.refreshTimer = setInterval(() => { if (!state.modeTransition) loadBootstrap(true); }, Math.max(1, minutes) * 60 * 1000);
}

function provenanceText(source, sourceTimestamp, fetchedAt, freshness, verification, degradedReason) {
  return `<div class="provenance-line"><span>来源 ${escapeHtml(source || '—')}</span><span>源时间 ${escapeHtml(timeText(sourceTimestamp))}</span><span>抓取 ${escapeHtml(timeText(fetchedAt))}</span><span>新鲜度 ${escapeHtml(freshness || 'unavailable')}</span><span>验证 ${escapeHtml(verification || 'unverified')}</span>${degradedReason ? `<span class="provenance-warning">${escapeHtml(degradedReason)}</span>` : ''}</div>`;
}

function quoteFreshness(quote) {
  if (quote?.freshness) return quote.freshness;
  if (quote?.degraded_reason || quote?.is_mock) return 'degraded';
  if (quote?.is_realtime) return 'fresh';
  return 'unavailable';
}

function quoteStateLabel(quote) {
  if (quote?.is_mock) return 'Mock · degraded';
  if (quoteFreshness(quote) === 'stale') return 'stale';
  if (quoteFreshness(quote) === 'degraded') return 'degraded';
  if (quoteFreshness(quote) === 'unavailable') return 'unavailable';
  return quote?.verification_status || 'unverified';
}

function contextObservation(item) {
  return item?.observation || item || {};
}

function contextStatus(item, observation) {
  if (!item?.enabled) return 'unavailable · disabled';
  if (item.verification_status !== 'verified') return 'unverified';
  if (!observation || (observation.degraded || ['degraded', 'unavailable'].includes(observation.freshness))) return observation?.is_mock ? 'Mock · degraded' : 'unavailable';
  if (observation.is_mock) return 'Mock · degraded';
  return observation.freshness || 'verified';
}

function marketContextCard(item) {
  const observation = contextObservation(item);
  const hasObservation = Boolean(item?.observation) || (item?.observed_value !== null && item?.observed_value !== undefined);
  const status = contextStatus(item, hasObservation ? observation : null);
  const value = observation.today_pct_change;
  const level = observation.observed_value ?? observation.price;
  const code = item.display_code || item.source_symbol;
  const unavailable = value === null || value === undefined;
  const tone = escapeHtml(unavailable ? 'neutral' : colorClass(value));
  return `<article class="context-card observed-card" role="listitem">
    <div class="context-card-head"><div class="context-identity">${displayIdentity(code, item.label)}</div><span class="status-badge ${status.includes('unavailable') || status.includes('unverified') ? 'status-muted' : ''}">${escapeHtml(status)}</span></div>
    <div class="context-region">${escapeHtml(item.region || '—')} · ${escapeHtml(item.context_kind || 'context')}</div>
    <div class="context-value ${tone}"><span class="context-value-label">今日涨跌</span><strong>${unavailable ? '—' : escapeHtml(pct(value))}</strong></div>
    <div class="context-level"><span>水平 / 价格</span><strong>${escapeHtml(fmt(level, 4))}</strong></div>
    ${provenanceText(observation.source, observation.source_timestamp, observation.fetched_at, observation.freshness || status, observation.verification_status || item.verification_status, observation.degraded_reason)}
  </article>`;
}

function mergeMarketContext(items) {
  const incoming = Array.isArray(items) ? items : [];
  const byId = new Map(incoming.filter(item => item && item.context_id).map(item => [item.context_id, item]));
  const defaults = DEFAULT_MARKET_CONTEXT.map(item => ({...item, ...(byId.get(item.context_id) || {})}));
  const standardIds = new Set(DEFAULT_MARKET_CONTEXT.map(item => item.context_id));
  const extras = incoming
    .filter(item => item && item.context_id && !standardIds.has(item.context_id))
    .map(item => ({...item}))
    .sort((a, b) => Number(a.display_order || 0) - Number(b.display_order || 0));
  return [...defaults, ...extras];
}

function renderMarketContext() {
  const node = qs('#marketContextCards');
  if (!node) return;
  const rows = mergeMarketContext(state.data?.market_context);
  node.innerHTML = rows.map(marketContextCard).join('');
}

function renderSummary() {
  const s = state.data.summary;
  const states = s.state_counts || {};
  const items = [
    ['观察标的', s.instrument_count, `数据源 ${s.provider}`],
    ['实时行情', s.live_quote_count, `最近 ${timeText(s.last_quote_time)}`],
    ['可入场 / 试探', (states['可入场'] || 0) + (states['可试探'] || 0), `入场 ${states['可入场'] || 0}`],
    ['加仓 / 持有', (states['加仓'] || 0) + (states['小幅加仓'] || 0) + (states['持有'] || 0), `持有 ${states['持有'] || 0}`],
    ['减仓 / 风险', (states['减仓'] || 0) + (states['风险观察'] || 0), `减仓 ${states['减仓'] || 0}`],
    ['上涨 / 下跌', `${s.market_width.up}/${s.market_width.down}`, `平 ${s.market_width.unchanged}`],
  ];
  qs('#summaryCards').innerHTML = items.map(([label, value, sub]) => `<div class="summary-card"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div><div class="sub">${escapeHtml(sub)}</div></div>`).join('');
  qs('#lastUpdated').textContent = `页面生成 ${timeText(state.data.generated_at)} · 信号 ${timeText(s.last_signal_time)}`;
  qs('#environmentLabel').textContent = `${s.app_env || 'research'} · ${state.demoMode ? 'DEMO' : (s.provider || 'unavailable')}`;
  renderSourceBadge(state.data);
  const warning = qs('#globalWarning');
  if (s.is_mock || s.live_quote_count < s.instrument_count) {
    warning.textContent = state.demoMode
      ? '当前为 DEMO 隔离 Mock 数据：不访问外网、不写生产数据库，所有结论均不可用于真实投资判断。'
      : s.is_mock
        ? '当前正式看板配置为 Mock 数据源：这不是隔离 DEMO，结果仅供测试；请到系统页使用“加载演示数据”验证功能。'
        : `仅 ${s.live_quote_count}/${s.instrument_count} 个标的具备执行级实时行情；退化数据会压低置信度并阻断操作级信号。`;
    warning.classList.remove('hidden');
  } else warning.classList.add('hidden');
}

function actualSource(data) {
  if (data?.demo === true) return 'DEMO';
  const sources = new Set();
  let hasCurrentQuoteProvenance = false;
  let hasUnknownCurrentSource = false;
  const addSource = value => {
    const source = String(value || '').toLowerCase();
    if (source.includes('tushare')) sources.add('Tushare');
    else if (source.includes('ftshare')) sources.add('FTShare');
    else if (source.includes('akshare')) sources.add('AKShare');
    else if (source) hasUnknownCurrentSource = true;
  };
  for (const row of (data?.instruments || [])) {
    if (row?.quote?.source) hasCurrentQuoteProvenance = true;
    addSource(row?.quote?.source);
  }
  if (hasCurrentQuoteProvenance) {
    if (hasUnknownCurrentSource) return 'unavailable';
    if (sources.size === 1) return [...sources][0];
    if (sources.size > 1) return 'fallback';
    return 'unavailable';
  }
  if (sources.size === 1) return [...sources][0];
  if (sources.size > 1) return 'fallback';
  // A formal empty view has no current quote provenance. Use only the latest
  // successful audit row as a weak source hint; failed/stale history must not
  // masquerade as the current provider.
  const latestSuccess = (data?.provider_health || []).find(item => ['ok', 'fallback_used'].includes(item?.status));
  if (latestSuccess?.status === 'fallback_used') return 'fallback';
  if (latestSuccess) {
    addSource(latestSuccess.provider);
    if (sources.size === 1) return [...sources][0];
  }
  return 'unavailable';
}
function renderSourceBadge(data) {
  const node = qs('#sourceBadge');
  if (!node) return;
  const source = actualSource(data);
  node.textContent = `来源 ${source === 'unavailable' ? '不可用' : source}`;
  node.className = `source-badge ${source === 'DEMO' ? 'demo' : source === 'fallback' ? 'fallback' : source === 'unavailable' ? 'unavailable' : 'verified'}`;
  const banner = qs('#demoBanner');
  if (banner) banner.classList.toggle('hidden', source !== 'DEMO');
  const status = qs('#demoStatus');
  if (status) {
    status.textContent = source === 'DEMO' ? `已进入演示 · ${data?.status_label || '演示数据'}` : '未进入演示';
    status.classList.toggle('status-muted', source !== 'DEMO');
  }
  const exit = qs('#demoExitButton');
  if (exit) exit.disabled = source !== 'DEMO';
  const demo = source === 'DEMO';
  const locked = demo || Boolean(state.modeTransition);
  const selectors = [
    '#newHoldingButton', '#portfolioImportButton', '#newsRefreshButton', '#generateReportButton',
    '#coefficientSave', '#settingsForm button', '#marketSourceForm button:not(#demoLoadButton)',
    '#tushareTokenInput', '#settingsForm input', '#boardAddForm input', '#boardAddForm select',
    '#boardAddForm button', '#portfolioImportForm input', '#portfolioImportForm button',
    '#portfolioConfirmButton', '#portfolioCancelButton', '.edit-holding', '.delete-holding',
    '.download-report', '.task-run', '#holdingForm button[type="submit"]',
  ];
  selectors.forEach(selector => qsa(selector).forEach(control => { control.disabled = locked; }));
  // The demo radio is a view switch, not a formal setting and must remain usable.
  const demoRadio = qs('input[name="market_data_tier"][value="demo"]');
  if (demoRadio) demoRadio.disabled = Boolean(state.modeTransition);
  ['#demoLoadButton', '#demoResetButton', '#demoExitButton', '#demoBannerExitButton'].forEach(selector => {
    qsa(selector).forEach(control => { control.disabled = Boolean(state.modeTransition); });
  });
  if (state.modeTransition) {
    const status = qs('#demoStatus');
    if (status) status.textContent = '模式切换中…';
  }
}

function renderNarrative() {
  if (state.demoMode && !(state.data?.instruments || []).length) {
    qs('#marketNarrative').textContent = '演示数据尚未加载。请到「系统」点击“加载演示数据”。';
    return;
  }
  const boards = state.boards;
  const scored = [...(boards?.industry || [])].filter(item => item.score != null).sort((a, b) => b.score - a.score);
  if (scored.length) {
    const top = scored.slice(0, 4).map(item => `${item.name}（${item.score}）`).join('、');
    qs('#marketNarrative').innerHTML = `<strong>行业ETF代理得分领先：</strong>${escapeHtml(top)}。分数由量能/均线/MACD/KDJ/RSI/九转/近周系数加权，研究提示非操作指令。无K线的板块显示未验证。`;
    return;
  }
  const rows = state.data.instruments || [];
  const usable = rows.filter(r => r.signal);
  if (!usable.length) { qs('#marketNarrative').textContent = '尚未生成信号。请打开「系统」运行完整流水线以写入日线；上方行业/概念卡片在无K线时仍会列出目录。'; return; }
  const strongest = [...usable].sort((a,b) => b.signal.score - a.signal.score).slice(0,3);
  const weakest = [...usable].sort((a,b) => a.signal.score - b.signal.score).slice(0,2);
  const stateCounts = state.data.summary.state_counts || {};
  const up = state.data.summary.market_width.up;
  const down = state.data.summary.market_width.down;
  qs('#marketNarrative').innerHTML = `
    <strong>市场宽度：</strong>${escapeHtml(up)} 涨 / ${escapeHtml(down)} 跌。当前信号以 <strong>${escapeHtml(Object.entries(stateCounts).sort((a,b)=>b[1]-a[1])[0]?.[0] || '暂无')}</strong> 为主。
    <strong>相对领先：</strong>${strongest.map(r => `${escapeHtml(r.name)}（${escapeHtml(fmt(r.signal.score,1))}）`).join('、')}。
    <strong>风险靠前：</strong>${weakest.map(r => `${escapeHtml(r.name)}（${escapeHtml(fmt(r.signal.score,1))}）`).join('、')}。
    所有预测均显示样本支持和区间；未校准预测不会获得高置信度。`;
}

function forecastCell(item) {
  const f = item || {};
  const hasCorridor = numericValue(f.path_low_price_q50) && numericValue(f.path_high_price_q50);
  const corridor = hasCorridor ? `
    <div class="forecast-corridor">
      <div>终点收盘 80%：${escapeHtml(fmt(f.terminal_price_q10,4))} ～ ${escapeHtml(fmt(f.terminal_price_q90,4))}</div>
      <div>路径支撑区：${escapeHtml(fmt(f.path_low_price_q10,4))} ～ ${escapeHtml(fmt(f.path_low_price_q90,4))}</div>
      <div>路径压力区：${escapeHtml(fmt(f.path_high_price_q10,4))} ～ ${escapeHtml(fmt(f.path_high_price_q90,4))}</div>
      <div>走廊位置 ${escapeHtml(fmt(f.corridor_position,1))}/100 · 触支撑 ${escapeHtml(pct(f.support_touch_probability,1,true))} · 触压力 ${escapeHtml(pct(f.resistance_touch_probability,1,true))}</div>
    </div>` : '<div class="forecast-meta">价格走廊不可用</div>';
  return `<div class="forecast-surface" aria-label="FORECAST · 非实际结果">
    <div class="forecast-label">FORECAST · 非实际结果 · 未校准</div>
    <div class="forecast-horizon">${escapeHtml(f.horizon == null ? '—' : `${f.horizon}日`)}</div>
    <div class="forecast-value">p(up) ${escapeHtml(f.p_up == null ? '—' : pct(f.p_up, 1, true))}</div>
    <div class="forecast-range">E[r] ${escapeHtml(pct(f.expected_return, 2, true))} · q10/q50/q90 ${escapeHtml(pct(f.q10, 2, true))} / ${escapeHtml(pct(f.q50, 2, true))} / ${escapeHtml(pct(f.q90, 2, true))}</div>
    ${corridor}
    <div class="forecast-meta">n=${escapeHtml(f.sample_count == null ? '—' : f.sample_count)} · ${escapeHtml(f.calibration_status || 'not_calibrated')} · ${escapeHtml(f.model_version || '—')}</div>
    <div class="forecast-meta">${escapeHtml(f.interval_method || 'empirical')} · schema ${escapeHtml(f.feature_schema_version || '—')}</div>
    <div class="forecast-meta">as_of ${escapeHtml(timeText(f.as_of_date))} · data_cutoff ${escapeHtml(timeText(f.data_cutoff))} · generated ${escapeHtml(timeText(f.generated_at))}</div>
  </div>`;
}
function instrumentRow(row) {
  const q = row.quote || {};
  const i = row.indicator || {};
  const v = i.values || {};
  const s = row.signal || {};
  const f = row.forecasts || {};
  const expired = s.expires_at && new Date(s.expires_at) < new Date();
  return `<tr class="clickable ${expired ? 'signal-expired' : ''}" tabindex="0" role="button" aria-label="打开 ${displayIdentity(row.ts_code, row.name)}" data-code="${escapeHtml(row.ts_code)}">
    <td><div class="instrument-name">${displayIdentity(row.ts_code, row.name)}</div><div class="instrument-meta">${escapeHtml(row.theme_l1 || '未分类')}/${escapeHtml(row.theme_l2 || '-')}</div></td>
    <td class="observed-surface quote-cell"><div class="metric-main quote-change ${escapeHtml(colorClass(q.pct_change))}">${escapeHtml(pct(q.pct_change))}</div><div class="metric-sub quote-price">价格 ${escapeHtml(fmt(q.price,4))}</div><div class="quote-state-badge ${escapeHtml(q.is_mock ? 'is-mock' : quoteFreshness(q))}">${escapeHtml(quoteStateLabel(q))}</div>${provenanceText(q.source, q.source_timestamp || q.time, q.fetched_at, quoteFreshness(q), q.verification_status || 'unverified', q.degraded_reason)}</td>
    <td><div class="metric-main">${escapeHtml(amountText(q.amount))}</div><div class="metric-sub">量比 ${escapeHtml(fmt(v.volume_ratio,2))}</div></td>
    <td><div class="metric-main">${escapeHtml(i.trend_label || '—')}</div><div class="metric-sub">技术 ${escapeHtml(fmt(i.technical_score,1))} / 风险 ${escapeHtml(fmt(i.risk_score,1))}</div></td>
    <td><div class="metric-main ${escapeHtml(Number(v.macd_hist || 0)>=0?'up':'down')}">${escapeHtml(fmt(v.macd_hist,6))}</div><div class="metric-sub">DIF ${escapeHtml(fmt(v.macd_dif,5))} / DEA ${escapeHtml(fmt(v.macd_dea,5))}</div></td>
    <td><div class="metric-main">J ${escapeHtml(fmt(v.kdj_j,1))}</div><div class="metric-sub">K ${escapeHtml(fmt(v.kdj_k,1))} / D ${escapeHtml(fmt(v.kdj_d,1))}</div></td>
    <td><div class="metric-main">${escapeHtml(fmt(v.rsi14,1))}</div><div class="metric-sub">6:${escapeHtml(fmt(v.rsi6,1))} / 12:${escapeHtml(fmt(v.rsi12,1))}</div></td>
    <td><div class="metric-main">${escapeHtml(v.td_buy_setup ?? '—')} / ${escapeHtml(v.td_sell_setup ?? '—')}</div><div class="metric-sub">买 / 卖设置</div></td>
    <td><div class="metric-main ${escapeHtml(colorClass(v.return_20d))}">${escapeHtml(pct(v.return_20d,2,true))}</div><div class="metric-sub">60日 ${escapeHtml(pct(v.return_60d,2,true))}</div></td>
    <td>${forecastCell(f['1'])}</td><td>${forecastCell(f['5'])}</td><td>${forecastCell(f['20'])}</td>
    <td><span class="badge ${escapeHtml(stateClass(s.state))}">${escapeHtml(s.state || '待计算')}</span><div class="metric-sub">分 ${escapeHtml(fmt(s.score,1))} · conf ${escapeHtml(fmt(s.confidence,1))}</div></td>
  </tr>`;
}
function renderInstruments() {
  return;
}

async function loadWatchlist() {
  try {
    const rows = await api('/api/watchlist');
    const node = qs('#watchlistList');
    if (!node) return;
    node.innerHTML = rows.length ? rows.map(r => `<div class="watchlist-item" style="display:flex;gap:8px;align-items:center;padding:4px 0"><strong>${escapeHtml(r.name || r.ts_code)}</strong><span class="muted">${escapeHtml(r.ts_code)}</span>${r.note?`<span class="muted">· ${escapeHtml(r.note)}</span>`:''}<span style="flex:1"></span><button class="small-button detail-jump" data-code="${escapeHtml(r.ts_code)}">详情</button><button class="small-button edit-holding" data-code="${escapeHtml(r.ts_code)}">转持仓</button><button class="small-button danger watchlist-remove" data-id="${r.id}">移除</button></div>`).join('') : '尚未添加自选。';
    qsa('#watchlistList .watchlist-remove').forEach(b => b.addEventListener('click', async () => {
      try { await api(`/api/watchlist/entries/${b.dataset.id}`, {method:'DELETE'}); await loadWatchlist(); toast('已移除自选'); } catch (e) { toast(`移除失败：${e.message}`); }
    }));
    qsa('#watchlistList .edit-holding').forEach(b => b.addEventListener('click', () => openHolding(b.dataset.code)));
    qsa('#watchlistList .detail-jump').forEach(b => b.addEventListener('click', () => { window.location.href = `/etf/${encodeURIComponent(b.dataset.code)}`; }));
  } catch (e) { /* 认证或网络失败时保留占位 */ }
}

async function addWatchlistEntry() {
  const input = qs('#watchlistCodeInput');
  const code = (input.value || '').trim();
  if (!code) { toast('请输入代码'); return; }
  try {
    const result = await api('/api/watchlist/entries', {method:'POST', body: JSON.stringify({code})});
    input.value = '';
    await loadWatchlist();
    toast(result.entry && result.entry.duplicate ? '该标的已在自选中' : '已添加自选');
  } catch (e) { toast(`添加失败：${e.message}`, 5000); }
}

function renderHoldings() {
  const holdings = state.data.holdings || [];
  const total = holdings.reduce((sum,h) => sum + Number(h.market_value || 0), 0);
  const pnl = holdings.reduce((sum,h) => sum + Number(h.pnl || 0), 0);
  const items = [
    ['持仓数量', holdings.length, 'ETF / LOF'],
    ['持仓市值', amountText(total), '按最新快照'],
    ['浮动盈亏', `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`, total ? `${(pnl/(total-pnl||1)*100).toFixed(2)}%` : '—'],
    ['现金 / 未分配', '未录入', '本版不推断现金余额'],
  ];
  qs('#holdingSummary').innerHTML = items.map(([l,v,s]) => `<div class="summary-card"><div class="label">${escapeHtml(l)}</div><div class="value">${escapeHtml(v)}</div><div class="sub">${escapeHtml(s)}</div></div>`).join('');
  qs('#holdingTable tbody').innerHTML = holdings.length ? holdings.map(h => `<tr><td><a class="instrument-name" href="/etf/${encodeURIComponent(h.ts_code)}">${displayIdentity(h.ts_code, h.name)}</a><div class="instrument-meta">${escapeHtml(h.theme_l1 || '未分类')}/${escapeHtml(h.theme_l2 || '-')}</div></td><td>${escapeHtml(fmt(h.shares,4))}</td><td>${escapeHtml(fmt(h.cost_price,4))}</td><td>${escapeHtml(fmt(h.latest_price,4))}</td><td>${escapeHtml(amountText(h.market_value))}</td><td class="${escapeHtml(colorClass(h.pnl))}">${escapeHtml(fmt(h.pnl,2))} / ${escapeHtml(holdingPnlPercent(h))}</td><td>${escapeHtml(fmt(h.current_weight*100,1))}%</td><td>${h.target_weight==null?'—':escapeHtml(fmt(h.target_weight*100,1))+'%'}</td><td>${escapeHtml(h.current_action||'—')}</td><td class="${escapeHtml(colorClass(h.forecasts&&h.forecasts['1']?h.forecasts['1'].expected_return:null))}">${escapeHtml(h.forecasts&&h.forecasts['1']?pct(h.forecasts['1'].expected_return,2,true):'—')}</td><td class="${escapeHtml(colorClass(h.forecasts&&h.forecasts['3']?h.forecasts['3'].expected_return:null))}">${escapeHtml(h.forecasts&&h.forecasts['3']?pct(h.forecasts['3'].expected_return,2,true):'—')}</td><td class="${escapeHtml(colorClass(h.forecasts&&h.forecasts['5']?h.forecasts['5'].expected_return:null))}">${escapeHtml(h.forecasts&&h.forecasts['5']?pct(h.forecasts['5'].expected_return,2,true):'—')}</td><td class="${escapeHtml(colorClass(h.forecasts&&h.forecasts['10']?h.forecasts['10'].expected_return:null))}">${escapeHtml(h.forecasts&&h.forecasts['10']?pct(h.forecasts['10'].expected_return,2,true):'—')}</td><td>${escapeHtml(fmt(h.nearest_support,3))}</td><td>${escapeHtml(fmt(h.nearest_resistance,3))}</td><td><button class="small-button edit-holding" data-code="${escapeHtml(h.ts_code)}">修改</button> <button class="small-button danger delete-holding" data-code="${escapeHtml(h.ts_code)}">删除</button></td></tr>`).join('') : '<tr class="loading-row"><td colspan="16">尚未录入持仓</td></tr>';
  qsa('.edit-holding').forEach(b => b.addEventListener('click', () => openHolding(b.dataset.code)));
  qsa('.delete-holding').forEach(b => b.addEventListener('click', () => deleteHolding(b.dataset.code)));
  syncHoldingOptions();
}

function syncHoldingOptions() {
  const overlay = qs('#holdingOverlay');
  if (!overlay.classList.contains('hidden')) return;
  const select = qs('#holdingCode');
  const selectedCode = select.value;
  select.innerHTML = (state.data.instruments || []).map(r => `<option value="${escapeHtml(r.ts_code)}">${displayIdentity(r.ts_code, r.name)}</option>`).join('');
  if ([...select.options].some(option => option.value === selectedCode)) select.value = selectedCode;
}

const IMPORT_EDITABLE_FIELDS = Object.freeze(['selected_code', 'name', 'shares', 'cost_price', 'target_weight', 'user_note']);
const IMPORT_STATUS_LABELS = Object.freeze({
  matched: '已匹配', ambiguous: '需明确选择', unmatched: '未匹配', low_confidence: '低置信度', duplicate: '重复候选',
  rejected: '已拒绝', pending: '待复核', reviewed: '已复核', confirmed: '已写入', saving: '保存中',
});
const IMPORT_FIELD_LABELS = Object.freeze({ts_code: '代码', name: '名称', shares: '份额', cost_price: '成本价', target_weight: '目标权重'});

function importCandidateValue(value) { return value === null || value === undefined ? '' : String(value); }
function importStatusLabel(value) { return IMPORT_STATUS_LABELS[value] || String(value || '待复核'); }
function importCandidate(candidate) {
  return {
    id: Number(candidate?.id), row_index: Number(candidate?.row_index ?? 0),
    ts_code: candidate?.ts_code == null ? null : String(candidate.ts_code), name: candidate?.name == null ? null : String(candidate.name),
    shares: candidate?.shares == null ? null : candidate.shares, cost_price: candidate?.cost_price == null ? null : candidate.cost_price,
    target_weight: candidate?.target_weight == null ? null : candidate.target_weight, user_note: candidate?.user_note == null ? null : String(candidate.user_note),
    match_status: String(candidate?.match_status || 'unmatched'), status: String(candidate?.status || 'pending'), action: String(candidate?.action || 'none'),
    selected_code: candidate?.selected_code == null ? null : String(candidate.selected_code),
    safe_alternatives: Array.isArray(candidate?.safe_alternatives) ? candidate.safe_alternatives.map(String) : [],
    field_confidence: Array.isArray(candidate?.field_confidence) ? candidate.field_confidence.map(item => ({field:String(item?.field || ''), confidence:item?.confidence})) : [],
  };
}
function importSession(payload) {
  const sessionId = typeof payload?.session_id === 'string' && /^[0-9a-f]{16,256}$/i.test(payload.session_id) ? payload.session_id : '';
  return {sessionId, session: {
    status: String(payload?.status || 'failed'), candidate_count: Number(payload?.candidate_count || 0), expires_at: payload?.expires_at || null,
    cloud_consent: Boolean(payload?.cloud_consent), ocr_mode: String(payload?.ocr_mode || 'local'), ocr_backend: String(payload?.ocr_backend || 'local'),
    ocr_model: String(payload?.ocr_model || '—'), ocr_version: String(payload?.ocr_version || '—'), candidates: Array.isArray(payload?.candidates) ? payload.candidates.map(importCandidate) : [],
  }, busy:false, uploadProgress:null, importBusy:false, importError:'', error:'', status:'就绪'};
}
function importAlternativeCodes(candidate) {
  const codes = new Set();
  for (const code of [candidate.selected_code, candidate.ts_code, ...(candidate.safe_alternatives || [])]) if (code) codes.add(String(code));
  for (const instrument of (state.data?.instruments || [])) if (instrument.ts_code) codes.add(String(instrument.ts_code));
  return [...codes].sort();
}
function importInstrumentName(code) { return (state.data?.instruments || []).find(item => item.ts_code === code)?.name || ''; }
function importCodeOptions(candidate) {
  const selected = importCandidateValue(candidate.selected_code || candidate.ts_code);
  return ['<option value="">请选择代码</option>', ...importAlternativeCodes(candidate).map(code => `<option value="${escapeHtml(code)}"${code === selected ? ' selected' : ''}>${displayIdentity(code, importInstrumentName(code))}</option>`)].join('');
}
function importWarning(candidate) {
  if (candidate.status === 'rejected') return '此行已明确拒绝，不会写入持仓。';
  return ({
    ambiguous: '存在多个可能标的；请明确选择，或拒绝此行。', unmatched: '服务端尚未解析到配置标的；请明确选择。',
    low_confidence: '识别置信度偏低；请人工核对代码、名称和数值。', duplicate: '此候选可能与其他行指向同一代码；确认前必须处理重复。',
  })[candidate.match_status] || '';
}
function renderImportCandidate(candidate) {
  const rejected = candidate.status === 'rejected' || candidate.action === 'reject';
  const badges = [candidate.match_status, candidate.status].filter(Boolean).map(status => {
    const safeStatus = IMPORT_STATUS_CLASS_ALLOWLIST[status] || 'pending';
    return `<span class="import-badge status-${safeStatus}">${escapeHtml(importStatusLabel(status))}</span>`;
  }).join('');
  const confidence = (candidate.field_confidence || []).map(item => `<span class="confidence-badge">${escapeHtml(IMPORT_FIELD_LABELS[item.field] || item.field)} ${escapeHtml(fmt(item.confidence, 2))}</span>`).join('');
  const disabled = rejected ? ' disabled' : '';
  const validation = rejected ? [] : [...importCandidateValidation(candidate), ...(state.importSaveErrors.get(candidate.id) ? [state.importSaveErrors.get(candidate.id)] : [])];
  return `<article class="candidate-card${rejected ? ' is-rejected' : ''}" role="listitem" data-candidate-id="${escapeHtml(candidate.id)}">
    <div class="candidate-card-head"><div><div class="candidate-row-title">第 ${escapeHtml(candidate.row_index + 1)} 行 · ${displayIdentity(candidate.selected_code || candidate.ts_code, candidate.name)}</div><div class="candidate-row-id">代码优先身份 · 服务端状态保留</div></div><div class="candidate-badges">${badges}</div></div>
    ${importWarning(candidate) ? `<div class="candidate-warning" role="note">${escapeHtml(importWarning(candidate))}</div>` : ''}
    ${validation.length ? `<div class="candidate-validation" role="alert">${validation.map(reason => escapeHtml(reason)).join(' · ')}</div>` : ''}
    <div class="candidate-fields">
      <label>选择代码<select data-import-field="selected_code"${disabled}>${importCodeOptions(candidate)}</select></label>
      <label>名称<input data-import-field="name" type="text" maxlength="128" value="${escapeHtml(importCandidateValue(candidate.name))}"${disabled}></label>
      <label>份额<input data-import-field="shares" type="number" min="0" step="0.0001" value="${escapeHtml(importCandidateValue(candidate.shares))}"${disabled}></label>
      <label>成本价<input data-import-field="cost_price" type="number" min="0" step="0.000001" value="${escapeHtml(importCandidateValue(candidate.cost_price))}"${disabled}></label>
      <label>目标权重（0-1，可空）<input data-import-field="target_weight" type="number" min="0" max="1" step="0.000001" value="${escapeHtml(importCandidateValue(candidate.target_weight))}"${disabled}></label>
      <label>用户备注<textarea data-import-field="user_note" maxlength="2000"${disabled}>${escapeHtml(importCandidateValue(candidate.user_note))}</textarea></label>
    </div>
    <div class="confidence-list" aria-label="字段置信度">${confidence || '<span class="muted">无字段置信度</span>'}</div>
    <div class="candidate-actions"><span class="candidate-save-state" aria-live="polite">${rejected ? '已拒绝' : '修改后自动保存'}</span>${rejected ? '' : '<button class="small-button danger import-reject" type="button">拒绝此行</button>'}</div>
  </article>`;
}
function importConfirmState() {
  const workflow = state.holdingImport, session = workflow?.session;
  if (!workflow || !session || workflow.busy || importWorkflowHasPendingSaves() || !['ready', 'editing'].includes(session.status)) return {ready:false, reason:'等待本地识别或保存完成'};
  if (!session.candidates.length) return {ready:false, reason:'没有可确认的候选，服务器不会创建持仓'};
  const seen = new Set();
  for (const candidate of session.candidates) {
    if (candidate.status === 'rejected') continue;
    const code = String(candidate.selected_code || '').trim().toUpperCase();
    if (candidate.status !== 'reviewed' || candidate.action !== 'none') return {ready:false, reason:'每一行都需要明确处理：选择代码、复核状态，或拒绝此行'};
    if (!code || seen.has(code)) return {ready:false, reason:'每一行都需要唯一的已配置代码；重复候选需明确处理'};
    const reasons = importCandidateValidation(candidate);
    if (reasons.length) return {ready:false, reason:reasons.join(' · ')};
    seen.add(code);
  }
  return {ready:true, reason:'所有未拒绝行已明确处理，可继续确认'};
}
function renderImportReview() {
  const workflow = state.holdingImport, review = qs('#portfolioImportReview');
  if (!workflow?.session) { review.classList.add('hidden'); return; }
  review.classList.remove('hidden');
  qs('#portfolioImportMeta').textContent = `${workflow.session.candidates.length} 行候选 · ${workflow.session.ocr_backend} · ${workflow.session.ocr_model}`;
  qs('#portfolioImportCandidates').innerHTML = workflow.session.candidates.length ? workflow.session.candidates.map(renderImportCandidate).join('') : '<div class="empty-state">未找到可复核候选；不会创建持仓。</div>';
  const gate = importConfirmState(), button = qs('#portfolioConfirmButton');
  button.disabled = !gate.ready; button.setAttribute('aria-disabled', String(!gate.ready)); qs('#portfolioConfirmReason').textContent = gate.reason;
  qs('#portfolioImportStatus').textContent = workflow.status || `状态：${workflow.session.status}`;
  if (workflow.canceling) setImportInteractionDisabled(true);
}
function renderCloudReview() {
  const panel = qs('#cloudReviewPanel'), enabled = state.cloudReviewEnabled === true;
  panel.classList.toggle('hidden', !enabled); panel.hidden = !enabled;
  if (enabled && state.holdingImport?.session) qs('#cloudReviewProvider').textContent = `${state.holdingImport.session.ocr_backend} / ${state.holdingImport.session.ocr_model}`;
}
function formatImportError(error) {
  if (error?.message === 'unauthorized') return '访问令牌已失效，请重新登录。';
  return ({413:'图片超过服务器大小限制。', 415:'仅支持 PNG、JPEG 或 WebP 图片。', 422:'图片或候选数据未通过服务器校验。', 503:'本地 OCR 暂不可用，请稍后重试。'})[error?.status] || '持仓截图导入失败，请检查后重试。';
}
function clearPortfolioImport() { resetImportWorkflow(); }
async function openPortfolioImport() {
  if (blockFormalMutation('持仓截图导入')) return;
  if (state.cancelPromise) await state.cancelPromise;
  if (state.holdingImport?.cancelError) { openModal('portfolioImportOverlay', '#portfolioCancelButton'); return; }
  resetImportWorkflow(); openModal('portfolioImportOverlay', '#portfolioImportFile'); renderCloudReview();
}
async function uploadPortfolioImport(event) {
  event.preventDefault(); const input = qs('#portfolioImportFile'), file = input.files?.[0];
  if (blockFormalMutation('持仓截图上传')) return;
  if (state.cancelPromise) { qs('#portfolioImportStatus').textContent = '等待取消请求完成后再开始新导入…'; await state.cancelPromise; return; }
  if (!file) { qs('#portfolioImportError').textContent = '请选择一张 PNG、JPEG 或 WebP 图片。'; return; }
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) qs('#portfolioImportError').textContent = 'MIME 类型仅作浏览器提示；服务器最终权威判定，仍会继续提交校验。';
  if (file.size > 10 * 1024 * 1024) { qs('#portfolioImportError').textContent = '浏览器提示：图片超过建议 10 MB；服务器限制优先，请选择较小图片。'; return; }
  const generation = newImportGeneration(); resetImportWorkflow({advance:false});
  state.holdingImport = {sessionId:'', session:null, generation, busy:true, uploadProgress:0, importBusy:true, importError:'', error:'', status:'上传并进行本地识别中…'}; qs('#portfolioImportStatus').textContent = '上传并进行本地识别中…'; qs('#portfolioImportProgress').setAttribute('aria-valuenow', '0'); qs('#portfolioImportProgress').classList.remove('hidden'); qs('#portfolioImportUploadButton').disabled = true;
  const body = new FormData(); body.append('file', file, 'portfolio-import');
  const controller = trackImportController(new AbortController());
  try {
    const workflow = importSession(await api('/api/holding-imports', {method:'POST', body, signal:controller.signal, authGeneration:authRequestGeneration()}));
    if (!isImportCurrent(generation) || controller.signal.aborted) return;
    if (!workflow.sessionId) throw Object.assign(new Error('invalid import session'), {status:422});
    workflow.generation = generation; workflow.uploadProgress = 100; state.holdingImport = workflow; renderImportReview(); renderCloudReview(); qs('#portfolioImportStatus').textContent = '本地识别完成，请逐行复核。'; qs('#portfolioImportProgress').setAttribute('aria-valuenow', '100'); qs('#portfolioImportProgress').classList.add('hidden');
  } catch (error) {
    if (!isImportCurrent(generation) || error?.name === 'AbortError') return;
    state.holdingImport.busy = false; state.holdingImport.importBusy = false; state.holdingImport.error = formatImportError(error); state.holdingImport.importError = state.holdingImport.error; qs('#portfolioImportStatus').textContent = '识别未完成'; qs('#portfolioImportError').textContent = state.holdingImport.error; qs('#portfolioImportProgress').classList.add('hidden'); qs('#portfolioImportUploadButton').disabled = false;
  } finally { untrackImportController(controller); }
}
function importPatchPayload(card) {
  const payload = {};
  for (const field of IMPORT_EDITABLE_FIELDS) {
    const control = qs(`[data-import-field="${field}"]`, card); if (!control) continue;
    const raw = control.value; payload[field] = raw === '' ? null : raw;
  }
  return payload;
}
function scheduleImportCandidateSave(card) {
  if (state.demoMode) return;
  const workflow = state.holdingImport; if (!workflow?.sessionId || workflow.canceling) return;
  const id = Number(card.dataset.candidateId), version = (state.importSaveVersions.get(id) || 0) + 1;
  state.importSaveVersions.set(id, version); state.importSaveErrors.delete(id); clearTimeout(state.pendingSaveTimers.get(id)?.timer);
  const payload = importPatchPayload(card), generation = state.importGeneration, sessionId = workflow.sessionId;
  const numericReasons = validateImportPayload(payload);
  if (numericReasons.length) { state.importSaveErrors.set(id, numericReasons.join(' · ')); const status = qs('.candidate-save-state', card); if (status) status.textContent = '数值待修正'; return; }
  const timer = setTimeout(() => flushCandidateSave(id, generation, sessionId, version), 280);
  state.pendingSaveTimers.set(id, {timer, payload, version, generation, sessionId, card});
  const status = qs('.candidate-save-state', card); if (status) status.textContent = '等待保存…';
}
async function flushCandidateSave(id, generation, sessionId, version) {
  const record = state.pendingSaveTimers.get(id);
  if (!record || record.version !== version) return false;
  if (!isImportCurrent(generation, sessionId)) return false;
  return enqueueSessionPatch(id, generation, sessionId, version);
}
function enqueueSessionPatch(id, generation, sessionId, version) {
  const existing = state.inflightSavePromises.get(id);
  if (existing && state.sessionQueuedVersions.get(id) >= version) return existing;
  const workflow = state.holdingImport;
  const run = async () => {
    if (!isImportCurrent(generation, sessionId)) return false;
    const latest = state.pendingSaveTimers.get(id);
    const sendRecord = latest && latest.version >= version ? latest : null;
    if (!sendRecord) return false;
    clearTimeout(sendRecord.timer); state.pendingSaveTimers.delete(id);
    const sendVersion = sendRecord.version;
    workflow.importBusy = true; workflow.status = '保存候选修改中…';
    const controller = trackImportController(new AbortController());
    try {
      const updated = await api(`/api/holding-imports/${encodeURIComponent(sessionId)}/candidates/${id}`, {method:'PATCH', body:JSON.stringify(sendRecord.payload), signal:controller.signal, authGeneration:authRequestGeneration()});
      if (!isImportCurrent(generation, sessionId) || state.importSaveVersions.get(id) !== sendVersion) return false;
      const index = workflow.session.candidates.findIndex(candidate => candidate.id === id); if (index >= 0) workflow.session.candidates[index] = importCandidate(updated);
      workflow.session.status = 'ready'; workflow.status = '已保存'; state.importSaveErrors.delete(id); renderImportReview(); return true;
    } catch (error) {
      if (!isImportCurrent(generation, sessionId) || error?.name === 'AbortError') return false;
      if (state.importSaveVersions.get(id) === sendVersion) { state.importSaveErrors.set(id, formatImportError(error)); workflow.status = '保存失败'; qs('#portfolioImportError').textContent = formatImportError(error); renderImportReview(); }
      return false;
    } finally {
      untrackImportController(controller);
      if (state.sessionQueuedVersions.get(id) === sendVersion) state.sessionQueuedVersions.delete(id);
      if (isImportCurrent(generation, sessionId) && state.pendingSaveTimers.has(id)) {
        const next = state.pendingSaveTimers.get(id); setTimeout(() => enqueueSessionPatch(id, next.generation, next.sessionId, next.version), 0);
      }
      if (isImportCurrent(generation, sessionId) && !state.pendingSaveTimers.has(id)) workflow.importBusy = false;
    }
  };
  const task = state.sessionSaveQueue.then(run, run);
  state.sessionSaveQueue = task.catch(() => false);
  state.sessionQueuedVersions.set(id, version);
  state.inflightSavePromises.set(id, task);
  task.finally(() => { if (state.inflightSavePromises.get(id) === task) state.inflightSavePromises.delete(id); });
  return task;
}
function queueImportCandidateSave(card, id, explicitPayload = null) {
  if (state.demoMode) return Promise.resolve(false);
  const workflow = state.holdingImport; if (!workflow?.sessionId || workflow.canceling) return Promise.resolve(false);
  const version = (state.importSaveVersions.get(id) || 0) + 1, generation = state.importGeneration, sessionId = workflow.sessionId;
  state.importSaveVersions.set(id, version); state.importSaveErrors.delete(id); clearTimeout(state.pendingSaveTimers.get(id)?.timer);
  state.pendingSaveTimers.set(id, {timer:setTimeout(() => flushCandidateSave(id, generation, sessionId, version), explicitPayload ? 0 : 280), payload:explicitPayload || importPatchPayload(card), version, generation, sessionId, card});
  return explicitPayload ? flushCandidateSave(id, generation, sessionId, version) : Promise.resolve(true);
}
async function saveImportCandidate(card, id, explicitPayload = null) { return queueImportCandidateSave(card, id, explicitPayload); }
async function rejectImportCandidate(card) { await queueImportCandidateSave(card, Number(card.dataset.candidateId), {action:'reject'}); }
async function flushImportSaves(generation, sessionId) {
  if (!isImportCurrent(generation, sessionId)) return false;
  while (isImportCurrent(generation, sessionId) && (state.pendingSaveTimers.size || state.inflightSavePromises.size)) {
    const pending = [...state.pendingSaveTimers.entries()].sort(([, left], [, right]) => {
      const leftRow = state.holdingImport?.session?.candidates.find(candidate => candidate.id === Number(left.card?.dataset.candidateId))?.row_index ?? Number.MAX_SAFE_INTEGER;
      const rightRow = state.holdingImport?.session?.candidates.find(candidate => candidate.id === Number(right.card?.dataset.candidateId))?.row_index ?? Number.MAX_SAFE_INTEGER;
      return leftRow - rightRow || left.version - right.version;
    });
    const queued = pending.map(([id, record]) => { clearTimeout(record.timer); return enqueueSessionPatch(id, record.generation, record.sessionId, record.version); });
    await Promise.all(queued);
    await Promise.all([...state.inflightSavePromises.values()]);
  }
  return isImportCurrent(generation, sessionId) && state.importSaveErrors.size === 0 && !importWorkflowHasPendingSaves();
}
async function requestPortfolioConfirm() {
  if (blockFormalMutation('持仓导入确认')) return;
  if (!importConfirmState().ready) { renderImportReview(); return; }
  const workflow = state.holdingImport, generation = state.importGeneration, sessionId = workflow.sessionId;
  workflow.busy = true; workflow.importBusy = true; workflow.status = '正在等待候选保存…'; renderImportReview();
  const flushed = await flushImportSaves(generation, sessionId);
  if (!isImportCurrent(generation, sessionId)) return;
  workflow.busy = false; workflow.importBusy = false; workflow.status = '已保存';
  if (!flushed) { workflow.status = '保存失败'; renderImportReview(); return; }
  if (!importConfirmState().ready) { renderImportReview(); return; }
  qs('#portfolioConfirmError').textContent = ''; openModal('portfolioConfirmOverlay', '#portfolioConfirmYes');
}
async function confirmPortfolioImport() {
  if (blockFormalMutation('持仓写入')) return;
  const workflow = state.holdingImport; if (!workflow?.sessionId || !importConfirmState().ready) return;
  const generation = state.importGeneration, sessionId = workflow.sessionId, controller = trackImportController(new AbortController());
  workflow.busy = true; workflow.importBusy = true; qs('#portfolioConfirmYes').disabled = true; qs('#portfolioConfirmError').textContent = '';
  try {
    await api(`/api/holding-imports/${encodeURIComponent(sessionId)}/confirm`, {method:'POST', signal:controller.signal, authGeneration:authRequestGeneration()});
    if (!isImportCurrent(generation, sessionId) || controller.signal.aborted) return;
    untrackImportController(controller); closeModal('portfolioConfirmOverlay'); closeModal('portfolioImportOverlay'); resetImportWorkflow(); toast('持仓导入已确认'); await loadBootstrap(true);
  } catch (error) {
    if (!isImportCurrent(generation, sessionId) || error?.name === 'AbortError') return;
    workflow.busy = false; workflow.importBusy = false; workflow.importError = formatImportError(error); qs('#portfolioConfirmYes').disabled = false; qs('#portfolioConfirmError').textContent = workflow.importError; renderImportReview();
  } finally { untrackImportController(controller); }
}
async function cancelPortfolioImport() {
  if (blockFormalMutation('持仓截图导入取消')) return;
  if (state.cancelPromise) return state.cancelPromise;
  const workflow = state.holdingImport, sessionId = workflow?.sessionId || '';
  if (!sessionId) { newImportGeneration(); resetImportWorkflow({advance:false}); closeModal('portfolioConfirmOverlay'); closeModal('portfolioImportOverlay'); return; }
  const generation = newImportGeneration(), authGenerationAtCancel = authRequestGeneration();
  workflow.generation = generation; workflow.canceling = true; workflow.cancelError = false; workflow.busy = true; workflow.status = '正在取消导入…'; setImportInteractionDisabled(true); renderImportReview();
  const controller = new AbortController(); state.cancelController = controller;
  const cancelPromise = (async () => {
    try {
      await api(`/api/holding-imports/${encodeURIComponent(sessionId)}/cancel`, {method:'POST', signal:controller.signal, authGeneration:authGenerationAtCancel});
      if (isImportCurrent(generation, sessionId)) { state.cancelPromise = null; state.cancelController = null; closeModal('portfolioConfirmOverlay'); closeModal('portfolioImportOverlay'); resetImportWorkflow(); toast('已取消截图导入'); }
    } catch (error) {
      if (isImportCurrent(generation, sessionId)) { workflow.canceling = false; workflow.busy = false; workflow.cancelError = true; workflow.status = '取消失败，请重试'; qs('#portfolioImportError').textContent = `取消失败，请重试：${formatImportError(error)}`; setImportInteractionDisabled(false); renderImportReview(); }
    } finally {
      if (state.cancelPromise === cancelPromise) state.cancelPromise = null;
      if (state.cancelController === controller) state.cancelController = null;
    }
  })();
  state.cancelPromise = cancelPromise;
  return cancelPromise;
}

function renderNews() {
  const rows = state.data.news || [];
  qs('#newsList').innerHTML = rows.length ? rows.map(item => {
    const href = safeHttpUrl(item.url);
    const title = href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a>` : escapeHtml(item.title);
    const impact = numericValue(item.impact_score) ? `${Number(item.impact_score) >= 0 ? '+' : ''}${escapeHtml(fmt(item.impact_score,2))}` : '—';
    // 解析来源分层（PR-I）：规则启发式 vs 模型分析，必须可分辨；provenance 异常显式告警。
    const analysis = item.analysis || {};
    const modelText = typeof analysis.model_analysis === 'string' ? analysis.model_analysis.trim() : '';
    let sourceBadge;
    if (analysis.analysis_coherent === false) sourceBadge = '<span class="news-facts amber">解析来源校验异常</span>';
    else if (modelText) sourceBadge = `<span class="news-facts">模型分析 · ${escapeHtml(analysis.model || analysis.provider || '已配置模型')}</span>`;
    else if (analysis.source === 'heuristic') sourceBadge = '<span class="news-facts muted">词典启发式解析（未启用 AI 深度分析）</span>';
    else sourceBadge = '';
    const modelBlock = modelText ? `<p><strong>AI 深度解读：</strong>${escapeHtml(modelText)}</p>` : '';
    return `<article class="news-card"><div><h3>${title}</h3><div class="news-meta">${escapeHtml(item.source)} · ${escapeHtml(timeText(item.published_at))} · ${escapeHtml((item.affected_themes || []).join(' / '))}</div>${sourceBadge}${item.facts?.length ? `<p><strong>事实：</strong>${escapeHtml(item.facts.join('；'))}</p>` : ''}${modelBlock}${item.inferences?.length ? `<div class="news-facts">推断（启发式）：${escapeHtml(item.inferences.join('；'))}</div>` : ''}${item.risk_flags?.length ? `<div class="news-facts amber">风险：${escapeHtml(item.risk_flags.join('；'))}</div>` : ''}</div><div><div class="news-score ${escapeHtml(colorClass(item.impact_score))}">${impact}</div><div class="news-meta">${escapeHtml(item.impact_direction || '中性')} · ${escapeHtml(item.impact_horizon || '-')}</div></div></article>`;
  }).join('') : '<div class="loading-row">暂无新闻；可在“系统”中运行 refresh_news。</div>';
}

async function downloadReport(filename) {
  if (blockFormalMutation('正式报告下载')) return;
  const requestGeneration = authRequestGeneration(), sessionActive = state.sessionActive;
  try {
    const response = await fetch(`/api/reports/${encodeURIComponent(filename)}`, {credentials:'same-origin'});
    if (response.status === 401) { if (requestGeneration === authRequestGeneration() && sessionActive === state.sessionActive) { state.sessionActive=false; showAuth('会话已失效，请重新登录'); } return; }
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  } catch (error) { toast(`报告下载失败：${error.message}`, 5000); }
}

async function loadSettings() {
  if (state.demoMode || (state.modeTransition && state.modeTransition.target !== 'formal')) return;
  const requestGeneration = authRequestGeneration(), sessionActive = state.sessionActive, controller = new AbortController();
  const modeGeneration = state.modeGeneration;
  state.settingsController?.abort(); state.settingsController = controller;
  try {
    const settings = await api('/api/settings', {signal:controller.signal, authGeneration:requestGeneration});
    if (requestGeneration !== authRequestGeneration() || sessionActive !== state.sessionActive || controller.signal.aborted || !modeRequestCurrent(modeGeneration, false)) return;
    state.settings = settings;
    const frequencyKeys = new Set(['quote_refresh_minutes','signal_refresh_minutes','news_refresh_minutes','lunch_news_refresh_minutes']);
    for (const [key,value] of Object.entries(state.settings)) {
      if (!frequencyKeys.has(key)) continue;
      const input = qs(`[name="${key}"]`, qs('#settingsForm'));
      if (input) input.value = value;
    }
    applyMarketSettings(state.settings);
    scheduleBrowserRefresh();
  } catch (error) { if (error.name !== 'AbortError' && requestGeneration === authRequestGeneration() && sessionActive === state.sessionActive && modeRequestCurrent(modeGeneration, false)) toast(`读取设置失败：${error.message}`); }
  finally { if (state.settingsController === controller) state.settingsController = null; }
}
function applyMarketSettings(settings) {
  if (!settings) return;
  const form = qs('#marketSourceForm');
  if (!form) return;
  const tier = settings.market_data_tier === 'complete' ? 'complete' : 'usable';
  const radio = qs(`input[name="market_data_tier"][value="${tier}"]`, form);
  if (radio) radio.checked = true;
  const tokenStatus = qs('#tokenStatus');
  if (settings.tushare_token_set) tokenStatus.textContent = '已配置 Token（不会回显）';
  else tokenStatus.textContent = '未配置 Token；免费档不需要';
  const meta = qs('#marketSourceMeta');
  const provider = settings.active_provider || '—';
  if (state.demoMode) {
    meta.textContent = '当前实际数据源：DEMO · 隔离 Mock（不访问外网、不写生产数据库）';
  }
  let extra = '';
  if (tier === 'complete' && !settings.complete_ready) extra = '；已选完整档但还没有 Token，拉数仍走免费源';
  if (settings.ftshare_enabled) extra += `；FTShare ${settings.ftshare_ready ? '资格已通过' : '未资格验证，已跳过'}`;
  if (provider === 'mock' && !state.demoMode) extra += '；正式看板当前为 Mock 配置，请使用隔离演示按钮';
  if (!state.demoMode) meta.textContent = `当前实际数据源：${provider}${extra}`;
  const ftshareStatus = qs('#ftshareStatus');
  if (ftshareStatus) {
    const enabled = settings.ftshare_enabled ? '已启用' : '未启用';
    const qualification = settings.ftshare_qualification === 'qualified' ? '资格已通过' : '未资格验证';
    const latest = settings.ftshare_last_probe?.providers?.find(item => item.provider === 'ftshare');
    ftshareStatus.textContent = `FTShare：${enabled} · ${qualification}${latest ? ` · 最近探测 ${latest.status}` : ''}`;
  }
}
function selectedMarketTier() {
  return qs('input[name="market_data_tier"]:checked', qs('#marketSourceForm'))?.value || 'usable';
}
function typedTushareToken() {
  return String(qs('#tushareTokenInput')?.value || '').trim();
}
async function saveMarketSource(event) {
  event.preventDefault();
  if (selectedMarketTier() === 'demo') { await enterDemoMode(); return; }
  if (blockFormalMutation('正式数据源设置保存')) return;
  const payload = {market_data_tier: selectedMarketTier()};
  const token = typedTushareToken();
  if (token) payload.tushare_token = token;
  try {
    state.settings = await api('/api/settings', {method:'PUT', body:JSON.stringify(payload)});
    qs('#tushareTokenInput').value = '';
    applyMarketSettings(state.settings);
    toast(token ? '数据源与 Token 已保存' : '数据源档位已保存');
  } catch (error) {
    toast(`保存失败：${error.message}`);
  }
}
function setProbeResult(kind, text) {
  const node = qs('#marketProbeResult');
  node.className = `probe-result ${kind}`;
  node.textContent = text;
}
function renderProbeMatrix(rows) {
  const node = qs('#marketProbeMatrix');
  if (!node) return;
  if (!Array.isArray(rows) || !rows.length) { node.textContent = ''; return; }
  node.innerHTML = `<div class="probe-matrix-title">逐 Provider 结果</div><div class="table-wrap"><table><thead><tr><th>数据源</th><th>操作</th><th>状态</th><th>记录</th><th>耗时</th><th>资格</th><th>原因</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHtml(row.provider)}</td><td>${escapeHtml(row.operation)}</td><td><span class="badge ${row.ok ? 'entry' : row.status === 'skipped' ? 'probe' : 'reduce'}">${escapeHtml(row.status)}</span></td><td>${escapeHtml(fmt(row.records,0))}</td><td>${escapeHtml(fmt(row.latency,1))} ms</td><td>${escapeHtml(row.qualification || '—')}</td><td>${escapeHtml(row.failure_class || '')}</td></tr>`).join('')}</tbody></table></div>`;
}
async function probeMarketSource() {
  if (state.demoMode || selectedMarketTier() === 'demo') {
    setProbeResult('skip', '演示模式不会访问外网');
    toast('演示模式未出网');
    return;
  }
  const payload = {market_data_tier: selectedMarketTier()};
  const token = typedTushareToken();
  if (token) payload.tushare_token = token;
  setProbeResult('muted', '正在测试连通…');
  try {
    const result = await api('/api/settings/market-probe', {method:'POST', body:JSON.stringify(payload)});
    const bits = [result.message || '探测结束'];
    if (result.provider) bits.push(`数据源 ${result.provider}`);
    if (Number.isFinite(Number(result.bars))) bits.push(`日线 ${result.bars} 条`);
    if (result.failure_class) bits.push(result.failure_class);
    if (Array.isArray(result.providers)) bits.push(`已检查 ${result.providers.length} 个数据源`);
    renderProbeMatrix(result.providers);
    const kind = result.ok ? 'ok' : result.skipped ? 'skip' : 'fail';
    setProbeResult(kind, bits.join(' · '));
    toast(result.ok ? '探测成功' : result.skipped ? '演示数据源未出网' : '探测未通过');
  } catch (error) {
    setProbeResult('fail', `测试失败：${error.message}`);
    toast(`测试失败：${error.message}`);
  }
}
async function clearStoredTushareToken() {
  if (blockFormalMutation('Token 清除')) return;
  try {
    state.settings = await api('/api/settings', {method:'PUT', body:JSON.stringify({clear_tushare_token:true})});
    qs('#tushareTokenInput').value = '';
    applyMarketSettings(state.settings);
    toast('已清除保存的 Token');
  } catch (error) {
    toast(`清除失败：${error.message}`);
  }
}
function renderSystem() {
  const providers = state.data.provider_health || [];
  qs('#providerTable tbody').innerHTML = providers.length ? providers.map(r => `<tr><td>${escapeHtml(timeText(r.created_at))}</td><td>${escapeHtml(r.operation)}</td><td>${escapeHtml(r.provider)}</td><td><span class="badge ${r.status==='ok'||r.status==='fallback_used'?'entry':'reduce'}">${escapeHtml(r.status)}</span></td><td>${escapeHtml(fmt(r.latency_ms,1))} ms</td><td>${escapeHtml(fmt(r.record_count,0))}</td><td class="muted">${escapeHtml(r.reason || '')}</td></tr>`).join('') : '<tr><td colspan="7">暂无审计记录</td></tr>';
  const tasks = state.data.tasks || [];
  qs('#taskTable tbody').innerHTML = tasks.length ? tasks.map(r => `<tr><td>${escapeHtml(timeText(r.started_at))}</td><td>${escapeHtml(r.task_name)}</td><td><span class="badge ${r.status==='succeeded'?'entry':r.status==='failed'?'reduce':'probe'}">${escapeHtml(r.status)}</span></td><td class="muted">${escapeHtml(r.run_id)}</td><td class="down">${escapeHtml(r.error || '')}</td></tr>`).join('') : '<tr><td colspan="5">暂无任务记录</td></tr>';
  const reports = state.reports || [];
  qs('#reportTable tbody').innerHTML = reports.length ? reports.map(r => `<tr><td>${escapeHtml(timeText(r.as_of_time))}</td><td>${escapeHtml(r.type)}</td><td>${escapeHtml(r.filename)}</td><td class="muted">${escapeHtml(String(r.content_hash || '').slice(0,16))}…</td><td><button class="small-button download-report" data-file="${escapeHtml(r.filename)}">下载</button></td></tr>`).join('') : '<tr><td colspan="5">暂无报告</td></tr>';
  qsa('.download-report').forEach(button => button.addEventListener('click', () => downloadReport(button.dataset.file)));
  renderSourceBadge(state.data);
}
function renderTaskButtons() {
  const tasks = [
    ['refresh_quotes','刷新行情'],['refresh_news','更新新闻'],['refresh_signals','重算信号'],['refresh_bars','更新日线'],['refresh_indicators','重算指标'],['refresh_forecasts','更新预测'],['generate_report','生成报告'],['validate_forecasts','验证预测'],['backtest_rotation','轮动回测'],['full_pipeline','完整流水线']
  ];
  qs('#taskButtons').innerHTML = tasks.map(([name,label]) => `<button class="ghost task-run" data-task="${name}"${state.demoMode ? ' disabled title="演示模式已禁用正式任务"' : ''}>${label}</button>`).join('');
  qsa('.task-run').forEach(b => b.addEventListener('click', () => runTask(b.dataset.task, b)));
}

function gradePct(value) {
  if (!numericValue(value)) return '—';
  return Math.abs(Number(value)) <= 1 ? pct(value, 2, true) : pct(value, 2, false);
}

async function loadSignalGrade(silent = false) {
  if (state.demoMode || state.modeTransition) return;
  const modeGeneration = state.modeGeneration;
  try {
    const result = await api('/api/signals/grade');
    if (!modeRequestCurrent(modeGeneration, false)) return;
    state.signalGrade = result;
    renderSignalGrade();
  } catch (error) {
    if (!silent && error.message !== 'unauthorized' && modeRequestCurrent(modeGeneration, false)) toast(`信号分级加载失败：${error.message}`, 5000);
  }
}

function macdPillClass(kind) {
  if (kind === 'death') return 'pill-macd-death';
  if (kind === 'gold' || kind === 'bull_cont') return 'pill-macd-bull';
  return 'pill-macd-approach';
}

function kdjPillClass(kind) {
  if (kind === 'death') return 'pill-kdj-death';
  if (kind === 'overbought') return 'pill-kdj-overbought';
  if (kind === 'high') return 'pill-kdj-high';
  return 'pill-kdj-healthy';
}

function gradeRowHtml(row) {
  const vol = row.volume || {};
  const ma = row.ma || {};
  const macd = row.macd || {};
  const kdj = row.kdj || {};
  const rsi = row.rsi || {};
  const td = row.td || {};
  const sector = row.sector || {};
  const forecast = row.forecast || {};
  const volClass = vol.kind === 'expand' ? 'pill-expand' : vol.kind === 'contract' ? 'pill-contract' : 'pill-flat';
  const arrows = (ma.arrows || []).map(item => `<span class="${item.dir === 'up' ? 'arrow-up' : 'arrow-down'}">${escapeHtml(item.window)}${item.dir === 'up' ? '↑' : '↓'}</span>`).join(' ');
  const vs = row.vs_yesterday === 'up' ? '<span class="arrow-up">↑</span>' : row.vs_yesterday === 'down' ? '<span class="arrow-down">↓</span>' : '—';
  return `<tr data-code="${escapeHtml(row.ts_code || '')}">
    <td><div class="instrument-name">${escapeHtml(row.name || row.ts_code)}</div><div class="instrument-meta">${escapeHtml(row.ts_code || '')} · ${escapeHtml(row.theme_l1 || '')}/${escapeHtml(row.theme_l2 || '')}</div></td>
    <td class="${escapeHtml(colorClass(row.pct_change))}">${escapeHtml(gradePct(row.pct_change))}</td>
    <td>${vs}</td>
    <td><span class="pill ${volClass}">${escapeHtml(vol.label || '—')} ${escapeHtml(vol.ratio == null ? '' : String(vol.ratio))}</span></td>
    <td><div class="ma-${escapeHtml(ma.kind || 'mixed')}">${escapeHtml(ma.label || '—')}</div><div class="metric-sub">${arrows}</div><div class="metric-sub">${escapeHtml(ma.values_text || '')}</div></td>
    <td><span class="pill ${macdPillClass(macd.kind)}">${escapeHtml(macd.label || '—')}</span><div class="metric-sub">DIF ${escapeHtml(fmt(macd.dif, 4))} DEA ${escapeHtml(fmt(macd.dea, 4))}</div></td>
    <td><span class="pill ${kdjPillClass(kdj.kind)}">J=${escapeHtml(fmt(kdj.j, 1))} ${escapeHtml(kdj.label || '')}</span><div class="metric-sub">${escapeHtml(kdj.note || '')}</div><div class="metric-sub">K=${escapeHtml(fmt(kdj.k, 1))} D=${escapeHtml(fmt(kdj.d, 1))}</div></td>
    <td><span class="td-pill">${escapeHtml(td.label || '—')}</span></td>
    <td><div class="metric-main">${escapeHtml(fmt(rsi.value, 1))}</div><div class="metric-sub">${escapeHtml(rsi.label || '')}</div></td>
    <td><div class="metric-main">${escapeHtml(sector.label || '未验证 / 不可用')}</div><div class="metric-sub">${escapeHtml(sector.note || '')}</div></td>
    <td class="${escapeHtml(colorClass(row.return_5d))}">${escapeHtml(gradePct(row.return_5d))}</td>
    <td><div class="${escapeHtml(colorClass(forecast.expected_return))}">${escapeHtml(gradePct(forecast.expected_return))}</div><div class="forecast-flag">FORECAST · 非实际结果</div><div class="metric-sub">conf ${escapeHtml(fmt(forecast.confidence, 0))} · ${escapeHtml(forecast.calibration_status || 'not_calibrated')}</div></td>
    <td><span class="badge ${escapeHtml(stateClass(row.grade))}">${escapeHtml(row.grade || '—')}</span><div class="metric-sub">研究提示，非操作指令</div></td>
  </tr>`;
}

function renderSignalGrade() {
  const payload = state.signalGrade;
  const cardsEl = qs('#gradeSummaryCards');
  const groupsEl = qs('#gradeGroups');
  if (!payload || !cardsEl || !groupsEl) return;
  const counts = payload.counts || {};
  const cards = [
    ['可加仓', counts['可加仓'] ?? 0, 'g-add'],
    ['可入场', counts['可入场'] ?? 0, 'g-entry'],
    ['可试探', counts['可试探'] ?? 0, 'g-probe'],
    ['观望', counts['观望'] ?? 0, 'g-watch'],
    ['减仓', counts['减仓'] ?? 0, 'g-cut'],
  ];
  cardsEl.innerHTML = cards.map(([label, value, klass]) => `<div class="summary-card ${klass}"><div class="label">${label}</div><div class="value">${escapeHtml(String(value))}</div><div class="sub">研究计数</div></div>`).join('');
  const narrative = qs('#gradeNarrative');
  if (narrative) narrative.textContent = payload.narrative || '';
  const meta = qs('#gradeMeta');
  if (meta) meta.textContent = `${payload.version || ''} · ${payload.disclaimer || ''}`;
  const groups = payload.groups || {};
  const reasons = {
    '可加仓': 'J < 90 · 上涨放量 · MA多头排列',
    '可入场': 'J < 90 · KDJ有余量 · 结构向好',
    '可试探': 'J < 90 · 信号偏弱 · 结构尚可',
    '观望': '超买/偏高 · 放量滞涨 · 回调风险',
    '减仓': 'KDJ死叉 · MACD将死叉 · 多重看空共振',
  };
  const headers = '<thead><tr><th>标的</th><th>今日涨幅</th><th>较昨日</th><th>量能</th><th>均线多空</th><th>MACD</th><th>KDJ</th><th>九转</th><th>RSI</th><th>板块涨跌</th><th>近1周</th><th>明日预测</th><th>操作建议</th></tr></thead>';
  groupsEl.innerHTML = ['可加仓', '可入场', '可试探', '观望', '减仓'].map(name => {
    const rows = groups[name] || [];
    const body = rows.length
      ? `<div class="table-wrap"><table class="signal-table grade-table">${headers}<tbody>${rows.map(gradeRowHtml).join('')}</tbody></table></div>`
      : `<div class="grade-empty">今日无「${name}」标的</div>`;
    return `<section class="grade-group"><div class="grade-group-head"><span class="badge ${escapeHtml(stateClass(name))}">${escapeHtml(name)}</span><span>${escapeHtml(reasons[name] || '')}</span><span class="count">${rows.length}个标的</span></div>${body}</section>`;
  }).join('');
  qsa('#gradeGroups tr[data-code]').forEach(row => {
    row.addEventListener('click', () => openDetail(row.dataset.code));
    row.style.cursor = 'pointer';
  });
}

async function loadSignalBoards(silent = false) {
  if (state.demoMode || state.modeTransition) return;
  const modeGeneration = state.modeGeneration;
  try {
    const result = await api('/api/signals/boards');
    if (!modeRequestCurrent(modeGeneration, false)) return;
    state.boards = result;
    renderBoards();
  } catch (error) {
    if (!silent && error.message !== 'unauthorized' && modeRequestCurrent(modeGeneration, false)) toast(`板块加载失败：${error.message}`, 5000);
  }
}

function boardCardHtml(board) {
  const score = board.score == null ? '—' : String(board.score);
  const pctText = board.pct_change == null ? '无K线' : gradePct(board.pct_change);
  const primary = board.primary_ts_code || '';
  const parts = board.components || {};
  const partLine = ['volume', 'ma', 'macd', 'kdj', 'rsi', 'td', 'momentum'].map(key => {
    const labels = {volume: '量能', ma: '均线', macd: 'MACD', kdj: 'KDJ', rsi: 'RSI', td: '九转', momentum: '近周'};
    return `${labels[key]} ${parts[key] == null ? '—' : Math.round(parts[key])}`;
  }).join(' · ');
  const funds = (board.members || []).map(item => item.name || item.ts_code).slice(0, 3).join(' / ') || '未挂ETF';
  return `<article class="board-card ${board.has_proxy ? '' : 'is-empty'}" data-code="${escapeHtml(primary)}" data-board="${escapeHtml(board.id)}" tabindex="0">
    <div class="board-card-top"><strong>${escapeHtml(board.name)}</strong><span class="badge ${escapeHtml(stateClass(board.grade))}">${escapeHtml(board.grade || '—')}</span></div>
    <div class="board-score">${escapeHtml(score)}<span>综合分</span></div>
    <div class="${escapeHtml(colorClass(board.pct_change))} board-chg">${escapeHtml(pctText)}</div>
    <div class="metric-sub">${escapeHtml(funds)}</div>
    <div class="metric-sub">${escapeHtml(partLine)}</div>
    <div class="metric-sub">${escapeHtml(board.note || '')}</div>
  </article>`;
}

function fillBoardSelect() {
  const select = qs('#boardAddSelect');
  if (!select || !state.boards) return;
  const kind = state.boardKind || 'industry';
  const boards = state.boards[kind] || [];
  select.innerHTML = boards.map(board => `<option value="${escapeHtml(board.id)}">${escapeHtml(board.name)}</option>`).join('');
}

function renderBoards() {
  const grid = qs('#boardGrid');
  if (!grid) return;
  const payload = state.boards;
  if (!payload) {
    grid.innerHTML = '<div class="empty-state">等待板块数据…</div>';
    return;
  }
  const meta = qs('#boardMeta');
  if (meta) meta.textContent = `${payload.version || ''} · 行业 ${payload.counts?.industry ?? 0} · 概念 ${payload.counts?.concept ?? 0} · 有ETF代理 行业${payload.counts?.industry_with_etf ?? 0}/概念${payload.counts?.concept_with_etf ?? 0}`;
  const kind = state.boardKind || 'industry';
  const boards = [...(payload[kind] || [])].sort((a, b) => Number(b.score ?? -1) - Number(a.score ?? -1));
  grid.innerHTML = boards.length ? boards.map(boardCardHtml).join('') : '<div class="empty-state">无板块目录</div>';
  fillBoardSelect();
  qsa('#boardGrid .board-card[data-code]').forEach(card => {
    const open = () => { if (card.dataset.code) openDetail(card.dataset.code); };
    card.addEventListener('click', open);
    card.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
    });
  });
}

async function submitBoardFund(event) {
  event.preventDefault();
  if (blockFormalMutation('板块标的修改')) return;
  const boardId = qs('#boardAddSelect')?.value;
  const tsCode = qs('#boardAddCode')?.value.trim();
  const name = qs('#boardAddName')?.value.trim();
  if (!boardId || !tsCode) return;
  try {
    const result = await api(`/api/signals/boards/${encodeURIComponent(boardId)}/funds`, {method: 'POST', body: JSON.stringify({ts_code: tsCode, name: name || null})});
    toast(`已加入板块：${result.ts_code}。正在拉日线（无 Token 时为 Mock）`);
    await api('/api/tasks/refresh_bars', {method: 'POST', body: JSON.stringify({lookback_days: 420, codes: [result.ts_code]})});
    await api('/api/tasks/refresh_indicators', {method: 'POST', body: JSON.stringify({codes: [result.ts_code]})});
    await loadBootstrap(true);
    await loadSignalBoards();
  } catch (error) {
    toast(`添加失败：${error.message}`, 5000);
  }
}

async function loadSignalCenter(silent = false, coefficientOverride = null) {
  if (state.demoMode || state.modeTransition || state.signalCenterLoading) return;
  const modeGeneration = state.modeGeneration;
  state.signalCenterLoading = true;
  if (!silent) qs('#signalCurveMeta').textContent = '加载中...';
  try {
    const query = coefficientOverride == null ? '' : `?coefficient=${encodeURIComponent(coefficientOverride)}`;
    const result = await api(`/api/signals/center${query}`);
    if (!modeRequestCurrent(modeGeneration, false)) return;
    state.signalCenter = result;
    renderSignalCenter();
  } catch (error) {
    if (error.message !== 'unauthorized' && modeRequestCurrent(modeGeneration, false)) toast(`信号中心加载失败：${error.message}`, 5000);
  } finally { state.signalCenterLoading = false; }
}

const SIGNAL_CATEGORIES = {
  opportunity: {label: '机会', color: 'var(--up)'},
  risk: {label: '风险', color: 'var(--blue)'},
  take_profit: {label: '止盈', color: 'var(--down)'},
};

function renderSignalCenter() {
  const payload = state.signalCenter;
  if (!payload) return;
  const warning = qs('#signalWarning');
  if (payload.research_only) {
    warning.textContent = '信号中心为研究视图：当前数据源为 Mock 演示数据，所有前排与板块强度仅用于功能验证，不可用于真实投资判断。';
    warning.classList.remove('hidden');
  } else warning.classList.add('hidden');
  const s = payload.summary || {};
  const cards = [
    ['总信号', s.total ?? 0, `信号系数 × ${fmt(payload.coefficient,2)}`, ''],
    ['机会', s.opportunity ?? 0, '可入场 / 试探 / 加仓', SIGNAL_CATEGORIES.opportunity.color],
    ['风险', s.risk ?? 0, '减仓 / 风险观察 / 低位', SIGNAL_CATEGORIES.risk.color],
    ['止盈', s.take_profit ?? 0, '过热研究提示', SIGNAL_CATEGORIES.take_profit.color],
  ];
  qs('#signalSummaryCards').innerHTML = cards.map(([label, value, sub, color]) => `<div class="summary-card"><div class="label">${escapeHtml(label)}</div><div class="value"${color?` style="color:${color}"`:''}>${escapeHtml(value)}</div><div class="sub">${escapeHtml(sub)}</div></div>`).join('');
  qs('#signalCurveMeta').textContent = `口径 ${payload.version} · 生成 ${timeText(payload.generated_at)}`;
  const sectors = payload.sectors || [];
  qs('#sectorList').innerHTML = sectors.length ? sectors.map(sectorRow).join('') : '<div class="loading-row">暂无板块数据；需要先完成指标重算（refresh_indicators）。</div>';
  renderFrontList();
  const slider = qs('#coefficientSlider');
  if (document.activeElement !== slider) slider.value = payload.coefficient;
  qs('#coefficientValue').textContent = `× ${fmt(payload.coefficient,2)}`;
  drawSignalCurve();
}

function sectorRow(sector) {
  const chips = (sector.members || []).slice(0, 4)
    .map(m => `<span class="chip">${escapeHtml(m.ts_code)} ${escapeHtml(m.name)}</span>`).join('');
  const meta = [
    `动量 ${fmt(sector.momentum_score, 0)}`,
    sector.technical_score == null ? null : `技术 ${fmt(sector.technical_score, 0)}`,
    sector.breadth == null ? null : `宽度 ${fmt(sector.breadth * 100, 0)}%`,
    sector.news_score == null ? null : `新闻 ${fmt(sector.news_score, 0)}`,
    sector.risk_score == null ? null : `风险 ${fmt(sector.risk_score, 0)}`,
    `${escapeHtml(sector.member_count)} 只`,
  ].filter(Boolean).join(' · ');
  return `<div class="sector-row">
    <div class="sector-rank">${escapeHtml(sector.rank)}</div>
    <div class="sector-main">
      <div class="sector-head"><span class="sector-name">${escapeHtml(sector.theme_l1)}</span><span class="sector-score ${sector.rank <= 3 ? 'up' : ''}">${fmt(sector.strength, 1)}</span></div>
      <div class="sector-bar"><i style="width:${Math.max(2, Math.min(100, Number(sector.strength) || 0))}%"></i></div>
      <div class="sector-meta">${escapeHtml(meta)}</div>
      <div class="sector-members">${chips}</div>
    </div>
  </div>`;
}

function frontItem(item, index) {
  let metricMain, metricSub;
  if (item.category === 'opportunity') {
    metricMain = fmt(item.effective_score, 1);
    metricSub = `有效分 · 原始 ${fmt(item.score, 1)} × 系数`;
  } else if (item.category === 'risk') {
    metricMain = fmt(item.risk_score, 1);
    metricSub = `风险分 · 有效分 ${fmt(item.effective_score, 1)}`;
  } else {
    metricMain = item.heat == null ? '—' : fmt(item.heat * 100, 0);
    metricSub = `过热度 · 20日 ${pct(item.return_20d, 1, true)}`;
  }
  const held = item.in_account;
  const holdingPart = held && item.holding
    ? `权重 ${fmt((item.holding.current_weight || 0) * 100, 1)}% · 浮动 ${item.holding.pnl_pct == null ? '—' : pct(item.holding.pnl_pct)}`
    : '';
  return `<div class="front-item ${held ? 'in-account' : ''}" data-code="${escapeHtml(item.ts_code)}">
    <div class="front-rank">${index + 1}</div>
    <div class="front-main">
      <div class="front-name">${escapeHtml(item.name)} <span class="muted">${escapeHtml(item.ts_code)}</span></div>
      <div class="front-meta">${escapeHtml(item.theme_l1 || '未分类')} · 技术 ${fmt(item.technical_score, 1)} · 风险 ${fmt(item.risk_score, 1)} · RSI ${fmt(item.rsi14, 1)} · 20日 ${pct(item.return_20d, 1, true)} · 信号 ${timeText(item.signal_time)}</div>
      ${held ? `<div class="account-warning">⚠ 该标的在你当前持仓中（${holdingPart}）——本页仅为研究提示，不构成账户操作指令，请结合自身成本与风险判断。</div>` : ''}
    </div>
    <div class="front-side">
      <span class="badge ${stateClass(item.state)}">${escapeHtml(item.state || '—')}</span>
      <div class="front-score">${escapeHtml(metricMain)}</div>
      <div class="metric-sub">${escapeHtml(metricSub)}</div>
    </div>
  </div>`;
}

function renderFrontList() {
  const payload = state.signalCenter;
  if (!payload) return;
  const tab = state.signalFrontTab;
  qsa('#frontTabs button').forEach(b => b.classList.toggle('active', b.dataset.front === tab));
  const items = (payload.fronts || {})[tab] || [];
  const labels = {opportunity: '机会前排', risk: '风险前排', take_profit: '止盈前排'};
  qs('#frontCount').textContent = `${labels[tab]} · 共 ${items.length} 只（研究提示，非操作指令）`;
  qs('#frontList').innerHTML = items.length ? items.map(frontItem).join('') : '<div class="loading-row">当前系数下该前排暂无标的。</div>';
  qsa('#frontList .front-item[data-code]').forEach(el => el.addEventListener('click', () => openDetail(el.dataset.code)));
}

const CURVE_SERIES = [
  {key: 'opportunity', color: '#ff605e', label: '机会'},
  {key: 'risk', color: '#4aa3ff', label: '风险'},
  {key: 'take_profit', color: '#24c997', label: '止盈'},
];

function drawSignalCurve(hoverIndex = null) {
  const canvas = qs('#signalCurveCanvas');
  const curve = state.signalCenter?.curve || [];
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(600, rect.width * dpr);
  canvas.height = 260 * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const width = canvas.width / dpr, height = canvas.height / dpr;
  ctx.clearRect(0, 0, width, height);
  canvas._points = null; canvas._curve = null; canvas._layout = null;
  if (!curve.length) {
    ctx.fillStyle = '#71839a'; ctx.font = '12px system-ui';
    ctx.fillText('暂无信号历史：运行 refresh_signals 后按交易日逐日累积。', 20, 30);
    return;
  }
  const left = 46, right = 16, top = 16, bottom = 30;
  const maxV = Math.max(4, ...curve.map(p => Math.max(p.opportunity || 0, p.risk || 0, p.take_profit || 0)));
  const xStep = (width - left - right) / curve.length;
  const y = v => top + (1 - v / maxV) * (height - top - bottom);
  ctx.strokeStyle = '#1d2a3b'; ctx.fillStyle = '#71839a'; ctx.font = '10px system-ui'; ctx.lineWidth = 1;
  for (let n = 0; n <= 4; n++) {
    const yy = top + (height - top - bottom) * n / 4;
    ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(width - right, yy); ctx.stroke();
    ctx.fillText(String(Math.round(maxV * (1 - n / 4))), 10, yy + 3);
  }
  ctx.fillText(curve[0].date, left, height - 8);
  const lastLabel = curve[curve.length - 1].date;
  ctx.fillText(lastLabel, width - right - ctx.measureText(lastLabel).width, height - 8);
  const points = {};
  for (const series of CURVE_SERIES) {
    ctx.strokeStyle = series.color; ctx.lineWidth = 1.6; ctx.beginPath();
    const pts = [];
    curve.forEach((p, i) => {
      const x = left + xStep * (i + .5), yy = y(Number(p[series.key] || 0));
      pts.push([x, yy]);
      i ? ctx.lineTo(x, yy) : ctx.moveTo(x, yy);
    });
    ctx.stroke();
    points[series.key] = pts;
  }
  canvas._points = points; canvas._curve = curve;
  canvas._layout = {left, right, xStep, top, bottom, height, width};
  if (hoverIndex != null) drawSignalCurveHover(hoverIndex);
}

function drawSignalCurveHover(index) {
  drawSignalCurve();
  const canvas = qs('#signalCurveCanvas');
  const points = canvas._points, curve = canvas._curve, layout = canvas._layout;
  if (!points || !curve || !curve[index]) return;
  const ctx = canvas.getContext('2d');
  const x = points.opportunity[index][0];
  ctx.strokeStyle = '#3a4a63'; ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(x, layout.top); ctx.lineTo(x, layout.height - layout.bottom); ctx.stroke();
  ctx.setLineDash([]);
  for (const series of CURVE_SERIES) {
    const [px, py] = points[series.key][index];
    ctx.fillStyle = series.color;
    ctx.beginPath(); ctx.arc(px, py, 3.2, 0, Math.PI * 2); ctx.fill();
  }
  const point = curve[index];
  const lines = [
    point.date,
    `总量 ${point.total}`,
    ...CURVE_SERIES.map(s => `${s.label} ${point[s.key] || 0}`),
  ];
  ctx.font = '11px system-ui';
  const boxWidth = Math.max(...lines.map(t => ctx.measureText(t).width)) + 18;
  const boxHeight = lines.length * 16 + 10;
  let boxX = x + 10;
  if (boxX + boxWidth > layout.width - layout.right) boxX = x - boxWidth - 10;
  const boxY = layout.top + 6;
  ctx.fillStyle = 'rgba(17,24,35,.95)'; ctx.strokeStyle = '#263246';
  ctx.beginPath(); ctx.roundRect(boxX, boxY, boxWidth, boxHeight, 6); ctx.fill(); ctx.stroke();
  lines.forEach((text, i) => {
    ctx.fillStyle = i === 0 ? '#e9eff8' : (i === 2 ? '#ff605e' : i === 3 ? '#4aa3ff' : i === 4 ? '#24c997' : '#aebacb');
    ctx.fillText(text, boxX + 9, boxY + 20 + i * 16);
  });
}

function onCoefficientInput(event) {
  const value = Number(event.currentTarget.value);
  qs('#coefficientValue').textContent = `× ${value.toFixed(2)}`;
  clearTimeout(state.coefficientTimer);
  state.coefficientTimer = setTimeout(() => loadSignalCenter(true, value), 420);
}

async function saveCoefficient() {
  if (blockFormalMutation('信号系数保存')) return;
  const value = Number(qs('#coefficientSlider').value);
  try {
    state.settings = await api('/api/settings', {method: 'PUT', body: JSON.stringify({signal_center_coefficient: value})});
    toast(`信号系数已保存为 ${value.toFixed(2)}`);
    await loadSignalCenter(true);
  } catch (error) { toast(`保存失败：${error.message}`, 5000); }
}

function renderAll() {
  renderDecisionBoard(); renderMarketContext(); renderHoldings(); renderNews(); renderSystem(); renderSignalCenter(); renderTaskButtons();
}

function switchTab(tab) {
  state.activeTab = tab;
  qsa('.view').forEach(v => v.classList.toggle('active', v.id === `view-${tab}`));
  qsa('#tabs button').forEach(b => { const selected = b.dataset.tab === tab; b.classList.toggle('active', selected); b.setAttribute('aria-selected', String(selected)); });
  if (tab === 'system' && !state.settings) loadSettings();
  if (tab === 'signals' && !state.signalCenter) loadSignalCenter();
  if (tab === 'dashboard') loadDecisionBoard(true);
  if (tab === 'holdings') loadWatchlist();
}

function openHolding(code = null) {
  if (blockFormalMutation('持仓编辑')) return;
  const form = qs('#holdingForm'); form.reset(); qs('#holdingError').textContent = '';
  if (code) {
    const h = (state.data.holdings || []).find(x => x.ts_code === code);
    if (h) {
      qs('#holdingCode').value = h.ts_code;
      form.elements.shares.value = h.shares;
      form.elements.cost_price.value = h.cost_price;
      form.elements.target_weight.value = h.target_weight ?? '';
      form.elements.notes.value = h.notes ?? '';
    }
  }
  openModal('holdingOverlay', '#holdingCode');
}
async function saveHolding(event) {
  event.preventDefault();
  if (blockFormalMutation('持仓保存')) return;
  const form = event.currentTarget;
  const payload = {
    ts_code: form.elements.ts_code.value,
    shares: Number(form.elements.shares.value),
    cost_price: Number(form.elements.cost_price.value),
    target_weight: form.elements.target_weight.value === '' ? null : Number(form.elements.target_weight.value),
    notes: form.elements.notes.value || null,
  };
  try {
    await api(`/api/holdings/${encodeURIComponent(payload.ts_code)}`, {method:'PUT', body:JSON.stringify(payload)});
    closeModal('holdingOverlay'); toast('持仓已保存'); await loadBootstrap(true);
  } catch (error) { qs('#holdingError').textContent = error.message; }
}
async function deleteHolding(code) {
  if (blockFormalMutation('持仓删除')) return;
  if (!confirm(`删除 ${code} 的持仓记录？`)) return;
  try { await api(`/api/holdings/${encodeURIComponent(code)}`, {method:'DELETE'}); toast('已删除'); await loadBootstrap(true); }
  catch (error) { toast(`删除失败：${error.message}`); }
}

async function runTask(name, button = null) {
  if (blockFormalMutation('正式任务')) return;
  if (button) button.disabled = true;
  qs('#taskOutput').textContent = `运行 ${name} 中...`;
  try {
    const payload = name === 'refresh_bars' ? {lookback_days: 120} : {};
    const result = await api(`/api/tasks/${encodeURIComponent(name)}`, {method:'POST', body:JSON.stringify(payload)});
    qs('#taskOutput').textContent = JSON.stringify(result, null, 2);
    toast(`${name} 完成`); await loadBootstrap(true);
  } catch (error) { qs('#taskOutput').textContent = `${name} 失败\n${error.message}`; toast(`任务失败：${error.message}`,5000); }
  finally { if (button) button.disabled = false; }
}

async function openDetail(code) {
  if (state.activeTab === 'dashboard' && state.decisionBoard) return openDecisionDetail(code);
  const row = (state.data.instruments || []).find(r => r.ts_code === code) || {ts_code: code, name: code, theme_l1: '', theme_l2: '', indicator: {}, signal: {}, quote: {}, forecasts: {}};
  state.decisionUi.openDetailCode = null; state.decisionUi.openDetailSnapshotId = null;
  qs('#chartCanvas')?.classList.remove('hidden');
  state.detailCode = code;
  const i = row.indicator || {}, v = i.values || {}, s = row.signal || {}, q = row.quote || {};
  const forecastHtml = Object.values(row.forecasts || {}).map(forecastCell).join('');
  qs('#detailContent').innerHTML = `<div class="eyebrow">${escapeHtml(row.theme_l1 || '')} / ${escapeHtml(row.theme_l2 || '')}</div><h2>${displayIdentity(row.ts_code, row.name)}</h2><div class="detail-hero observed-surface"><div class="detail-primary-change ${escapeHtml(colorClass(q.pct_change))}"><span>今日涨跌</span><strong>${escapeHtml(pct(q.pct_change))}</strong></div><div class="detail-secondary-price"><span>最新价格</span><strong>${escapeHtml(fmt(q.price,4))}</strong></div><div class="quote-state-badge ${escapeHtml(q.is_mock ? 'is-mock' : quoteFreshness(q))}">${escapeHtml(quoteStateLabel(q))}</div>${provenanceText(q.source, q.source_timestamp || q.time, q.fetched_at, quoteFreshness(q), q.verification_status || 'unverified', q.degraded_reason)}</div><div class="detail-grid">
    ${[['技术分',fmt(i.technical_score,1)],['风险分',fmt(i.risk_score,1)],['信号',s.state||'—'],['信号分',fmt(s.score,1)],['MACD柱',fmt(v.macd_hist,6)],['KDJ J',fmt(v.kdj_j,1)],['RSI14',fmt(v.rsi14,1)],['量比',fmt(v.volume_ratio,2)],['TD买/卖',`${v.td_buy_setup??'—'}/${v.td_sell_setup??'—'}`],['溢价率',q.premium_rate==null?'—':pct(q.premium_rate)]].map(([label,value])=>`<div class="detail-metric"><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></div>`).join('')}</div><section class="detail-forecast forecast-surface" aria-labelledby="detailForecastHeading"><div class="eyebrow">FORECAST · 非实际结果</div><h3 id="detailForecastHeading">预测摘要</h3><div class="detail-forecast-grid">${forecastHtml || '<span class="muted">预测不可用</span>'}</div></section><div class="reason-box"><strong>理由：</strong>${escapeHtml((s.reasons||[]).join('；')||'暂无')}<br><span class="amber"><strong>风险：</strong>${escapeHtml((s.risks||[]).join('；')||'暂无')}</span></div>`;
  openModal('detailOverlay');
  scheduleDetailBars(code);
}

function ema(values, period) {
  const out=[], alpha=2/(period+1); let previous=values[0] || 0;
  values.forEach((v,idx)=>{ previous = idx===0?v:alpha*v+(1-alpha)*previous; out.push(previous); }); return out;
}
function sma(values, period) {
  return values.map((_,idx)=> idx+1<period ? null : values.slice(idx-period+1,idx+1).reduce((a,b)=>a+b,0)/period);
}
function drawChart(bars) {
  const canvas = qs('#chartCanvas');
  const rect = canvas.getBoundingClientRect(); const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(600, rect.width*dpr); canvas.height = 520*dpr;
  const ctx = canvas.getContext('2d'); ctx.scale(dpr,dpr);
  const width=canvas.width/dpr, height=canvas.height/dpr; ctx.clearRect(0,0,width,height);
  const data=bars.slice(-140); if (!data.length) return;
  const left=55,right=18,top=24,priceBottom=365,macdTop=400,bottom=500;
  const highs=data.map(x=>Number(x.high)), lows=data.map(x=>Number(x.low)), closes=data.map(x=>Number(x.close));
  const max=Math.max(...highs), min=Math.min(...lows), range=max-min||1;
  const xStep=(width-left-right)/data.length, candle=Math.max(2,Math.min(8,xStep*.62));
  const y=p=>top+(max-p)/range*(priceBottom-top);
  ctx.strokeStyle='#1d2a3b'; ctx.lineWidth=1; ctx.fillStyle='#71839a'; ctx.font='10px system-ui';
  for(let n=0;n<=5;n++){const yy=top+(priceBottom-top)*n/5;ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(width-right,yy);ctx.stroke();const price=max-range*n/5;ctx.fillText(price.toFixed(3),5,yy+3);}
  data.forEach((b,idx)=>{const x=left+xStep*(idx+.5), open=Number(b.open), close=Number(b.close), high=Number(b.high), low=Number(b.low), up=close>=open;ctx.strokeStyle=up?'#ff605e':'#24c997';ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.moveTo(x,y(high));ctx.lineTo(x,y(low));ctx.stroke();const yy=Math.min(y(open),y(close)),hh=Math.max(1,Math.abs(y(open)-y(close)));ctx.fillRect(x-candle/2,yy,candle,hh);});
  const drawLine=(values,color)=>{ctx.strokeStyle=color;ctx.lineWidth=1.4;ctx.beginPath();let active=false;values.forEach((v,idx)=>{if(v==null)return;const x=left+xStep*(idx+.5),yy=y(v);if(!active){ctx.moveTo(x,yy);active=true}else ctx.lineTo(x,yy);});ctx.stroke();};
  drawLine(sma(closes,5),'#f6c85f'); drawLine(sma(closes,20),'#4aa3ff'); drawLine(sma(closes,60),'#b283ff');
  ctx.fillStyle='#f6c85f';ctx.fillText('MA5',left,15);ctx.fillStyle='#4aa3ff';ctx.fillText('MA20',left+38,15);ctx.fillStyle='#b283ff';ctx.fillText('MA60',left+83,15);
  const dif=ema(closes,12).map((v,i)=>v-ema(closes,26)[i]); const dea=ema(dif,9); const hist=dif.map((v,i)=>(v-dea[i])*2); const abs=Math.max(...hist.map(Math.abs),...dif.map(Math.abs),...dea.map(Math.abs),1e-6); const zero=(macdTop+bottom)/2; const my=v=>zero-v/abs*(bottom-macdTop)*.42;
  ctx.strokeStyle='#1d2a3b';ctx.beginPath();ctx.moveTo(left,zero);ctx.lineTo(width-right,zero);ctx.stroke();
  hist.forEach((v,idx)=>{const x=left+xStep*(idx+.5);ctx.fillStyle=v>=0?'#ff605e':'#24c997';ctx.fillRect(x-candle/2,Math.min(zero,my(v)),candle,Math.max(1,Math.abs(my(v)-zero)));});
  const drawMacd=(values,color)=>{ctx.strokeStyle=color;ctx.beginPath();values.forEach((v,idx)=>{const x=left+xStep*(idx+.5),yy=my(v);idx?ctx.lineTo(x,yy):ctx.moveTo(x,yy)});ctx.stroke();};drawMacd(dif,'#4aa3ff');drawMacd(dea,'#e8a63e');
  ctx.fillStyle='#71839a';ctx.fillText('MACD',5,macdTop+8);ctx.fillText(data[0].date,left,bottom+14);ctx.fillText(data[data.length-1].date,width-82,bottom+14);
}

function scheduleEventReconnect() {
  clearTimeout(state.eventRetry);
  state.eventRetry = setTimeout(() => connectEvents(), 3000);
}

async function connectEvents() {
  if (state.eventAbort) state.eventAbort.abort();
  clearTimeout(state.eventRetry);
  if (state.modeTransition) return;
  const requestGeneration = authRequestGeneration(), sessionActive = state.sessionActive;
  const controller = new AbortController();
  state.eventAbort = controller;
  try {
    const response = await fetch('/api/events', {
      signal: controller.signal,
      cache: 'no-store',
      credentials:'same-origin',
    });
    if (response.status === 401) { if (requestGeneration === authRequestGeneration() && sessionActive === state.sessionActive) { state.sessionActive=false; showAuth('会话已失效，请重新登录'); } return; }
    if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`);
    qs('#connectionBadge').className='status-dot online';
    qs('#connectionBadge').textContent='实时连接';
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const watched = new Set(['decision_board.updated','instruments.updated','bars.updated','indicators.updated','forecasts.updated','quotes.updated','news.updated','signals.updated','holdings.updated','market_context.updated','report.generated']);
    let buffer = '';
    let timer = null;
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true}).replaceAll('\r\n', '\n');
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        let eventName = 'message';
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) eventName = line.slice(6).trim();
        }
        if (watched.has(eventName)) {
          clearTimeout(timer);
          timer = setTimeout(() => {
            // Both reads consume an already materialized snapshot; neither asks a
            // provider to refresh data from the browser.
            loadDecisionBoard(true);
            if (state.activeTab === 'signals') loadSignalCenter(true);
          }, 450);
        }
      }
    }
    if (!controller.signal.aborted) throw new Error('SSE stream closed');
  } catch (error) {
    if (controller.signal.aborted || state.modeTransition) return;
    qs('#connectionBadge').className='status-dot offline';
    qs('#connectionBadge').textContent='重连中';
    scheduleEventReconnect();
  }
}

function bindEvents() {
  qs('#authForm').addEventListener('submit', async event => {
    event.preventDefault();
    const error = qs('#authError'); error.textContent = '';
    try {
      const response = await fetch('/api/auth/login', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify({identifier:qs('#identifierInput').value.trim(), password:qs('#passwordInput').value})});
      if (!response.ok) { error.textContent = '登录失败，请检查凭据后重试'; return; }
      await refreshAuthIdentity(); advanceAuthRequestGeneration(); await loadBootstrap(); if (state.sessionActive) { connectEvents(); loadSettings(); loadAdminUsers(); }
    } catch (_) { error.textContent = '登录暂不可用，请稍后重试'; }
  });
  qs('#refreshButton').addEventListener('click', requestDecisionBoardRefresh);
  qs('#lockButton').addEventListener('click', async ()=>{ try { await api('/api/auth/logout',{method:'POST'}); } catch (_) {} state.sessionActive=false; advanceAuthRequestGeneration(); showAuth(); });
  qs('#adminCreateForm')?.addEventListener('submit', submitAdminCreate);
  qs('#adminResetPasswordForm')?.addEventListener('submit', submitAdminPasswordReset);
  qs('#adminResetCancelButton')?.addEventListener('click', () => { qs('#adminResetPasswordForm').reset(); qs('#adminResetPasswordForm').classList.add('hidden'); setAdminAccountStatus(); });
  qs('#adminUserList')?.addEventListener('click', event => {
    const control = event.target.closest('[data-admin-action]');
    if (!control) return;
    if (control.dataset.adminAction === 'reset') openAdminPasswordReset(control.dataset.userId);
    else runAdminLifecycleAction(event);
  });
  qsa('#tabs button').forEach(button=>button.addEventListener('click',()=>switchTab(button.dataset.tab)));
  qs('#decisionModeGrouped')?.addEventListener('click', () => { state.decisionUi.mode = 'grouped'; renderDecisionBoard(); });
  qs('#decisionModeGlobal')?.addEventListener('click', () => { state.decisionUi.mode = 'global'; renderDecisionBoard(); });
  qs('#decisionSearch')?.addEventListener('input', event => { state.decisionUi.filter = event.currentTarget.value; renderDecisionBoard(); });
  qs('#decisionHorizon')?.addEventListener('change', event => { state.decisionUi.horizon = Number(event.currentTarget.value); loadDecisionBoard(true); });
  qsa('#boardKindTabs button').forEach(button => button.addEventListener('click', () => {
    state.boardKind = button.dataset.boardKind;
    qsa('#boardKindTabs button').forEach(item => item.classList.toggle('active', item === button));
    renderBoards();
  }));
  const boardAdd = qs('#boardAddForm');
  if (boardAdd) boardAdd.addEventListener('submit', submitBoardFund);
  qsa('[data-close]').forEach(button=>button.addEventListener('click',()=>closeModal(button.dataset.close)));
  qsa('.overlay').forEach(overlay=>{
    overlay.addEventListener('click',event=>{if(event.target===overlay&&!overlay.classList.contains('auth-overlay')&&!['portfolioImportOverlay','portfolioConfirmOverlay'].includes(overlay.id))closeModal(overlay.id);});
    overlay.addEventListener('keydown', trapModalFocus);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      if (!qs('#portfolioConfirmOverlay').classList.contains('hidden')) closeModal('portfolioConfirmOverlay');
      else if (!qs('#portfolioImportOverlay').classList.contains('hidden')) cancelPortfolioImport();
      else qsa('.overlay:not(.hidden):not(.auth-overlay)').forEach(overlay => closeModal(overlay.id));
    }
  });
  qs('#newHoldingButton').addEventListener('click',()=>openHolding());
  qs('#watchlistAddButton').addEventListener('click',addWatchlistEntry);
  qs('#watchlistCodeInput').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();addWatchlistEntry();}});
  qs('#holdingForm').addEventListener('submit',saveHolding);
  qs('#portfolioImportButton').addEventListener('click', openPortfolioImport);
  qs('#portfolioImportCloseButton').addEventListener('click', cancelPortfolioImport);
  qs('#portfolioImportForm').addEventListener('submit', uploadPortfolioImport);
  qs('#portfolioImportCandidates').addEventListener('change', event => {
    const field = event.target.closest('[data-import-field]');
    const card = event.target.closest('[data-candidate-id]');
    if (field && card) scheduleImportCandidateSave(card);
  });
  qs('#portfolioImportCandidates').addEventListener('click', event => {
    const button = event.target.closest('.import-reject');
    const card = event.target.closest('[data-candidate-id]');
    if (button && card) rejectImportCandidate(card);
  });
  qs('#portfolioCancelButton').addEventListener('click', cancelPortfolioImport);
  qs('#portfolioConfirmButton').addEventListener('click', requestPortfolioConfirm);
  qs('#portfolioConfirmYes').addEventListener('click', confirmPortfolioImport);
  qs('#portfolioConfirmNo').addEventListener('click', () => closeModal('portfolioConfirmOverlay'));
  qs('#newsRefreshButton').addEventListener('click',event=>runTask('refresh_news',event.currentTarget));
  qs('#generateReportButton').addEventListener('click',event=>runTask('generate_report',event.currentTarget));
  qs('#settingsForm').addEventListener('submit',async event=>{event.preventDefault();if(blockFormalMutation('刷新频率设置保存'))return;const form=new FormData(event.currentTarget),payload={};for(const [k,v] of form.entries())payload[k]=Number(v);try{state.settings=await api('/api/settings',{method:'PUT',body:JSON.stringify(payload)});toast('刷新频率已保存');scheduleBrowserRefresh();}catch(error){toast(`保存失败：${error.message}`);}});
  qs('#marketSourceForm').addEventListener('submit', saveMarketSource);
  qs('#marketProbeButton').addEventListener('click', probeMarketSource);
  qs('#clearTushareTokenButton').addEventListener('click', clearStoredTushareToken);
  qs('#demoLoadButton').addEventListener('click', enterDemoMode);
  qs('#demoResetButton').addEventListener('click', resetDemoMode);
  qs('#demoExitButton').addEventListener('click', exitDemoMode);
  qs('#demoBannerExitButton').addEventListener('click', exitDemoMode);
  qs('#coefficientSlider').addEventListener('input', onCoefficientInput);
  qs('#coefficientSave').addEventListener('click', saveCoefficient);
  qsa('#frontTabs button').forEach(button => button.addEventListener('click', () => {
    state.signalFrontTab = button.dataset.front;
    renderFrontList();
  }));
  const curveCanvas = qs('#signalCurveCanvas');
  curveCanvas.addEventListener('mousemove', event => {
    const canvas = event.currentTarget;
    if (!canvas._curve || !canvas._layout) return;
    const rect = canvas.getBoundingClientRect();
    const relative = (event.clientX - rect.left - canvas._layout.left) / canvas._layout.xStep;
    const index = Math.max(0, Math.min(canvas._curve.length - 1, Math.round(relative - .5)));
    drawSignalCurveHover(index);
  });
  curveCanvas.addEventListener('mouseleave', () => { if (qs('#signalCurveCanvas')._curve) drawSignalCurve(); });
  window.addEventListener('resize',()=>{if(!qs('#detailOverlay').classList.contains('hidden') && state.detailCode && !state.decisionUi.openDetailCode) scheduleDetailBars(state.detailCode); if(state.activeTab==='signals') drawSignalCurve();});
}

async function start() {
  handleDecisionBoardRoute(); bindEvents(); renderTaskButtons();
  try { await refreshAuthIdentity(); } catch (_) { state.sessionActive = false; state.auth = {identifier: null, role: null}; renderAuthIdentity(); }
  if (!state.sessionActive) { showAuth(); return; }
  await loadBootstrap();
  // Auth-disabled servers report an authenticated anonymous browser from
  // /api/auth/me, preserving the existing local demo/test experience.
  if (state.data) { connectEvents(); loadSettings(); loadDecisionBoard(true); scheduleDecisionStatusPoll(); loadAdminUsers(); }
}

// Kept deliberately small so the pure ordering/formatting/escaping contract can
// be covered by Node without a browser DOM or a live provider.
globalThis.DecisionBoardUi = Object.freeze({
  api,
  detailHtml: decisionDetailHtml,
  groupedRows: decisionGroupedRows,
  headerHtml: decisionHeaderHtml,
  loadBootstrap,
  loadDecisionBoard,
  nextSort: decisionNextSort,
  percent: decisionPercent,
  rowHtml: decisionRowHtml,
  requestRefresh: requestDecisionBoardRefresh,
  state,
  tableHtml: decisionTableHtml,
  visibleRows: decisionVisibleRows,
});

document.addEventListener('DOMContentLoaded', start);
