'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const state = {
  sessionActive: false,
  summary: null,
  detail: null,
  mode: '综合',
  resizeTimer: null,
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}
function number(value) { return value !== null && value !== undefined && Number.isFinite(Number(value)); }
function fmt(value, digits = 2, fallback = '—') { return number(value) ? Number(value).toFixed(digits) : fallback; }
function pctRatio(value, digits = 2) { return number(value) ? `${Number(value) >= 0 ? '+' : ''}${(Number(value) * 100).toFixed(digits)}%` : '—'; }
function pctPoint(value, digits = 2) { return number(value) ? `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(digits)}%` : '—'; }
function color(value) { return !number(value) ? 'neutral' : Number(value) >= 0 ? 'up' : 'down'; }
function actionClass(action) {
  if (action === '可加仓' || action === '可入场') return 'buy';
  if (action === '可试探') return 'probe';
  if (action === '观望') return 'hold';
  if (action === '减仓') return 'reduce';
  return 'data';
}
function timeText(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', {hour12:false, timeZone:'Asia/Shanghai'});
}
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (String(options.method || 'GET').toUpperCase() !== 'GET') {
    const csrf = String(document.cookie || '').split('; ').find(value => value.startsWith('__Host-fund-csrf=') || value.startsWith('fund-csrf='))?.split('=').slice(1).join('');
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf));
  }
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, {...options, headers, credentials:'same-origin'});
  if (response.status === 401) {
    showAuth();
    state.sessionActive = false;
    throw new Error('需要重新登录');
  }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { const payload = await response.json(); detail = payload.detail || detail; } catch (_) {}
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return response.json();
}
function showAuth() { $('#authOverlay').classList.remove('hidden'); $('#passwordInput').value=''; $('#identifierInput').focus(); }
function hideAuth() { $('#authOverlay').classList.add('hidden'); }

function summaryCard(label, value, note, accent) {
  return `<article class="summary-card" style="--accent:${accent}"><div class="value">${escapeHtml(value)}</div><div class="label">${escapeHtml(label)}</div><div class="note">${escapeHtml(note)}</div></article>`;
}
function renderSummary(data) {
  state.summary = data;
  const counts = data.counts || {};
  $('#summaryCards').innerHTML = [
    summaryCard('可加仓', counts['可加仓'] || 0, 'canonical 五档 · 加仓候选', '#27e48a'),
    summaryCard('可入场', counts['可入场'] || 0, 'canonical 五档 · 入场候选', '#4aa8ff'),
    summaryCard('可试探', counts['可试探'] || 0, 'canonical 五档 · 弱信号', '#ffb020'),
    summaryCard('观望', counts['观望'] || 0, 'canonical 五档 · 等待确认', '#8aa4bd'),
    summaryCard('减仓', counts['减仓'] || 0, 'canonical 五档 · 风险复核', '#ff5b61'),
    summaryCard('标的总数', (data.rows || []).length, '自动订单永久关闭', '#28d7e5'),
  ].join('');
  $('#generatedAt').textContent = `生成：${timeText(data.generated_at)}`;
  const windowInfo = data.decision_window || {};
  $('#heroMeta').innerHTML = `决策窗口 <strong>${escapeHtml(windowInfo.start || '14:20')}–${escapeHtml(windowInfo.end || '14:40')}</strong><br>目标时刻 <strong>${escapeHtml(windowInfo.target || '14:30')}</strong><br>历史14:30回测 <strong>${escapeHtml(data.historical_1430_backtest || 'not_qualified')}</strong>`;
  $('#warningBanner').innerHTML = (data.disclaimers || []).map(item => `• ${escapeHtml(item)}`).join('<br>');
  renderRows(data.rows || []);
}
function renderRows(rows) {
  const body = $('#decisionRows');
  if (!rows.length) { body.innerHTML = '<tr><td colspan="12" class="empty">尚无可展示标的，请先同步日线、指标与预测。</td></tr>'; return; }
  body.innerHTML = rows.map(row => {
    const s = row.component_scores || {};
    const m = row.structure_metrics || {};
    return `<tr class="clickable" data-code="${escapeHtml(row.ts_code)}">
      <td><div class="instrument-name">${escapeHtml(row.name)}</div><div class="instrument-code">${escapeHtml(row.ts_code)} · ${escapeHtml(row.theme_l1 || '未分类')}</div></td>
      <td><div>${fmt(row.current_price, 3)}</div><div class="${color(row.today_pct_change)}">${pctPoint(row.today_pct_change)}</div></td>
      <td><span class="score">${fmt(row.score,1)}</span></td>
      <td><span class="metric">${fmt(s.trend,1)}</span></td>
      <td><span class="metric">${fmt(s.momentum,1)}</span></td>
      <td><span class="metric">${fmt(s.volume_flow,1)}</span></td>
      <td><span class="metric">${fmt(s.structure,1)}</span></td>
      <td><span class="metric">${fmt(s.forecast,1)}</span></td>
      <td class="down">${fmt(m.support,3)}</td>
      <td class="up">${fmt(m.resistance,3)}</td>
      <td>${fmt(m.risk_reward,2)}</td>
      <td><span class="chip ${actionClass(row.action)}">${escapeHtml(row.action)}</span>${row.actionable ? '' : '<div class="instrument-code">研究态</div>'}</td>
    </tr>`;
  }).join('');
  body.querySelectorAll('tr[data-code]').forEach(row => row.addEventListener('click', () => { window.location.assign(`/etf/${encodeURIComponent(row.dataset.code)}`); }));
}

