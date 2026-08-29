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
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
function fmt(value, digits = 2, fallback = '—') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback;
  return Number(value).toFixed(digits);
}
function pct(value, digits = 2, ratio = false) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const n = Number(value) * (ratio ? 100 : 1);
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`;
}
function colorClass(value) { return Number(value || 0) >= 0 ? 'up' : 'down'; }
function safeHttpUrl(value) {
  if (!value) return '';
  try {
    const parsed = new URL(String(value), window.location.origin);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : '';
  } catch (_) { return ''; }
}
function timeText(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', {hour12:false});
}
function amountText(value) {
  const n = Number(value || 0);
  if (!n) return '—';
  if (n >= 1e8) return `${(n / 1e8).toFixed(2)}亿`;
  if (n >= 1e4) return `${(n / 1e4).toFixed(1)}万`;
  return n.toFixed(0);
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
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, {...options, headers});
  if (response.status === 401) {
    showAuth('令牌无效或已变更');
    throw new Error('unauthorized');
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { const payload = await response.json(); detail = payload.detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  const type = response.headers.get('content-type') || '';
  return type.includes('application/json') ? response.json() : response.text();
}

function showAuth(error = '') {
  qs('#authOverlay').classList.remove('hidden');
  qs('#authError').textContent = error;
  qs('#tokenInput').value = state.token;
  setTimeout(() => qs('#tokenInput').focus(), 30);
}
function hideAuth() { qs('#authOverlay').classList.add('hidden'); }

async function loadBootstrap(silent = false) {
  if (!state.token) { showAuth(); return; }
  if (!silent) qs('#refreshButton').disabled = true;
  try {
    const bootstrap = await api('/api/bootstrap');
    let reports = [];
    try {
      reports = await api('/api/reports');
    } catch (reportError) {
      console.warn('report list unavailable', reportError);
    }
    state.data = bootstrap;
    state.reports = reports;
    hideAuth();
    renderAll();
    scheduleBrowserRefresh();
  } catch (error) {
    if (error.message !== 'unauthorized') toast(`刷新失败：${error.message}`, 5000);
  } finally {
    qs('#refreshButton').disabled = false;
  }
}

function scheduleBrowserRefresh() {
  clearInterval(state.refreshTimer);
  const minutes = Number(state.settings?.quote_refresh_minutes || 3);
  state.refreshTimer = setInterval(() => loadBootstrap(true), Math.max(1, minutes) * 60 * 1000);
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
    <strong>市场宽度：</strong>${up} 涨 / ${down} 跌。当前信号以 <strong>${escapeHtml(Object.entries(stateCounts).sort((a,b)=>b[1]-a[1])[0]?.[0] || '暂无')}</strong> 为主。
    <strong>相对领先：</strong>${strongest.map(r => `${escapeHtml(r.name)}（${fmt(r.signal.score,1)}）`).join('、')}。
    <strong>风险靠前：</strong>${weakest.map(r => `${escapeHtml(r.name)}（${fmt(r.signal.score,1)}）`).join('、')}。
    所有预测均显示样本支持和区间；未校准预测不会获得高置信度。`;
}

