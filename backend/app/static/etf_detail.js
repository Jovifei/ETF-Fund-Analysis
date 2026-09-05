'use strict';

/**
 * ETF 详情 · 研究研判台（/etf/{ts_code}）
 *
 * 全站唯一的单标的详情页：决策表 / 板块 / 持仓 / 14:30 工作台点击标的都进入这里。
 * 数据源：/api/workbench/1430/{ts_code}（与 14:30 工作台同一只读 API，同一决策契约）。
 * 图表为 Canvas 自绘（CSP script-src 'self'，不引入外部图表库）。
 */

const $ = (selector, root = document) => root.querySelector(selector);
const state = { detail: null, mode: '综合', resizeTimer: null, code: null };

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
  if (action === '买入候选') return 'buy';
  if (action === '可试探') return 'probe';
  if (action === '持有/观察') return 'hold';
  if (action === '减仓候选') return 'reduce';
  if (action === '回避') return 'avoid';
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
  if (response.status === 401) { showAuth(); throw new Error('需要重新登录'); }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { const payload = await response.json(); detail = payload.detail || detail; } catch (_) {}
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return response.json();
}
function showAuth() { $('#authOverlay').classList.remove('hidden'); $('#passwordInput').value=''; $('#identifierInput').focus(); }
function hideAuth() { $('#authOverlay').classList.add('hidden'); }

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
      <dt>上涨概率</dt><dd>${number(item.p_up) ? `${(Number(item.p_up)*100).toFixed(1)}%` : '—'}</dd>
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
    renderModes(state.detail); renderLevels(state.detail); drawChart(state.detail);
  }));
}
function filteredLevels(row) {
  return (row.support_resistance?.levels || []).filter(level => (level.methods || []).some(method => modeMatches(method, state.mode))).sort((a,b)=>Math.abs(a.distance_pct)-Math.abs(b.distance_pct));
}

// ---------- 图表视口（PR-F：缩放 / 平移 / 十字线 / 半透明支撑压力区） ----------
const chartView = { start: 0, end: 0, crosshair: null, dragging: false, dragOriginX: 0, dragStart: 0, hintShown: false };
const MIN_VISIBLE_BARS = 10;

function resetViewport(total) {
  chartView.start = 0;
  chartView.end = Math.max(total, 1);
}

function visibleSlice(data) {
  const total = data.length;
  if (chartView.end <= chartView.start || chartView.end > total || chartView.start < 0) resetViewport(total);
  return data.slice(chartView.start, chartView.end);
}

