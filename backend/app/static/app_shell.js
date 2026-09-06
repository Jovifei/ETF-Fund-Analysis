'use strict';

/**
 * 统一应用壳（app-shell-v1）
 *
 * 所有一级页面在 <body> 顶部放一个 <div id="shellTopbar"></div>，
 * 并在页面脚本之前引入本文件，调用 ETFShell.mount({...})。
 *
 * 设计规则（ui-ux-pro-max）：navigation-consistency（导航跨页位置/样式不变）、
 * nav-state-active（按路径高亮）、no-emoji-icons（内联 SVG，18px stroke 1.5）、
 * font-scale（shell.css 统一字体口径）。
 *
 * 一级导航（用户心智模型）：
 *   🎯→SVG 决策 /   🔥→SVG 板块 /boards   💼→SVG 持仓 /holdings
 *   🔬→SVG 研究 /research   👤→SVG 个人中心 /account
 * 系统管理（admin）从个人中心进入，不再占据一级导航。
 */

(function () {
  const ICONS = {
    decision: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 20h18"/><path d="M5 16l4-5 4 3 5-7"/></svg>',
    boards: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/></svg>',
    holdings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 12h18"/></svg>',
    research: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6"/><path d="M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3"/><path d="M7.5 14h9"/></svg>',
    account: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5"/></svg>',
    system: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z"/></svg>',
  };

  const NAV_ITEMS = [
    { key: 'decision', href: '/', label: '决策', icon: ICONS.decision },
    { key: 'boards', href: '/boards', label: '板块', icon: ICONS.boards },
    { key: 'holdings', href: '/holdings', label: '持仓', icon: ICONS.holdings },
    { key: 'research', href: '/research', label: '研究', icon: ICONS.research },
    { key: 'account', href: '/account', label: '个人中心', icon: ICONS.account },
  ];

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
  }

  function render(config) {
    const host = document.getElementById('shellTopbar');
    if (!host) return;
    const active = config.active || '';
    const actionsHtml = config.actionsHtml || '';
    const title = escapeHtml(config.title || 'ETF 决策系统');
    const titleIdAttr = config.titleId ? ` id="${escapeHtml(config.titleId)}"` : '';
    const subtitle = escapeHtml(config.subtitle || '私有研究系统');
    const nav = NAV_ITEMS.map(item => `
      <a href="${item.href}" class="${item.key === active ? 'active' : ''}"
         ${item.key === active ? 'aria-current="page"' : ''} title="${item.label}">
        ${item.icon}<span>${item.label}</span>
      </a>`).join('');
    host.innerHTML = `
      <header class="shell-topbar" role="banner">
        <a class="shell-brand" href="/">
          <span class="shell-mark">${ICONS.decision}</span>
          <span><span class="shell-title"${titleIdAttr}>${title}</span><span class="shell-sub">${subtitle}</span></span>
        </a>
        <nav class="shell-nav" aria-label="主导航">${nav}</nav>
        <div class="shell-actions">
          ${actionsHtml}
          <span id="shellAccount" class="shell-account" aria-live="polite">…</span>
        </div>
      </header>`;
    refreshAccount();
  }

  function refreshAccount() {
    const node = document.getElementById('shellAccount');
    if (!node) return;
    fetch('/api/auth/me', { credentials: 'same-origin' })
      .then(response => (response.ok ? response.json() : { authenticated: false }))
      .then(auth => {
        if (auth.authenticated && auth.identifier) {
          node.textContent = `${auth.identifier}${auth.role ? ' · ' + auth.role : ''}`;
          node.classList.remove('danger');
        } else {
          node.textContent = '未登录 · 单机模式';
        }
      })
      .catch(() => { node.textContent = '连接失败'; });
  }

  async function logout() {
    try {
      const csrf = String(document.cookie || '').split('; ').find(v => v.startsWith('__Host-fund-csrf=') || v.startsWith('fund-csrf='));
      const headers = { 'Content-Type': 'application/json' };
      if (csrf) headers['X-CSRF-Token'] = decodeURIComponent(csrf.split('=').slice(1).join('='));
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin', headers, body: '{}' });
    } catch (_) { /* 本地/认证关闭时忽略 */ }
    window.location.href = '/';
  }

  window.ETFShell = Object.freeze({ render, logout, icons: ICONS });
})();