async function loadSummary() {
  $('#decisionRows').innerHTML = '<tr><td colspan="12" class="empty">正在计算 14:30 工作台…</td></tr>';
  try {
    const data = await api('/api/workbench/1430/summary');
    hideAuth();
    renderSummary(data);
  } catch (error) {
    $('#warningBanner').textContent = `加载失败：${error.message}`;
  }
}

function renderScores(row) {
  const scores = row.component_scores || {};
  $('#detailScores').innerHTML = Object.entries({趋势:scores.trend, 动量:scores.momentum, 量能资金:scores.volume_flow, 结构:scores.structure, 预测:scores.forecast, 新闻:scores.news})
    .map(([label, value]) => `<div class="score-item"><span>${escapeHtml(label)}</span><strong>${fmt(value,1)}</strong></div>`).join('');
}
function renderForecasts(row) {
  const items = Object.values(row.forecasts || {}).sort((a,b)=>Number(a.horizon)-Number(b.horizon));
  $('#forecastCards').innerHTML = items.map(item => `<article class="forecast-card">
    <h4>${escapeHtml(item.horizon)} 日</h4>
    <div class="main ${color(item.expected_return)}">${pctRatio(item.expected_return)}</div>
    <dl>
      <dt>${item.calibration_status === 'calibrated' ? '上涨概率' : '历史上涨占比'}</dt><dd>${number(item.p_up) ? `${(Number(item.p_up)*100).toFixed(1)}%` : '—'}</dd>
      <dt>终点中位价</dt><dd>${fmt(item.terminal_price_q50,3)}</dd>
      <dt>路径支撑</dt><dd class="down">${fmt(item.path_low_price_q50,3)}</dd>
      <dt>路径压力</dt><dd class="up">${fmt(item.path_high_price_q50,3)}</dd>
      <dt>样本 / conf</dt><dd>${escapeHtml(item.sample_count || 0)} / ${fmt(item.confidence,0)}</dd>
      <dt>校准</dt><dd>${escapeHtml(item.calibration_status || 'not_calibrated')}</dd>
    </dl>
  </article>`).join('') || '<div class="empty">预测不可用</div>';
}
function modeMatches(method, mode) {
  if (mode === '综合') return true;
  if (mode === '均线') return /^MA\d+/.test(method) || method.includes('趋势线');
  if (mode === 'MACD') return method.includes('MACD');
  if (mode === 'KDJ') return method.includes('KDJ');
  if (mode === 'RSI') return method.includes('RSI');
  if (mode === '缠论近似') return method.includes('缠论');
  if (mode === '成交密集成本') return method.includes('成交') || method.includes('COST');
  return true;
}
function renderLevels(row) {
  const levels = (row.support_resistance?.levels || []).filter(level => (level.methods || []).some(method => modeMatches(method, state.mode)));
  const sorted = levels.sort((a,b)=>Math.abs(a.distance_pct)-Math.abs(b.distance_pct)).slice(0,12);
  $('#levelTable').innerHTML = sorted.map(level => `<div class="level-row">
    <strong class="${level.kind === 'support' ? 'down' : 'up'}">${fmt(level.price,3)}</strong>
    <span>${level.kind === 'support' ? '支撑' : '压力'}</span>
    <span>强度 ${fmt(level.strength,0)}</span>
    <span class="methods" title="${escapeHtml((level.methods || []).join(' / '))}">${escapeHtml((level.methods || []).join(' / '))}</span>
  </div>`).join('') || '<div class="empty">当前模式暂无已确认价格区域</div>';
}
function renderIndicators(row) {
  const v = row.indicator?.values || {};
  const keys = [
    ['MACD DIF','macd_dif'],['MACD DEA','macd_dea'],['MACD柱','macd_hist'],['KDJ J','kdj_j'],
    ['RSI14','rsi14'],['量比','volume_ratio'],['MFI14','mfi14'],['CMF20','cmf20'],
    ['ADX14','adx14'],['RPS20','rps20'],['RSRS','rsrs_zscore'],['ATR14','atr14'],
  ];
  $('#indicatorGrid').innerHTML = keys.map(([label,key])=>`<div class="indicator-item"><span>${escapeHtml(label)}</span><strong>${fmt(v[key], key==='rps20'||key==='rsi14'||key==='kdj_j'?1:4)}</strong></div>`).join('');
}
function renderNews(row) {
  const news = row.news || [];
  $('#newsList').innerHTML = news.map(item => `<article class="news-item"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.source)} · ${timeText(item.published_at)} · ${escapeHtml(item.impact_direction || 'neutral')}</small></article>`).join('') || '<div class="empty">最近72小时没有匹配到结构化主题新闻。</div>';
}
function renderModes(row) {
  const modes = row.chart?.overlay_modes || ['综合','均线','MACD','KDJ','RSI','缠论近似','成交密集成本'];
  $('#modeTabs').innerHTML = modes.map(mode => `<button class="${mode===state.mode?'active':''}" data-mode="${escapeHtml(mode)}">${escapeHtml(mode)}</button>`).join('');
  $('#modeTabs').querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
    state.mode = button.dataset.mode;
    renderModes(row); renderLevels(row); drawChart(row);
  }));
}
async function openDetail(code) {
  $('#detailOverlay').classList.remove('hidden');
  $('#detailTitle').textContent = `加载 ${code}…`;
  try {
    const row = await api(`/api/workbench/1430/${encodeURIComponent(code)}`);
    state.detail = row; state.mode = '综合';
    $('#detailTitle').textContent = `${row.name} · ${row.ts_code}`;
    $('#detailSub').textContent = `${row.theme_l1 || '未分类'} / ${row.theme_l2 || '—'} · 数据日 ${row.as_of_date || '—'}`;
    $('#detailAction').innerHTML = `<span class="chip ${actionClass(row.action)}">${escapeHtml(row.action)} · ${fmt(row.score,1)}</span>`;
    $('#detailWarnings').innerHTML = (row.risks || []).map(item=>`• ${escapeHtml(item)}`).join('<br>') || '研究状态正常；仍不构成自动交易指令。';
    renderScores(row); renderForecasts(row); renderModes(row); renderLevels(row); renderIndicators(row); renderNews(row); drawChart(row);
  } catch (error) {
    $('#detailWarnings').textContent = `详情加载失败：${error.message}`;
  }
}

