'use strict';

/**
 * Shared navigation contract for every user-facing research surface.
 *
 * Product rule:
 *   4 stable business entries: Decision / Boards / Portfolio / Research
 *   1 focused task entry: 14:30
 *   1 canonical instrument detail route: /etf/{ts_code}
 *
 * The legacy mega-page remains for compatibility, but its default surface is
 * Research (#signals), not the duplicated decision dashboard. Holdings is a
 * first-class destination at #holdings. This file intentionally owns routing
 * semantics so individual pages cannot drift apart again.
 */

const PRIMARY_LINKS = Object.freeze([
  Object.freeze({key: 'decision', href: '/', label: '🎯 决策'}),
  Object.freeze({key: 'boards', href: '/boards', label: '🔥 板块'}),
  Object.freeze({key: 'portfolio', href: '/portfolio', label: '💼 我的'}),
  Object.freeze({key: 'research', href: '/research', label: '🔬 研究'}),
]);
const TASK_LINK = Object.freeze({key: '1430', href: '/workbench/1430', label: '⏱️ 14:30'});
const LEGACY_TABS = Object.freeze(new Set(['signals', 'holdings', 'news', 'system']));
const LEGACY_HASHES = Object.freeze({signals: '#signals', holdings: '#holdings', news: '#news', system: '#system'});
const LEGACY_PATHS = Object.freeze(new Set(['/legacy', '/assets/index.html']));
const INTERACTIVE_SELECTOR = 'a,button,input,select,textarea,label,[role="button"]';

function primaryLinks() {
  return PRIMARY_LINKS.map(item => ({...item}));
}

function taskLink() {
  return {...TASK_LINK};
}

