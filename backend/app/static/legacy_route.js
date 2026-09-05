'use strict';

const LEGACY_DESTINATIONS = Object.freeze({
  signals: {tab: 'signals', title: 'ETF 研究中心'},
  news: {tab: 'news', title: 'ETF 研究中心 · 新闻证据'},
  holdings: {tab: 'holdings', title: '我的持仓'},
  system: {tab: 'system', title: '系统管理'},
});
const CANONICAL_PATHS = Object.freeze({
  signals: '/research',
  news: '/research/news',
  holdings: '/holdings',
  system: '/system',
});
const RESEARCH_ETF_SELECTOR = [
  '#gradeGroups tr[data-code]',
  '#boardGrid .board-card[data-code]',
  '#frontList .front-item[data-code]',
].join(', ');

function normalizedPath(pathname) {
  return String(pathname || '/research').replace(/\/+$/, '') || '/';
}

function hashDestinationKey(hash) {
  const key = String(hash || '').replace(/^#/, '').trim().toLowerCase();
  return Object.hasOwn(LEGACY_DESTINATIONS, key) ? key : null;
}

function destinationKeyForLocation(pathname, hash = '') {
  const path = normalizedPath(pathname);

  // HTTP redirects never send fragments to the server. Browsers preserve an
  // old `/legacy#holdings` fragment when following the 307 to `/research`, so
  // on that compatibility landing page the fragment must win once, then the
  // URL is canonicalized to the corresponding first-class task path.
  if (path === '/research') {
    const legacyKey = hashDestinationKey(hash);
    if (legacyKey) return legacyKey;
    return 'signals';
  }
  if (path === '/holdings') return 'holdings';
  if (path === '/system') return 'system';
  if (path === '/research/news') return 'news';
  return hashDestinationKey(hash) || 'signals';
}

function canonicalPathForDestination(key) {
  return CANONICAL_PATHS[key] || CANONICAL_PATHS.signals;
}

function requestedLegacyDestination() {
  return LEGACY_DESTINATIONS[destinationKeyForLocation(window.location.pathname, window.location.hash)];
}

function canonicalEtfPath(code) {
  const normalized = String(code ?? '').trim();
  return normalized ? `/etf/${encodeURIComponent(normalized)}` : '/';
}

function researchEtfSelectors() {
  return RESEARCH_ETF_SELECTOR.split(', ');
}

function applyLegacyDestination() {
  const key = destinationKeyForLocation(window.location.pathname, window.location.hash);
  const destination = LEGACY_DESTINATIONS[key];
  const button = document.querySelector(`#tabs button[data-tab="${destination.tab}"]`);
  if (button) button.click();
  const shellTitle = document.querySelector('#legacyShellTitle');
  if (shellTitle) shellTitle.textContent = destination.title;
  document.title = destination.title;
  const tablist = document.querySelector('#tabs');
  if (tablist) tablist.hidden = !['signals', 'news'].includes(destination.tab);

  const canonicalPath = canonicalPathForDestination(key);
  if (window.location.pathname !== canonicalPath || window.location.hash) {
    window.history.replaceState(null, '', `${canonicalPath}${window.location.search || ''}`);
  }
}

function researchEtfTarget(target) {
  return target?.closest?.(RESEARCH_ETF_SELECTOR) || null;
}

function routeResearchEtf(event) {
  const target = researchEtfTarget(event.target);
  const code = String(target?.dataset?.code || '').trim();
  if (!code) return false;
  event.preventDefault();
  event.stopImmediatePropagation();
  window.location.assign(canonicalEtfPath(code));
  return true;
}

function routeResearchEtfKey(event) {
  if (event.key !== 'Enter' && event.key !== ' ') return false;
  return routeResearchEtf(event);
}

globalThis.LegacyRouteUi = Object.freeze({
  canonicalEtfPath,
  canonicalPathForDestination,
  destinationKeyForLocation,
  researchEtfSelectors,
});

if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  window.addEventListener('hashchange', applyLegacyDestination);
  window.addEventListener('popstate', applyLegacyDestination);
  document.addEventListener('click', routeResearchEtf, true);
  document.addEventListener('keydown', routeResearchEtfKey, true);
  document.addEventListener('DOMContentLoaded', () => window.setTimeout(applyLegacyDestination, 0));
}