function filteredLevels(row) {
  return (row.support_resistance?.levels || []).filter(level => (level.methods || []).some(method => modeMatches(method, state.mode))).sort((a,b)=>Math.abs(a.distance_pct)-Math.abs(b.distance_pct)).slice(0,8);
}
function drawChart(row) {
  const canvas = $('#candleCanvas');
  if (!canvas || !row?.chart) return;
  const ratio = Math.max(1, window.devicePixelRatio || 1);
  const rect = canvas.getBoundingClientRect();
  const cssWidth = Math.max(320, rect.width || 1200), cssHeight = Math.max(300, rect.height || 520);
  canvas.width = Math.round(cssWidth * ratio); canvas.height = Math.round(cssHeight * ratio);
  const ctx = canvas.getContext('2d'); ctx.setTransform(ratio,0,0,ratio,0,0); ctx.clearRect(0,0,cssWidth,cssHeight);
  const historical = row.chart.historical || [], forecast = row.chart.forecast_scenario || [];
  const data = [...historical, ...forecast]; if (!data.length) return;
  const levels = filteredLevels(row);
  let minPrice = Math.min(...data.map(item=>Number(item.low)), ...levels.map(item=>Number(item.price)));
  let maxPrice = Math.max(...data.map(item=>Number(item.high)), ...levels.map(item=>Number(item.price)));
  const pad = Math.max((maxPrice-minPrice)*0.08, maxPrice*0.005); minPrice -= pad; maxPrice += pad;
  const margin = {left:64,right:86,top:25,bottom:42};
  const plotW = cssWidth-margin.left-margin.right, plotH=cssHeight-margin.top-margin.bottom;
  const y = price => margin.top + (maxPrice-price)/(maxPrice-minPrice)*plotH;
  const step = plotW/Math.max(data.length,1); const x = i => margin.left+(i+.5)*step;
  ctx.font='11px system-ui'; ctx.strokeStyle='#1e2a3b'; ctx.fillStyle='#71849e'; ctx.lineWidth=1;
  for(let i=0;i<=6;i++){const py=margin.top+i*plotH/6;ctx.beginPath();ctx.moveTo(margin.left,py);ctx.lineTo(margin.left+plotW,py);ctx.stroke();const price=maxPrice-i*(maxPrice-minPrice)/6;ctx.fillText(price.toFixed(3),margin.left+plotW+8,py+4)}
  const boundaryX = margin.left + historical.length*step;
  if(forecast.length){ctx.fillStyle='rgba(123,64,232,.07)';ctx.fillRect(boundaryX,margin.top,plotW-(boundaryX-margin.left),plotH);ctx.save();ctx.setLineDash([6,5]);ctx.strokeStyle='#b879ff';ctx.beginPath();ctx.moveTo(boundaryX,margin.top);ctx.lineTo(boundaryX,margin.top+plotH);ctx.stroke();ctx.restore();ctx.fillStyle='#c69aff';ctx.fillText('预测情景 · 非实际结果',Math.min(boundaryX+8,cssWidth-170),margin.top+16)}
  levels.forEach((level,index)=>{const py=y(Number(level.price));ctx.save();ctx.setLineDash([5,4]);ctx.strokeStyle=level.kind==='support'?'#27e48a':'#ff5b61';ctx.globalAlpha=.75;ctx.beginPath();ctx.moveTo(margin.left,py);ctx.lineTo(margin.left+plotW,py);ctx.stroke();ctx.restore();ctx.fillStyle=level.kind==='support'?'#47ef9c':'#ff777b';ctx.fillText(`${level.kind==='support'?'支':'压'} ${Number(level.price).toFixed(3)}`,margin.left+4,py-4-index%2*11)});
  const trendLines = row.support_resistance?.trend_lines || [];
  trendLines.filter(line=>state.mode==='综合'||state.mode==='均线').forEach(line=>{const startX=x(Math.max(0,historical.length-1-(line.end_index-line.start_index)));const endX=boundaryX+Math.min(forecast.length,5)*step;ctx.strokeStyle=line.label.includes('支撑')?'#28d7e5':'#ffb020';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(startX,y(Number(line.start_price)));ctx.lineTo(endX,y(Number(line.projected_price)));ctx.stroke()});
  data.forEach((item,index)=>{const px=x(index);const open=Number(item.open),close=Number(item.close),high=Number(item.high),low=Number(item.low);const isForecast=Boolean(item.is_forecast);const rising=close>=open;const bodyColor=isForecast?'#9b6cff':rising?'#ff5b61':'#27e48a';ctx.strokeStyle=bodyColor;ctx.fillStyle=bodyColor;ctx.globalAlpha=isForecast?.76:1;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(px,y(high));ctx.lineTo(px,y(low));ctx.stroke();const top=y(Math.max(open,close)),bottom=y(Math.min(open,close));const width=Math.max(2,Math.min(9,step*.62));ctx.fillRect(px-width/2,top,width,Math.max(1,bottom-top));ctx.globalAlpha=1});
  ctx.fillStyle='#71849e';const labelEvery=Math.max(1,Math.ceil(data.length/8));data.forEach((item,index)=>{if(index%labelEvery===0||index===data.length-1){ctx.save();ctx.translate(x(index),cssHeight-15);ctx.rotate(-.35);ctx.fillText(String(item.date).slice(5),0,0);ctx.restore()}});
}