function forecastCell(item) {
  if (!item || item.p_up === null) return '<span class="muted">—</span>';
  const cls = Number(item.expected_return || 0) >= 0 ? 'up' : 'down';
  return `<div class="metric-main ${cls}">${fmt(item.p_up * 100,1)}%</div><div class="metric-sub">中位 ${pct(item.q50,2,true)} · n=${item.sample_count}</div>`;
}
function instrumentRow(row) {
  const q = row.quote || {};
  const i = row.indicator || {};
  const v = i.values || {};
  const s = row.signal || {};
  const f = row.forecasts || {};
  const expired = s.expires_at && new Date(s.expires_at) < new Date();
  return `<tr class="clickable ${expired ? 'signal-expired' : ''}" data-code="${escapeHtml(row.ts_code)}">
    <td><div class="instrument-name">${escapeHtml(row.name)}</div><div class="instrument-meta">${escapeHtml(row.ts_code)} · ${escapeHtml(row.theme_l1 || '未分类')}/${escapeHtml(row.theme_l2 || '-')}</div></td>
    <td><div class="metric-main ${colorClass(q.pct_change)}">${q.price == null ? '—' : fmt(q.price,4)}</div><div class="metric-sub ${colorClass(q.pct_change)}">${pct(q.pct_change)} · ${escapeHtml(q.source || '')}</div></td>
    <td><div class="metric-main">${amountText(q.amount)}</div><div class="metric-sub">量比 ${fmt(v.volume_ratio,2)}</div></td>
    <td><div class="metric-main">${escapeHtml(i.trend_label || '—')}</div><div class="metric-sub">技术 ${fmt(i.technical_score,1)} / 风险 ${fmt(i.risk_score,1)}</div></td>
    <td><div class="metric-main ${Number(v.macd_hist || 0)>=0?'up':'down'}">${fmt(v.macd_hist,6)}</div><div class="metric-sub">DIF ${fmt(v.macd_dif,5)} / DEA ${fmt(v.macd_dea,5)}</div></td>
    <td><div class="metric-main">J ${fmt(v.kdj_j,1)}</div><div class="metric-sub">K ${fmt(v.kdj_k,1)} / D ${fmt(v.kdj_d,1)}</div></td>
    <td><div class="metric-main">${fmt(v.rsi14,1)}</div><div class="metric-sub">6:${fmt(v.rsi6,1)} / 12:${fmt(v.rsi12,1)}</div></td>
    <td><div class="metric-main">${v.td_buy_setup ?? '—'} / ${v.td_sell_setup ?? '—'}</div><div class="metric-sub">买 / 卖设置</div></td>
    <td><div class="metric-main ${colorClass(v.return_20d)}">${pct(v.return_20d,2,true)}</div><div class="metric-sub">60日 ${pct(v.return_60d,2,true)}</div></td>
    <td>${forecastCell(f['1'])}</td><td>${forecastCell(f['5'])}</td><td>${forecastCell(f['20'])}</td>
    <td><span class="badge ${stateClass(s.state)}">${escapeHtml(s.state || '待计算')}</span><div class="metric-sub">分 ${fmt(s.score,1)} · conf ${fmt(s.confidence,1)}</div></td>
  </tr>`;
}
function renderInstruments() {
  const body = qs('#instrumentTable tbody');
  const rows = [...(state.data.instruments || [])].sort((a,b) => Number(b.signal?.score || -1) - Number(a.signal?.score || -1));
  body.innerHTML = rows.length ? rows.map(instrumentRow).join('') : '<tr class="loading-row"><td colspan="13">暂无数据，请运行 bootstrap</td></tr>';
  qsa('#instrumentTable tbody tr[data-code]').forEach(row => row.addEventListener('click', () => openDetail(row.dataset.code)));
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
  qs('#holdingTable tbody').innerHTML = holdings.length ? holdings.map(h => `<tr><td><div class="instrument-name">${escapeHtml(h.name)}</div><div class="instrument-meta">${escapeHtml(h.ts_code)}</div></td><td>${fmt(h.shares,4)}</td><td>${fmt(h.cost_price,4)}</td><td>${fmt(h.latest_price,4)}</td><td>${amountText(h.market_value)}</td><td class="${colorClass(h.pnl)}">${fmt(h.pnl,2)} / ${h.pnl_pct==null?'—':pct(h.pnl_pct)}</td><td>${fmt(h.current_weight*100,1)}%</td><td>${h.target_weight==null?'—':fmt(h.target_weight*100,1)+'%'}</td><td><button class="small-button edit-holding" data-code="${escapeHtml(h.ts_code)}">修改</button> <button class="small-button danger delete-holding" data-code="${escapeHtml(h.ts_code)}">删除</button></td></tr>`).join('') : '<tr class="loading-row"><td colspan="9">尚未录入持仓</td></tr>';
  qsa('.edit-holding').forEach(b => b.addEventListener('click', () => openHolding(b.dataset.code)));
  qsa('.delete-holding').forEach(b => b.addEventListener('click', () => deleteHolding(b.dataset.code)));
  const select = qs('#holdingCode');
  select.innerHTML = (state.data.instruments || []).map(r => `<option value="${escapeHtml(r.ts_code)}">${escapeHtml(r.ts_code)} · ${escapeHtml(r.name)}</option>`).join('');
}