function zoneBounds(level, sr) {
  const tolerance = Number(sr?.default_zone_tolerance) || 0;
  let low = Number(level.zone_low), high = Number(level.zone_high);
  if (!Number.isFinite(low) || !Number.isFinite(high)) { low = Number(level.price) - tolerance; high = Number(level.price) + tolerance; }
  if (high - low < tolerance * 0.4) { const mid = (low + high) / 2; low = mid - tolerance * 0.2; high = mid + tolerance * 0.2; }
  return [low, high];
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
  if (!chartView.end) resetViewport(data.length);
  const sr = row.support_resistance || {};
  const levels = filteredLevels(row);
  const visible = visibleSlice(data);
  const offset = chartView.start;

  let minPrice = Math.min(...visible.map(item=>Number(item.low)), ...levels.map(item=>Number(item.price)), ...levels.map(item=>zoneBounds(item, sr)[0]));
  let maxPrice = Math.max(...visible.map(item=>Number(item.high)), ...levels.map(item=>Number(item.price)), ...levels.map(item=>zoneBounds(item, sr)[1]));
  const pad = Math.max((maxPrice-minPrice)*0.08, maxPrice*0.005); minPrice -= pad; maxPrice += pad;
  const margin = {left:64,right:86,top:25,bottom:42};
  const plotW = cssWidth-margin.left-margin.right, plotH=cssHeight-margin.top-margin.bottom;
  const y = price => margin.top + (maxPrice-price)/(maxPrice-minPrice)*plotH;
  const step = plotW/Math.max(visible.length,1);
  const x = i => margin.left+(i+0.5)*step;
  const xAbsolute = absoluteIndex => x(absoluteIndex - offset);

  ctx.font='11px system-ui'; ctx.strokeStyle='#1e2a3b'; ctx.fillStyle='#71849e'; ctx.lineWidth=1;
  for(let i=0;i<=6;i++){const py=margin.top+i*plotH/6;ctx.beginPath();ctx.moveTo(margin.left,py);ctx.lineTo(margin.left+plotW,py);ctx.stroke();const price=maxPrice-i*(maxPrice-minPrice)/6;ctx.fillText(price.toFixed(3),margin.left+plotW+8,py+4)}

  // 半透明支撑/压力区域（先画区域，再画蜡烛）
  levels.forEach(level=>{
    const [low, high] = zoneBounds(level, sr);
    const top = y(Math.max(low, high)), height = Math.max(2, Math.abs(y(low)-y(high)));
    ctx.save();
    ctx.globalAlpha = 0.16;
    ctx.fillStyle = level.kind==='support' ? '#27e48a' : '#ff5b61';
    ctx.fillRect(margin.left, top, plotW, height);
    ctx.restore();
  });

  // 预测分界
  const histVisibleEnd = Math.max(0, historical.length - offset);
  const boundaryX = margin.left + histVisibleEnd*step;
  if(forecast.length && histVisibleEnd > 0 && histVisibleEnd < visible.length){
    ctx.fillStyle='rgba(123,64,232,.07)';ctx.fillRect(boundaryX,margin.top,cssWidth-margin.right-boundaryX,plotH);
    ctx.save();ctx.setLineDash([6,5]);ctx.strokeStyle='#b879ff';ctx.beginPath();ctx.moveTo(boundaryX,margin.top);ctx.lineTo(boundaryX,margin.top+plotH);ctx.stroke();ctx.restore();
    ctx.fillStyle='#c69aff';ctx.fillText('预测情景 · 非实际结果',Math.min(boundaryX+8,cssWidth-170),margin.top+16);
  }

  // 支撑/压力中枢线（区域之上再画细线 + 标签）
  levels.slice(0, 14).forEach((level,index)=>{
    const py=y(Number(level.price));
    ctx.save();ctx.setLineDash([5,4]);ctx.strokeStyle=level.kind==='support'?'#27e48a':'#ff5b61';ctx.globalAlpha=.75;ctx.beginPath();ctx.moveTo(margin.left,py);ctx.lineTo(margin.left+plotW,py);ctx.stroke();ctx.restore();
    ctx.fillStyle=level.kind==='support'?'#47ef9c':'#ff777b';
    ctx.fillText(`${level.kind==='support'?'支':'压'} ${Number(level.price).toFixed(3)}`,margin.left+4,py-4-index%2*11);
  });

  // 趋势线（综合/均线模式）
  const trendLines = row.support_resistance?.trend_lines || [];
  trendLines.filter(line=>state.mode==='综合'||state.mode==='均线').forEach(line=>{
    const startX=xAbsolute(Math.max(0,historical.length-1-(line.end_index-line.start_index)));
    const endX=xAbsolute(Math.min(data.length-1, historical.length + Math.min(forecast.length,5)-1));
    if (endX <= margin.left || startX >= cssWidth-margin.right) return;
    ctx.strokeStyle=line.label.includes('支撑')?'#28d7e5':'#ffb020';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(startX,y(Number(line.start_price)));ctx.lineTo(endX,y(Number(line.projected_price)));ctx.stroke();ctx.lineWidth=1;
  });

  // 蜡烛（可见窗口）
  visible.forEach((item,index)=>{const px=x(index);const open=Number(item.open),close=Number(item.close),high=Number(item.high),low=Number(item.low);const isForecast=Boolean(item.is_forecast);const rising=close>=open;const bodyColor=isForecast?'#9b6cff':rising?'#ff5b61':'#27e48a';ctx.strokeStyle=bodyColor;ctx.fillStyle=bodyColor;ctx.globalAlpha=isForecast?.76:1;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(px,y(high));ctx.lineTo(px,y(low));ctx.stroke();const top=y(Math.max(open,close)),bottom=y(Math.min(open,close));const width=Math.max(2,Math.min(9,step*.62));ctx.fillRect(px-width/2,top,width,Math.max(1,bottom-top));ctx.globalAlpha=1});

  // 时间轴
  ctx.fillStyle='#71849e';const labelEvery=Math.max(1,Math.ceil(visible.length/8));visible.forEach((item,index)=>{if(index%labelEvery===0||index===visible.length-1){ctx.save();ctx.translate(x(index),cssHeight-15);ctx.rotate(-.35);ctx.fillText(String(item.date).slice(5),0,0);ctx.restore()}});

  // 十字光标 + OHLC 提示
  if (chartView.crosshair) {
    const cx = chartView.crosshair.x, cy = chartView.crosshair.y;
    if (cx >= margin.left && cx <= margin.left+plotW && cy >= margin.top && cy <= margin.top+plotH) {
      ctx.save();ctx.setLineDash([3,3]);ctx.strokeStyle='#8ba0b5';ctx.beginPath();ctx.moveTo(cx,margin.top);ctx.lineTo(cx,margin.top+plotH);ctx.moveTo(margin.left,cy);ctx.lineTo(margin.left+plotW,cy);ctx.stroke();ctx.restore();
      const hoverIndex = Math.min(visible.length-1, Math.max(0, Math.floor((cx-margin.left)/step)));
      const item = visible[hoverIndex];
      if (item) {
        const lines = [String(item.date), `O ${Number(item.open).toFixed(3)}  H ${Number(item.high).toFixed(3)}`, `L ${Number(item.low).toFixed(3)}  C ${Number(item.close).toFixed(3)}`, item.is_forecast ? '预测情景·非实际' : '实际历史'];
        const boxW = 210, boxH = 78, boxX = Math.min(cx+12, cssWidth-boxW-6), boxY = Math.min(cy+12, cssHeight-boxH-6);
        ctx.fillStyle='rgba(10,20,32,.92)';ctx.strokeStyle='#27455f';ctx.beginPath();ctx.roundRect(boxX,boxY,boxW,boxH,6);ctx.fill();ctx.stroke();
        ctx.fillStyle='#cfe3f5';lines.forEach((line,i)=>ctx.fillText(line,boxX+10,boxY+18+i*16));
      }
    }
  }

  if (!chartView.hintShown) { chartView.hintShown = true; ctx.fillStyle='#5f7a95'; ctx.fillText('滚轮缩放 · 拖拽平移 · 双击复位', margin.left+6, cssHeight-24); }
}

