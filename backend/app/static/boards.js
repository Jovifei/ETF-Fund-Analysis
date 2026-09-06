'use strict';

/**
 * 行业板块 · 板块市场（/boards）
 * 数据源：/api/sectors/market（板块广度快照 + 池内 ETF 代理，诚实标注覆盖语义）。
 * 成员 ETF 点击进入全站唯一详情页 /etf/{code}。
 */

const $ = (selector) => document.querySelector(selector);
const state = { kind: '', data: null };

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}
function number(value) { return value !== null && value !== undefined && Number.isFinite(Number(value)); }
function fmt(value, digits = 2, fallback = '—') { return number(value) ? Number(value).toFixed(digits) : fallback; }
function pctPoint(value, digits = 2) { return number(value) ? `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(digits)}%` : '—'; }
function colorClass(value) { return !number(value) ? 'neutral' : Number(value) >= 0 ? 'up' : 'down'; }
function actionClass(action) {
  if (action === '可加仓') return 'buy';
  if (action === '可入场') return 'buy';
  if (action === '可试探') return 'probe';
  if (action === '观望') return 'hold';
  if (action === '减仓') return 'reduce';
  return 'data';
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

function boardRow(board, index) {
  const breadth = board.breadth;
  const primary = (board.members && board.members[0]) || null;
  const membersHtml = (board.members || []).slice(0, 6).map(member =>
    `<a class="chip ${member.grade === '减仓' ? 'reduce' : member.grade === '可入场' || member.grade === '可加仓' ? 'buy' : 'hold'}" href="/etf/${encodeURIComponent(member.ts_code)}" title="${escapeHtml(member.name)} ${pctPoint(member.pct_change)}">${escapeHtml(member.name)} ${pctPoint(member.pct_change)}</a>`
  ).join('') || '<span class="muted">无 ETF 代理</span>';
  const today = breadth ? pctPoint(board.sector_pct_change) : '—';
  const up = breadth ? breadth.up : '—';
  const down = breadth ? breadth.down : '—';
  const downRatio = breadth && breadth.down_ratio != null ? `${breadth.down_ratio}%` : '—';
  const coverage = breadth
    ? ''
    : '<div class="instrument-code">广度不可用</div>';
  return `<tr class="clickable">
    <td>${index + 1}</td>
    <td><div class="instrument-name">${escapeHtml(board.name)}</div><div class="instrument-code">${escapeHtml(board.coverage === 'etf_proxy' ? 'ETF 代理' : '未验证 / 不可用')}</div></td>
    <td>${escapeHtml(board.kind === 'industry' ? '行业' : '概念')}</td>
    <td class="${colorClass(board.sector_pct_change)}">${today}${coverage}</td>
    <td class="up">${escapeHtml(String(up))}</td>
    <td class="down">${escapeHtml(String(down))}</td>
    <td>${escapeHtml(downRatio)}</td>
    <td>${primary ? `${escapeHtml(primary.name)}<div class="instrument-code">${escapeHtml(primary.ts_code)}</div>` : '—'}</td>
    <td class="${colorClass(primary ? primary.pct_change : null)}">${primary ? pctPoint(primary.pct_change) : '—'}</td>
    <td>${primary ? `<span class="chip ${actionClass(primary.grade)}">${escapeHtml(primary.grade)}</span>` : '—'}</td>
    <td><div style="display:flex;gap:4px;flex-wrap:wrap;max-width:420px">${membersHtml}</div></td>
  </tr>`;
}

function render(data) {
  state.data = data;
  const boards = data.boards || [];
  $('#metaBar').innerHTML = `板块快照日 <strong>${escapeHtml(data.trade_date || '—')}</strong><br>板块 ${boards.length} · 有广度 ${data.counts?.with_breadth ?? 0} · 有 ETF 代理 ${data.counts?.with_etf ?? 0}<br>自动订单永久关闭 · 研究模式`;
  $('#boardRows').innerHTML = boards.length
    ? boards.map((board, index) => boardRow(board, index)).join('')
    : '<tr><td colspan="11" class="empty">暂无板块数据，请等待板块快照同步任务完成。</td></tr>';
}

if (window.ETFShell) ETFShell.render({
  active: 'boards',
  title: '行业板块 · 板块市场',
  subtitle: '板块广度 + ETF 代理 · 研究模式',
  actionsHtml: `<button id="refreshButton">刷新</button><button id="lockButton">退出登录</button>`,
});

async function loadBoards() {
  $('#boardRows').innerHTML = '<tr><td colspan="11" class="empty">正在加载板块市场…</td></tr>';
  try {
    const query = state.kind ? `?kind=${state.kind}` : '';
    const data = await api(`/api/sectors/market${query}`);
    hideAuth();
    render(data);
  } catch (error) {
    $('#boardRows').innerHTML = `<tr><td colspan="11" class="empty">加载失败：${escapeHtml(error.message)}</td></tr>`;
  }
}

$('#authForm').addEventListener('submit', async event => {
  event.preventDefault();
  const response = await fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({identifier:$('#identifierInput').value.trim(),password:$('#passwordInput').value})});
  if (!response.ok) { $('#authError').textContent = '登录失败，请检查凭据后重试'; return; }
  hideAuth();
  await loadBoards();
});
$('#refreshButton').addEventListener('click', loadBoards);
$('#lockButton').addEventListener('click', async ()=>{try{await api('/api/auth/logout',{method:'POST'});}catch(_){ } showAuth();});
document.querySelectorAll('#kindTabs button').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('#kindTabs button').forEach(item => item.classList.toggle('active', item === button));
  state.kind = button.dataset.kind;
  loadBoards();
}));

fetch('/api/auth/me',{credentials:'same-origin'})
  .then(response=>response.ok?response.json():{authenticated:false})
  .then(auth=>{ if (!auth.authenticated) { showAuth(); return; } loadBoards(); })
  .catch(showAuth);