function renderNews() {
  const rows = state.data.news || [];
  qs('#newsList').innerHTML = rows.length ? rows.map(item => {
    const href = safeHttpUrl(item.url);
    const title = href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a>` : escapeHtml(item.title);
    return `<article class="news-card"><div><h3>${title}</h3><div class="news-meta">${escapeHtml(item.source)} · ${timeText(item.published_at)} · ${escapeHtml((item.affected_themes || []).join(' / '))}</div>${item.facts?.length ? `<p><strong>事实：</strong>${escapeHtml(item.facts.join('；'))}</p>` : ''}${item.inferences?.length ? `<div class="news-facts">推断：${escapeHtml(item.inferences.join('；'))}</div>` : ''}${item.risk_flags?.length ? `<div class="news-facts amber">风险：${escapeHtml(item.risk_flags.join('；'))}</div>` : ''}</div><div><div class="news-score ${colorClass(item.impact_score)}">${Number(item.impact_score || 0)>=0?'+':''}${fmt(item.impact_score,2)}</div><div class="news-meta">${escapeHtml(item.impact_direction || '中性')} · ${escapeHtml(item.impact_horizon || '-')}</div></div></article>`;
  }).join('') : '<div class="loading-row">暂无新闻；可在“系统”中运行 refresh_news。</div>';
}

async function downloadReport(filename) {
  try {
    const response = await fetch(`/api/reports/${encodeURIComponent(filename)}`, {headers: {Authorization: `Bearer ${state.token}`}});
    if (response.status === 401) { showAuth('令牌无效或已变更'); return; }
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  } catch (error) { toast(`报告下载失败：${error.message}`, 5000); }
}

async function loadSettings() {
  try {
    state.settings = await api('/api/settings');
    for (const [key,value] of Object.entries(state.settings)) {
      const input = qs(`[name="${key}"]`, qs('#settingsForm'));
      if (input) input.value = value;
    }
    scheduleBrowserRefresh();
  } catch (error) { toast(`读取设置失败：${error.message}`); }
}
function renderSystem() {
  const providers = state.data.provider_health || [];
  qs('#providerTable tbody').innerHTML = providers.length ? providers.map(r => `<tr><td>${timeText(r.created_at)}</td><td>${escapeHtml(r.operation)}</td><td>${escapeHtml(r.provider)}</td><td><span class="badge ${r.status==='ok'||r.status==='fallback_used'?'entry':'reduce'}">${escapeHtml(r.status)}</span></td><td>${fmt(r.latency_ms,1)} ms</td><td>${r.record_count}</td><td class="muted">${escapeHtml(r.reason || '')}</td></tr>`).join('') : '<tr><td colspan="7">暂无审计记录</td></tr>';
  const tasks = state.data.tasks || [];
  qs('#taskTable tbody').innerHTML = tasks.length ? tasks.map(r => `<tr><td>${timeText(r.started_at)}</td><td>${escapeHtml(r.task_name)}</td><td><span class="badge ${r.status==='succeeded'?'entry':r.status==='failed'?'reduce':'probe'}">${escapeHtml(r.status)}</span></td><td class="muted">${escapeHtml(r.run_id)}</td><td class="down">${escapeHtml(r.error || '')}</td></tr>`).join('') : '<tr><td colspan="5">暂无任务记录</td></tr>';
  const reports = state.reports || [];
  qs('#reportTable tbody').innerHTML = reports.length ? reports.map(r => `<tr><td>${timeText(r.as_of_time)}</td><td>${escapeHtml(r.type)}</td><td>${escapeHtml(r.filename)}</td><td class="muted">${escapeHtml(String(r.content_hash || '').slice(0,16))}…</td><td><button class="small-button download-report" data-file="${escapeHtml(r.filename)}">下载</button></td></tr>`).join('') : '<tr><td colspan="5">暂无报告</td></tr>';
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
  renderSummary(); renderNarrative(); renderInstruments(); renderHoldings(); renderNews(); renderSystem(); renderSignalCenter();
}

function switchTab(tab) {
  state.activeTab = tab;
  qsa('.view').forEach(v => v.classList.toggle('active', v.id === `view-${tab}`));
  qsa('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
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
  qs('#holdingOverlay').classList.remove('hidden');
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
    qs('#holdingOverlay').classList.add('hidden'); toast('持仓已保存'); await loadBootstrap(true);
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
  const i = row.indicator || {}, v = i.values || {}, s = row.signal || {}, q = row.quote || {};
  qs('#detailContent').innerHTML = `<div class="eyebrow">${escapeHtml(row.theme_l1 || '')} / ${escapeHtml(row.theme_l2 || '')}</div><h2>${escapeHtml(row.name)} <span class="muted">${escapeHtml(row.ts_code)}</span></h2><div class="detail-grid">
    ${[['最新价格',fmt(q.price,4)],['今日涨跌',pct(q.pct_change)],['技术分',fmt(i.technical_score,1)],['风险分',fmt(i.risk_score,1)],['信号',s.state||'—'],['信号分',fmt(s.score,1)],['MACD柱',fmt(v.macd_hist,6)],['KDJ J',fmt(v.kdj_j,1)],['RSI14',fmt(v.rsi14,1)],['量比',fmt(v.volume_ratio,2)],['TD买/卖',`${v.td_buy_setup??'—'}/${v.td_sell_setup??'—'}`],['溢价率',q.premium_rate==null?'—':pct(q.premium_rate)]].map(([label,value])=>`<div class="detail-metric"><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></div>`).join('')}</div><div class="reason-box"><strong>理由：</strong>${escapeHtml((s.reasons||[]).join('；')||'暂无')}<br><span class="amber"><strong>风险：</strong>${escapeHtml((s.risks||[]).join('；')||'暂无')}</span></div>`;
  qs('#detailOverlay').classList.remove('hidden');
  try { const bars = await api(`/api/instruments/${encodeURIComponent(code)}/bars?limit=220`); drawChart(bars); }
  catch (error) { toast(`K线加载失败：${error.message}`); }
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
  const controller = new AbortController();
  state.eventAbort = controller;
  try {
    const response = await fetch('/api/events', {
      headers: {Authorization: `Bearer ${state.token}`},
      signal: controller.signal,
      cache: 'no-store',
    });
    if (response.status === 401) { showAuth('令牌无效或已变更'); return; }
    if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`);
    qs('#connectionBadge').className='status-dot online';
    qs('#connectionBadge').textContent='实时连接';
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const watched = new Set(['instruments.updated','bars.updated','indicators.updated','forecasts.updated','quotes.updated','news.updated','signals.updated','holdings.updated','report.generated']);
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
    event.preventDefault(); state.token=qs('#tokenInput').value.trim(); localStorage.setItem('fundDecisionToken',state.token); await loadBootstrap(); connectEvents();
  });
  qs('#refreshButton').addEventListener('click',()=>loadBootstrap());
  qs('#lockButton').addEventListener('click',()=>{state.token='';localStorage.removeItem('fundDecisionToken');if(state.eventAbort)state.eventAbort.abort();clearTimeout(state.eventRetry);showAuth();});
  qsa('#tabs button').forEach(button=>button.addEventListener('click',()=>switchTab(button.dataset.tab)));
  qsa('[data-close]').forEach(button=>button.addEventListener('click',()=>qs(`#${button.dataset.close}`).classList.add('hidden')));
  qsa('.overlay').forEach(overlay=>overlay.addEventListener('click',event=>{if(event.target===overlay&&!overlay.classList.contains('auth-overlay'))overlay.classList.add('hidden');}));
  qs('#newHoldingButton').addEventListener('click',()=>openHolding());
  qs('#holdingForm').addEventListener('submit',saveHolding);
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
  window.addEventListener('resize',()=>{if(!qs('#detailOverlay').classList.contains('hidden')){const code=qs('#detailContent .muted')?.textContent; if(code) api(`/api/instruments/${encodeURIComponent(code)}/bars?limit=220`).then(drawChart).catch(()=>{});} if(state.activeTab==='signals') drawSignalCurve();});
}

async function start() {
  bindEvents(); renderTaskButtons();
  if (!state.token) showAuth();
  else { await loadBootstrap(); connectEvents(); }
  loadSettings();
}

document.addEventListener('DOMContentLoaded', start);
