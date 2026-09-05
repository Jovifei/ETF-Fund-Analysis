'use strict';

const LEGACY_DESTINATIONS = Object.freeze({
  signals: {tab: 'signals', title: 'ETF 研究中心'},
  news: {tab: 'news', title: 'ETF 研究中心 · 新闻证据'},
  holdings: {tab: 'holdings', title: '我的持仓'},
  system: {tab: 'system', title: '系统管理'},
});

function requestedLegacyDestination() {
  const path = String(window.location.pathname || '/research').replace(/\/+$/, '') || '/';
  if (path === '/holdings') return LEGACY_DESTINATIONS.holdings;
  if (path === '/system') return LEGACY_DESTINATIONS.system;
  if (path === '/research/news') return LEGACY_DESTINATIONS.news;
  if (path === '/research') return LEGACY_DESTINATIONS.signals;

  // Old #holdings/#news/#system bookmarks remain readable during the
  // compatibility window, but new navigation never generates them.
  const key = String(window.location.hash || '').replace(/^#/, '').trim().toLowerCase();
  return LEGACY_DESTINATIONS[key] || LEGACY_DESTINATIONS.signals;
}

function applyLegacyDestination() {
  const destination = requestedLegacyDestination();
  const button = document.querySelector(`#tabs button[data-tab="${destination.tab}"]`);
  if (button) button.click();
  const shellTitle = document.querySelector('#legacyShellTitle');
  if (shellTitle) shellTitle.textContent = destination.title;
  document.title = destination.title;
  const tablist = document.querySelector('#tabs');
  if (tablist) tablist.hidden = !['signals', 'news'].includes(destination.tab);
}

window.addEventListener('hashchange', applyLegacyDestination);
window.addEventListener('popstate', applyLegacyDestination);
document.addEventListener('DOMContentLoaded', () => window.setTimeout(applyLegacyDestination, 0));