async function generateReport() {
  const button = $('#generateButton'); const original=button.textContent; button.disabled=true; button.textContent='生成中…';
  try { const result=await api('/api/workbench/1430/generate',{method:'POST'}); alert(`报告已生成：${result.filename}`); }
  catch(error){ alert(`生成失败：${error.message}`); }
  finally{button.disabled=false;button.textContent=original;}
}

$('#authForm').addEventListener('submit', async event => { event.preventDefault(); const response=await fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({identifier:$('#identifierInput').value.trim(),password:$('#passwordInput').value})}); if(!response.ok){$('#authError').textContent='登录失败，请检查凭据后重试';return;} state.sessionActive=true; await loadSummary(); });
$('#refreshButton').addEventListener('click', loadSummary);
$('#generateButton').addEventListener('click', generateReport);
$('#lockButton').addEventListener('click', async ()=>{try{await api('/api/auth/logout',{method:'POST'});}catch(_){ } state.sessionActive=false;showAuth();});
$('#detailClose').addEventListener('click', ()=>$('#detailOverlay').classList.add('hidden'));
$('#detailOverlay').addEventListener('click', event=>{if(event.target===$('#detailOverlay')) $('#detailOverlay').classList.add('hidden')});
window.addEventListener('resize', ()=>{clearTimeout(state.resizeTimer);state.resizeTimer=setTimeout(()=>{if(state.detail)drawChart(state.detail)},120)});

fetch('/api/auth/me',{credentials:'same-origin'}).then(response=>response.ok?response.json():{authenticated:false}).then(auth=>{state.sessionActive=Boolean(auth.authenticated);if(!state.sessionActive){showAuth();return;}loadSummary();}).catch(showAuth);
