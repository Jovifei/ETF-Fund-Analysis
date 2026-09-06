'use strict';

/**
 * 个人中心（/account）：账户信息 + 我的自选 + 快捷入口。
 * 管理员规则说明内置（首账户=管理员；后续由管理员创建并可指定角色）。
 */

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (v) => String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');

if (window.ETFShell) ETFShell.render({
  active: 'account',
  title: '个人中心',
  subtitle: '账户 · 自选 · 设置',
  actionsHtml: '<button id="logoutButton">退出登录</button>',
});

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (String(options.method || 'GET').toUpperCase() !== 'GET') {
    const csrf = String(document.cookie || '').split('; ').find(v => v.startsWith('__Host-fund-csrf=') || v.startsWith('fund-csrf='));
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf.split('=').slice(1).join('=')));
  }
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, { ...options, headers, credentials: 'same-origin' });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { const payload = await response.json(); detail = payload.detail || detail; } catch (_) {}
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return response.json();
}

function renderAccount(auth) {
  const authenticated = Boolean(auth.authenticated);
  $('#accountMeta').textContent = authenticated
    ? (auth.identifier ? `已登录：${auth.identifier}` : '已登录') + (auth.role ? ` · ${auth.role}` : '')
    : '未登录（单机模式）';
  const links = [
    ['💼 我的持仓', '/holdings', '份额 / 成本 / 盈亏 / 预测'],
    ['🔬 研究中心', '/research', '信号研究 / 新闻证据'],
    ['⚙ 系统设置', '/system', auth.role === 'admin' ? '任务 / 数据源 / 用户管理（管理员）' : '需要管理员角色'],
    ['📈 决策总览', '/', '今日五档与 14:30 尾盘模式'],
  ];
  $('#quickLinks').innerHTML = links.map(([label, href, note]) => `
    <a class="detail-item" href="${href}" style="display:block;padding:10px 12px;border:1px solid var(--line,#1e3247);border-radius:10px;text-decoration:none;color:inherit">
      <strong>${escapeHtml(label)}</strong><div class="muted" style="font-size:12px">${escapeHtml(note)}</div>
    </a>`).join('');
  $('#accountInfo').innerHTML = `
    <div class="indicator-item"><span>登录状态</span><strong>${authenticated ? '已登录' : '未登录（单机模式）'}</strong></div>
    <div class="indicator-item"><span>用户名</span><strong>${escapeHtml(auth.identifier || '—')}</strong></div>
    <div class="indicator-item"><span>角色</span><strong>${escapeHtml(auth.role || '—')}</strong></div>
    <div class="indicator-item"><span>注册</span><strong>默认关闭（需服务器邀请码）</strong></div>`;
  $('#logoutButton').style.display = authenticated ? '' : 'none';
}

async function loadWatchlist() {
  const node = $('#watchlistList');
  try {
    const rows = await api('/api/watchlist');
    node.innerHTML = rows.length ? rows.map(row => `
      <div style="display:flex;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid rgba(30,50,71,.6)">
        <a href="/etf/${encodeURIComponent(row.ts_code)}" style="color:inherit;text-decoration:none">
          <strong>${escapeHtml(row.name || row.ts_code)}</strong> <span class="muted">${escapeHtml(row.ts_code)}</span>
        </a>
        <span style="flex:1"></span>
        <button data-id="${row.id}" class="watchlist-remove">移除</button>
      </div>`).join('') : '<div class="muted">尚未添加自选。</div>';
    node.querySelectorAll('.watchlist-remove').forEach(button => button.addEventListener('click', async () => {
      try { await api(`/api/watchlist/entries/${button.dataset.id}`, { method: 'DELETE' }); await loadWatchlist(); }
      catch (error) { alert(`移除失败：${error.message}`); }
    }));
  } catch (error) {
    node.innerHTML = `<div class="muted">自选读取失败：${escapeHtml(error.message)}</div>`;
  }
}

async function addWatchlist() {
  const input = $('#watchlistCodeInput');
  const code = (input.value || '').trim();
  if (!code) return;
  try {
    await api('/api/watchlist/entries', { method: 'POST', body: JSON.stringify({ code }) });
    input.value = '';
    await loadWatchlist();
  } catch (error) {
    alert(`添加失败：${error.message}`);
  }
}

$('#logoutButton').addEventListener('click', async () => {
  try { await api('/api/auth/logout', { method: 'POST', body: '{}' }); } catch (_) {}
  window.location.href = '/';
});
$('#watchlistAddButton').addEventListener('click', addWatchlist);
$('#watchlistCodeInput').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); addWatchlist(); } });

fetch('/api/auth/me', { credentials: 'same-origin' })
  .then(response => response.json())
  .then(auth => { renderAccount(auth); return loadWatchlist(); })
  .catch(error => { $('#accountMeta').textContent = `加载失败：${error.message}`; });