function legacyTabFromHash(hash) {
  const tab = String(hash || '').replace(/^#/, '').trim().toLowerCase();
  return LEGACY_TABS.has(tab) ? tab : 'signals';
}

function canonicalEtfPath(code) {
  const normalized = String(code ?? '').trim();
  return normalized ? `/etf/${encodeURIComponent(normalized)}` : '/';
}

function sectionForLocation(pathname, hash = '') {
  const path = String(pathname || '');
  if (path === '/') return 'decision';
  if (path === '/boards') return 'boards';
  if (path === '/portfolio') return 'portfolio';
  if (path === '/research') return 'research';
  if (LEGACY_PATHS.has(path)) return legacyTabFromHash(hash) === 'holdings' ? 'portfolio' : 'research';
  if (path === '/workbench/1430' || path === '/assets/etf_1430_workbench.html') return '1430';
  if (path.startsWith('/etf/')) return 'detail';
  return null;
}

function isLegacyLocation() {
  return typeof window !== 'undefined' && LEGACY_PATHS.has(window.location.pathname);
}

function createAnchor(item, classes, activeKey) {
  const anchor = document.createElement('a');
  anchor.href = item.href;
  anchor.className = classes;
  anchor.textContent = item.label;
  anchor.dataset.shellKey = item.key;
  if (item.key === activeKey) {
    anchor.classList.add('active');
    anchor.setAttribute('aria-current', 'page');
  }
  return anchor;
}

function ensureShellStyle() {
  if (document.getElementById('appShellStyle')) return;
  const style = document.createElement('style');
  style.id = 'appShellStyle';
  style.textContent = `
    .app-shell-link[aria-current="page"], .app-shell-task[aria-current="page"] {
      font-weight: 700;
      box-shadow: inset 0 -2px 0 currentColor;
    }
    .app-shell-task {
      white-space: nowrap;
      border: 1px solid currentColor !important;
      font-weight: 700;
    }
    .app-shell-back { white-space: nowrap; }
  `;
  document.head.appendChild(style);
}

function addDetailBackButton(fragment) {
  if (!window.location.pathname.startsWith('/etf/')) return;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'ghost app-shell-back';
  button.textContent = '← 返回';
  button.addEventListener('click', () => {
    try {
      const referrer = document.referrer ? new URL(document.referrer, window.location.href) : null;
      if (referrer && referrer.origin === window.location.origin && referrer.pathname !== window.location.pathname) {
        window.history.back();
        return;
      }
    } catch (_) {}
    window.location.assign('/');
  });
  fragment.appendChild(button);
}

function renderSharedNavigation() {
  const activeKey = sectionForLocation(window.location.pathname, window.location.hash);
  const rootNav = document.querySelector('nav.top-nav');
  if (rootNav) {
    rootNav.replaceChildren(...PRIMARY_LINKS.map(item => createAnchor(item, 'nav-tab app-shell-link', activeKey)));
  }

  const actions = document.querySelector('.top-actions');
  if (!actions) return;

  // Remove page-local navigation anchors while preserving status chips and buttons.
  [...actions.querySelectorAll('a')].forEach(anchor => anchor.remove());
  const fragment = document.createDocumentFragment();
  if (!rootNav) {
    addDetailBackButton(fragment);
    PRIMARY_LINKS.forEach(item => fragment.appendChild(createAnchor(item, 'ghost link app-shell-link', activeKey)));
  }
  fragment.appendChild(createAnchor(TASK_LINK, 'ghost link app-shell-task', activeKey));
  actions.insertBefore(fragment, actions.firstChild);
}

function normalizeLegacyTabs() {
  if (!isLegacyLocation()) return;
  document.querySelector('#tabs button[data-tab="dashboard"]')?.remove();
}

function setLegacyUrl(tab) {
  const nextHash = LEGACY_HASHES[tab] || LEGACY_HASHES.signals;
  if (window.location.hash === nextHash) return;
  window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${nextHash}`);
}

function fallbackLegacySwitch(tab) {
  document.querySelectorAll('.view').forEach(view => view.classList.toggle('active', view.id === `view-${tab}`));
  document.querySelectorAll('#tabs button[data-tab]').forEach(button => {
    const selected = button.dataset.tab === tab;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-selected', String(selected));
  });
}

function activateLegacyTab() {
  if (!isLegacyLocation()) return;
  normalizeLegacyTabs();
  const tab = legacyTabFromHash(window.location.hash);
  setLegacyUrl(tab);
  if (typeof globalThis.switchTab === 'function') globalThis.switchTab(tab);
  else fallbackLegacySwitch(tab);
  renderSharedNavigation();
}

function bindLegacyRouting() {
  if (!isLegacyLocation()) return;

  document.addEventListener('click', event => {
    const button = event.target.closest?.('#tabs button[data-tab]');
    if (!button) return;
    const tab = String(button.dataset.tab || '');
    if (!LEGACY_TABS.has(tab)) return;
    setLegacyUrl(tab);
    queueMicrotask(renderSharedNavigation);
  }, true);

  window.addEventListener('hashchange', activateLegacyTab);

  // If the first tab activation happened before login completed, run it again
  // once the auth overlay closes so the selected workspace loads its own data.
  const authOverlay = document.getElementById('authOverlay');
  if (authOverlay && typeof MutationObserver !== 'undefined') {
    const observer = new MutationObserver(() => {
      if (authOverlay.classList.contains('hidden')) setTimeout(activateLegacyTab, 0);
    });
    observer.observe(authOverlay, {attributes: true, attributeFilter: ['class']});
  }
}

function routeSelectorForPage(pathname) {
  if (pathname === '/') return '.decision-data-row[data-code]';
  if (pathname === '/workbench/1430' || pathname === '/assets/etf_1430_workbench.html') return '#decisionRows tr[data-code]';
  if (LEGACY_PATHS.has(pathname)) {
    return '#gradeGroups tr[data-code], #boardGrid .board-card[data-code], #frontList .front-item[data-code]';
  }
  return null;
}

function eventCodeTarget(event) {
  const selector = routeSelectorForPage(window.location.pathname);
  if (selector) {
    const candidate = event.target.closest?.(selector);
    if (candidate && candidate.dataset.code) {
      const interactive = event.target.closest?.(INTERACTIVE_SELECTOR);
      if (!interactive || interactive === candidate) return candidate.dataset.code;
    }
  }

  // Holdings rows keep edit/delete as explicit actions; clicking the instrument
  // identity itself is the unambiguous route to the canonical ETF detail page.
  if (isLegacyLocation()) {
    const holdingCell = event.target.closest?.('#holdingTable tbody tr td:first-child');
    const editButton = holdingCell?.closest('tr')?.querySelector('.edit-holding[data-code]');
    if (editButton?.dataset.code) return editButton.dataset.code;
  }
  return null;
}

function bindCanonicalEtfNavigation() {
  document.addEventListener('click', event => {
    const code = eventCodeTarget(event);
    if (!code) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    window.location.assign(canonicalEtfPath(code));
  }, true);

  document.addEventListener('keydown', event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const selector = routeSelectorForPage(window.location.pathname);
    const candidate = selector ? event.target.closest?.(selector) : null;
    if (!candidate?.dataset.code) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    window.location.assign(canonicalEtfPath(candidate.dataset.code));
  }, true);
}

function bootAppShell() {
  ensureShellStyle();
  normalizeLegacyTabs();
  renderSharedNavigation();
  bindLegacyRouting();
  bindCanonicalEtfNavigation();
  if (isLegacyLocation()) setTimeout(activateLegacyTab, 0);
}

globalThis.ETFAppShell = Object.freeze({
  primaryLinks,
  taskLink,
  legacyTabFromHash,
  canonicalEtfPath,
  sectionForLocation,
});

if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bootAppShell, {once: true});
  else bootAppShell();
}
