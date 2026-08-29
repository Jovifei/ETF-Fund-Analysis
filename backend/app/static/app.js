'use strict';

const qs = (selector, root = document) => root.querySelector(selector);
const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {
  token: localStorage.getItem('fundDecisionToken') || '',
  data: null,
  settings: null,
  reports: [],
  signalCenter: null,
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
  if (['加仓', '小幅加仓'].includes(label)) return 'add';
  if (['持有', '观察'].includes(label)) return 'hold';
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

async function api(path, options = {}) {
  const {authGeneration = state.authRequestGeneration, ...requestOptions} = options;
  const headers = new Headers(requestOptions.headers || {});
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  if (requestOptions.body instanceof FormData) {
    headers.delete('Content-Type');
    for (const name of [...headers.keys()]) if (name.toLowerCase() === 'content-type') headers.delete(name);
  } else if (requestOptions.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, {...requestOptions, headers});
  if (response.status === 401) {
    if (authGeneration === state.authRequestGeneration) showAuth('令牌无效或已变更');
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
  qs('#authOverlay').classList.remove('hidden');
  qs('#authError').textContent = error;
  qs('#tokenInput').value = state.token;
  setTimeout(() => qs('#tokenInput').focus(), 30);
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
  if (id === 'detailOverlay') cancelDetailRequest();
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
  if (!code || qs('#detailOverlay').classList.contains('hidden')) return;
  cancelDetailRequest();
  const requestToken = state.detailRequestToken;
  const controller = new AbortController();
  state.detailRequestController = controller;
  api(`/api/instruments/${encodeURIComponent(code)}/bars?limit=220`, {signal: controller.signal})
    .then(bars => {
      if (requestToken === state.detailRequestToken && state.detailCode === code && !qs('#detailOverlay').classList.contains('hidden')) drawChart(bars);
    })
    .catch(error => {
      if (error.name !== 'AbortError' && requestToken === state.detailRequestToken) toast(`K线加载失败：${error.message}`);
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
  if (!state.token) { showAuth(); return; }
  const requestGeneration = authRequestGeneration(), requestToken = state.token, controller = new AbortController();
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
    if (requestGeneration !== authRequestGeneration() || requestToken !== state.token || controller.signal.aborted) return;
    state.data = bootstrap;
    state.reports = reports;
    hideAuth();
    renderAll();
    scheduleBrowserRefresh();
  } catch (error) {
    if (error.name !== 'AbortError' && requestGeneration === authRequestGeneration() && requestToken === state.token) toast(`刷新失败：${error.message}`, 5000);
  } finally {
    if (state.bootstrapController === controller) { state.bootstrapController = null; qs('#refreshButton').disabled = false; }
  }
}

function scheduleBrowserRefresh() {
  clearInterval(state.refreshTimer);
  const minutes = Number(state.settings?.quote_refresh_minutes || 3);
  state.refreshTimer = setInterval(() => loadBootstrap(true), Math.max(1, minutes) * 60 * 1000);
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
  const rows = mergeMarketContext(state.data.market_context);
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
  qs('#environmentLabel').textContent = `${s.app_env} · ${s.provider}`;
  const warning = qs('#globalWarning');
  if (s.is_mock || s.live_quote_count < s.instrument_count) {
    warning.textContent = s.is_mock
      ? '当前为 Mock 演示数据：页面功能可验证，但所有结论均不可用于真实投资判断。'
      : `仅 ${s.live_quote_count}/${s.instrument_count} 个标的具备执行级实时行情；退化数据会压低置信度并阻断操作级信号。`;
    warning.classList.remove('hidden');
  } else warning.classList.add('hidden');
}

function renderNarrative() {
  const rows = state.data.instruments || [];
  const usable = rows.filter(r => r.signal);
  if (!usable.length) { qs('#marketNarrative').textContent = '尚未生成信号，请先在“系统”中执行完整初始化。'; return; }
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
  return `<div class="forecast-surface" aria-label="FORECAST · 非实际结果">
    <div class="forecast-label">FORECAST · 非实际结果</div>
    <div class="forecast-horizon">${escapeHtml(f.horizon == null ? '—' : `${f.horizon}日`)}</div>
    <div class="forecast-value">p(up) ${escapeHtml(f.p_up == null ? '—' : pct(f.p_up, 1, true))}</div>
    <div class="forecast-range">E[r] ${escapeHtml(pct(f.expected_return, 2, true))} · q10/q50/q90 ${escapeHtml(pct(f.q10, 2, true))} / ${escapeHtml(pct(f.q50, 2, true))} / ${escapeHtml(pct(f.q90, 2, true))}</div>
    <div class="forecast-meta">n=${escapeHtml(f.sample_count == null ? '—' : f.sample_count)} · ${escapeHtml(f.calibration_status || 'not_calibrated')} · ${escapeHtml(f.model_version || '—')}</div>
    <div class="forecast-meta">as_of ${escapeHtml(timeText(f.as_of_date))} · generated ${escapeHtml(timeText(f.generated_at))} · cutoff ${escapeHtml(timeText(f.data_cutoff))}</div>
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
  const body = qs('#instrumentTable tbody');
  const rows = [...(state.data.instruments || [])].sort((a,b) => Number(b.signal?.score || -1) - Number(a.signal?.score || -1));
  body.innerHTML = rows.length ? rows.map(instrumentRow).join('') : '<tr class="loading-row"><td colspan="13">暂无数据，请运行 bootstrap</td></tr>';
  qsa('#instrumentTable tbody tr[data-code]').forEach(row => {
    const open = () => openDetail(row.dataset.code);
    row.addEventListener('click', open);
    row.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
    });
  });
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
  qs('#holdingTable tbody').innerHTML = holdings.length ? holdings.map(h => `<tr><td><div class="instrument-name">${displayIdentity(h.ts_code, h.name)}</div><div class="instrument-meta">${escapeHtml(h.theme_l1 || '未分类')}/${escapeHtml(h.theme_l2 || '-')}</div></td><td>${escapeHtml(fmt(h.shares,4))}</td><td>${escapeHtml(fmt(h.cost_price,4))}</td><td>${escapeHtml(fmt(h.latest_price,4))}</td><td>${escapeHtml(amountText(h.market_value))}</td><td class="${escapeHtml(colorClass(h.pnl))}">${escapeHtml(fmt(h.pnl,2))} / ${escapeHtml(holdingPnlPercent(h))}</td><td>${escapeHtml(fmt(h.current_weight*100,1))}%</td><td>${h.target_weight==null?'—':escapeHtml(fmt(h.target_weight*100,1))+'%'}</td><td><button class="small-button edit-holding" data-code="${escapeHtml(h.ts_code)}">修改</button> <button class="small-button danger delete-holding" data-code="${escapeHtml(h.ts_code)}">删除</button></td></tr>`).join('') : '<tr class="loading-row"><td colspan="9">尚未录入持仓</td></tr>';
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
  if (state.cancelPromise) await state.cancelPromise;
  if (state.holdingImport?.cancelError) { openModal('portfolioImportOverlay', '#portfolioCancelButton'); return; }
  resetImportWorkflow(); openModal('portfolioImportOverlay', '#portfolioImportFile'); renderCloudReview();
}
async function uploadPortfolioImport(event) {
  event.preventDefault(); const input = qs('#portfolioImportFile'), file = input.files?.[0];
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
  if (state.cancelPromise) return state.cancelPromise;
  const workflow = state.holdingImport, sessionId = workflow?.sessionId || '';
  if (!sessionId) { newImportGeneration(); resetImportWorkflow({advance:false}); closeModal('portfolioConfirmOverlay'); closeModal('portfolioImportOverlay'); return; }
  const generation = newImportGeneration(), authGenerationAtCancel = authRequestGeneration(), capturedToken = state.token;
  workflow.generation = generation; workflow.canceling = true; workflow.cancelError = false; workflow.busy = true; workflow.status = '正在取消导入…'; setImportInteractionDisabled(true); renderImportReview();
  const controller = new AbortController(); state.cancelController = controller;
  const cancelPromise = (async () => {
    try {
      await api(`/api/holding-imports/${encodeURIComponent(sessionId)}/cancel`, {method:'POST', headers: capturedToken ? {Authorization:`Bearer ${capturedToken}`} : {}, signal:controller.signal, authGeneration:authGenerationAtCancel});
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
    return `<article class="news-card"><div><h3>${title}</h3><div class="news-meta">${escapeHtml(item.source)} · ${escapeHtml(timeText(item.published_at))} · ${escapeHtml((item.affected_themes || []).join(' / '))}</div>${item.facts?.length ? `<p><strong>事实：</strong>${escapeHtml(item.facts.join('；'))}</p>` : ''}${item.inferences?.length ? `<div class="news-facts">推断：${escapeHtml(item.inferences.join('；'))}</div>` : ''}${item.risk_flags?.length ? `<div class="news-facts amber">风险：${escapeHtml(item.risk_flags.join('；'))}</div>` : ''}</div><div><div class="news-score ${escapeHtml(colorClass(item.impact_score))}">${impact}</div><div class="news-meta">${escapeHtml(item.impact_direction || '中性')} · ${escapeHtml(item.impact_horizon || '-')}</div></div></article>`;
  }).join('') : '<div class="loading-row">暂无新闻；可在“系统”中运行 refresh_news。</div>';
}

async function downloadReport(filename) {
  const requestGeneration = authRequestGeneration(), requestToken = state.token;
  try {
    const response = await fetch(`/api/reports/${encodeURIComponent(filename)}`, {headers: {Authorization: `Bearer ${state.token}`}});
    if (response.status === 401) { if (requestGeneration === authRequestGeneration() && requestToken === state.token) showAuth('令牌无效或已变更'); return; }
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  } catch (error) { toast(`报告下载失败：${error.message}`, 5000); }
}

async function loadSettings() {
  if (!state.token) return;
  const requestGeneration = authRequestGeneration(), requestToken = state.token, controller = new AbortController();
  state.settingsController?.abort(); state.settingsController = controller;
  try {
    const settings = await api('/api/settings', {signal:controller.signal, authGeneration:requestGeneration});
    if (requestGeneration !== authRequestGeneration() || requestToken !== state.token || controller.signal.aborted) return;
    state.settings = settings;
    for (const [key,value] of Object.entries(state.settings)) {
      const input = qs(`[name="${key}"]`, qs('#settingsForm'));
      if (input) input.value = value;
    }
    scheduleBrowserRefresh();
  } catch (error) { if (error.name !== 'AbortError' && requestGeneration === authRequestGeneration() && requestToken === state.token) toast(`读取设置失败：${error.message}`); }
  finally { if (state.settingsController === controller) state.settingsController = null; }
}
function renderSystem() {
  const providers = state.data.provider_health || [];
  qs('#providerTable tbody').innerHTML = providers.length ? providers.map(r => `<tr><td>${escapeHtml(timeText(r.created_at))}</td><td>${escapeHtml(r.operation)}</td><td>${escapeHtml(r.provider)}</td><td><span class="badge ${r.status==='ok'||r.status==='fallback_used'?'entry':'reduce'}">${escapeHtml(r.status)}</span></td><td>${escapeHtml(fmt(r.latency_ms,1))} ms</td><td>${escapeHtml(fmt(r.record_count,0))}</td><td class="muted">${escapeHtml(r.reason || '')}</td></tr>`).join('') : '<tr><td colspan="7">暂无审计记录</td></tr>';
  const tasks = state.data.tasks || [];
  qs('#taskTable tbody').innerHTML = tasks.length ? tasks.map(r => `<tr><td>${escapeHtml(timeText(r.started_at))}</td><td>${escapeHtml(r.task_name)}</td><td><span class="badge ${r.status==='succeeded'?'entry':r.status==='failed'?'reduce':'probe'}">${escapeHtml(r.status)}</span></td><td class="muted">${escapeHtml(r.run_id)}</td><td class="down">${escapeHtml(r.error || '')}</td></tr>`).join('') : '<tr><td colspan="5">暂无任务记录</td></tr>';
  const reports = state.reports || [];
  qs('#reportTable tbody').innerHTML = reports.length ? reports.map(r => `<tr><td>${escapeHtml(timeText(r.as_of_time))}</td><td>${escapeHtml(r.type)}</td><td>${escapeHtml(r.filename)}</td><td class="muted">${escapeHtml(String(r.content_hash || '').slice(0,16))}…</td><td><button class="small-button download-report" data-file="${escapeHtml(r.filename)}">下载</button></td></tr>`).join('') : '<tr><td colspan="5">暂无报告</td></tr>';
  qsa('.download-report').forEach(button => button.addEventListener('click', () => downloadReport(button.dataset.file)));
}
function renderTaskButtons() {
  const tasks = [
    ['refresh_quotes','刷新行情'],['refresh_news','更新新闻'],['refresh_signals','重算信号'],['refresh_bars','更新日线'],['refresh_indicators','重算指标'],['refresh_forecasts','更新预测'],['generate_report','生成报告'],['validate_forecasts','验证预测'],['backtest_rotation','轮动回测'],['full_pipeline','完整流水线']
  ];
  qs('#taskButtons').innerHTML = tasks.map(([name,label]) => `<button class="ghost task-run" data-task="${name}">${label}</button>`).join('');
  qsa('.task-run').forEach(b => b.addEventListener('click', () => runTask(b.dataset.task, b)));
}

async function loadSignalCenter(silent = false, coefficientOverride = null) {
  if (!state.token || state.signalCenterLoading) return;
  state.signalCenterLoading = true;
  if (!silent) qs('#signalCurveMeta').textContent = '加载中...';
  try {
    const query = coefficientOverride == null ? '' : `?coefficient=${encodeURIComponent(coefficientOverride)}`;
    state.signalCenter = await api(`/api/signals/center${query}`);
    renderSignalCenter();
  } catch (error) {
    if (error.message !== 'unauthorized') toast(`信号中心加载失败：${error.message}`, 5000);
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
    `${sector.member_count} 只`,
  ].filter(Boolean).join(' · ');
  return `<div class="sector-row">
    <div class="sector-rank">${sector.rank}</div>
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
  const value = Number(qs('#coefficientSlider').value);
  try {
    state.settings = await api('/api/settings', {method: 'PUT', body: JSON.stringify({signal_center_coefficient: value})});
    toast(`信号系数已保存为 ${value.toFixed(2)}`);
    await loadSignalCenter(true);
  } catch (error) { toast(`保存失败：${error.message}`, 5000); }
}

function renderAll() {
  renderSummary(); renderNarrative(); renderMarketContext(); renderInstruments(); renderHoldings(); renderNews(); renderSystem(); renderSignalCenter();
}

function switchTab(tab) {
  state.activeTab = tab;
  qsa('.view').forEach(v => v.classList.toggle('active', v.id === `view-${tab}`));
  qsa('#tabs button').forEach(b => { const selected = b.dataset.tab === tab; b.classList.toggle('active', selected); b.setAttribute('aria-selected', String(selected)); });
  if (tab === 'system' && !state.settings) loadSettings();
  if (tab === 'signals' && !state.signalCenter) loadSignalCenter();
}

function openHolding(code = null) {
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
  if (!confirm(`删除 ${code} 的持仓记录？`)) return;
  try { await api(`/api/holdings/${encodeURIComponent(code)}`, {method:'DELETE'}); toast('已删除'); await loadBootstrap(true); }
  catch (error) { toast(`删除失败：${error.message}`); }
}

async function runTask(name, button = null) {
  if (button) button.disabled = true;
  qs('#taskOutput').textContent = `运行 ${name} 中...`;
  try {
    const payload = name === 'refresh_bars' ? {lookback_days: 30} : {};
    const result = await api(`/api/tasks/${encodeURIComponent(name)}`, {method:'POST', body:JSON.stringify(payload)});
    qs('#taskOutput').textContent = JSON.stringify(result, null, 2);
    toast(`${name} 完成`); await loadBootstrap(true);
  } catch (error) { qs('#taskOutput').textContent = `${name} 失败\n${error.message}`; toast(`任务失败：${error.message}`,5000); }
  finally { if (button) button.disabled = false; }
}

async function openDetail(code) {
  const row = (state.data.instruments || []).find(r => r.ts_code === code);
  if (!row) return;
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
  if (!state.token) return;
  const requestGeneration = authRequestGeneration(), requestToken = state.token;
  const controller = new AbortController();
  state.eventAbort = controller;
  try {
    const response = await fetch('/api/events', {
      headers: {Authorization: `Bearer ${state.token}`},
      signal: controller.signal,
      cache: 'no-store',
    });
    if (response.status === 401) { if (requestGeneration === authRequestGeneration() && requestToken === state.token) showAuth('令牌无效或已变更'); return; }
    if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`);
    qs('#connectionBadge').className='status-dot online';
    qs('#connectionBadge').textContent='实时连接';
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const watched = new Set(['instruments.updated','bars.updated','indicators.updated','forecasts.updated','quotes.updated','news.updated','signals.updated','holdings.updated','market_context.updated','report.generated']);
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
            loadBootstrap(true);
            if (state.activeTab === 'signals') loadSignalCenter(true);
          }, 450);
        }
      }
    }
    if (!controller.signal.aborted) throw new Error('SSE stream closed');
  } catch (error) {
    if (controller.signal.aborted) return;
    qs('#connectionBadge').className='status-dot offline';
    qs('#connectionBadge').textContent='重连中';
    scheduleEventReconnect();
  }
}

function bindEvents() {
  qs('#authForm').addEventListener('submit', async event => {
    event.preventDefault(); state.token=qs('#tokenInput').value.trim(); localStorage.setItem('fundDecisionToken',state.token); advanceAuthRequestGeneration(); await loadBootstrap(); if (state.token) { connectEvents(); loadSettings(); }
  });
  qs('#refreshButton').addEventListener('click',()=>loadBootstrap());
  qs('#lockButton').addEventListener('click',()=>{state.token='';localStorage.removeItem('fundDecisionToken');advanceAuthRequestGeneration();showAuth();});
  qsa('#tabs button').forEach(button=>button.addEventListener('click',()=>switchTab(button.dataset.tab)));
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
  qs('#settingsForm').addEventListener('submit',async event=>{event.preventDefault();const form=new FormData(event.currentTarget),payload={};for(const [k,v] of form.entries())payload[k]=Number(v);try{state.settings=await api('/api/settings',{method:'PUT',body:JSON.stringify(payload)});toast('刷新频率已保存');scheduleBrowserRefresh();}catch(error){toast(`保存失败：${error.message}`);}});
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
  window.addEventListener('resize',()=>{if(!qs('#detailOverlay').classList.contains('hidden') && state.detailCode) scheduleDetailBars(state.detailCode); if(state.activeTab==='signals') drawSignalCurve();});
}

async function start() {
  bindEvents(); renderTaskButtons();
  if (!state.token) showAuth();
  else { await loadBootstrap(); if (state.token) { connectEvents(); loadSettings(); } }
}

document.addEventListener('DOMContentLoaded', start);