function bindChartInteractions() {
  const canvas = $('#candleCanvas');
  if (!canvas) return;
  canvas.addEventListener('wheel', event => {
    if (!state.detail) return;
    event.preventDefault();
    const data = [...(state.detail.chart?.historical||[]), ...(state.detail.chart?.forecast_scenario||[])];
    const total = data.length; if (!total) return;
    if (!chartView.end) resetViewport(total);
    const span = chartView.end - chartView.start;
    const factor = event.deltaY > 0 ? 1.2 : 1/1.2;
    const newSpan = Math.max(MIN_VISIBLE_BARS, Math.min(total, Math.round(span*factor)));
    const rect = canvas.getBoundingClientRect();
    const ratio = (event.clientX - rect.left - 64) / Math.max(1, rect.width - 150);
    const anchor = chartView.start + Math.max(0, Math.min(span, Math.round(span*ratio)));
    let start = Math.round(anchor - (anchor-chartView.start)*factor);
    start = Math.max(0, Math.min(start, total-newSpan));
    chartView.start = start; chartView.end = start + newSpan;
    drawChart(state.detail);
  }, {passive:false});
  canvas.addEventListener('mousedown', event => { chartView.dragging = true; chartView.dragOriginX = event.clientX; chartView.dragStart = chartView.start; });
  window.addEventListener('mouseup', ()=>{ chartView.dragging = false; });
  canvas.addEventListener('mousemove', event => {
    const rect = canvas.getBoundingClientRect();
    const cx = event.clientX-rect.left, cy = event.clientY-rect.top;
    if (chartView.dragging && state.detail) {
      const data = [...(state.detail.chart?.historical||[]), ...(state.detail.chart?.forecast_scenario||[])];
      const total = data.length;
      const span = chartView.end - chartView.start;
      const step = Math.max(1,(rect.width-150)/span);
      const shiftBars = Math.round((chartView.dragOriginX - event.clientX)/step);
      const start = Math.max(0, Math.min(total-span, chartView.dragStart + shiftBars));
      chartView.start = start; chartView.end = start + span;
    }
    chartView.crosshair = {x: cx, y: cy};
    if (state.detail) drawChart(state.detail);
  });
  canvas.addEventListener('mouseleave', ()=>{ chartView.crosshair = null; chartView.dragging = false; if (state.detail) drawChart(state.detail); });
  canvas.addEventListener('dblclick', ()=>{ if (state.detail) { resetViewport((state.detail.chart?.historical||[]).length + (state.detail.chart?.forecast_scenario||[]).length); drawChart(state.detail); } });
}

async function loadDetail() {
  const code = decodeURIComponent(location.pathname.split('/').pop() || '').trim().toUpperCase();
  state.code = code;
  if (!code) { $('#detailTitle').textContent = '缺少 ETF 代码'; return; }
  try {
    const row = await api(`/api/workbench/1430/${encodeURIComponent(code)}`);
    hideAuth();
    renderDetail(row);
  } catch (error) {
    $('#detailWarnings').textContent = `详情加载失败：${error.message}`;
  }
}

$('#authForm').addEventListener('submit', async event => {
  event.preventDefault();
  const response = await fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({identifier:$('#identifierInput').value.trim(),password:$('#passwordInput').value})});
  if (!response.ok) { $('#authError').textContent = '登录失败，请检查凭据后重试'; return; }
  hideAuth();
  await loadDetail();
});
$('#refreshButton').addEventListener('click', loadDetail);
$('#lockButton').addEventListener('click', async ()=>{try{await api('/api/auth/logout',{method:'POST'});}catch(_){ } showAuth();});
window.addEventListener('resize', ()=>{clearTimeout(state.resizeTimer);state.resizeTimer=setTimeout(()=>{if(state.detail)drawChart(state.detail)},120)});

bindChartInteractions();

fetch('/api/auth/me',{credentials:'same-origin'})
  .then(response=>response.ok?response.json():{authenticated:false})
  .then(auth=>{ if (!auth.authenticated) { showAuth(); return; } loadDetail(); })
  .catch(showAuth);
