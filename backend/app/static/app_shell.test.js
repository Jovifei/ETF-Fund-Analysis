'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

require('./app_shell.js');

const shell = globalThis.ETFAppShell;

test('primary navigation is four stable business entries', () => {
  assert.ok(shell);
  assert.deepEqual(
    shell.primaryLinks().map(item => [item.key, item.href]),
    [
      ['decision', '/'],
      ['boards', '/boards'],
      ['portfolio', '/portfolio'],
      ['research', '/research'],
    ],
  );
  assert.deepEqual(shell.taskLink(), {key: '1430', href: '/workbench/1430', label: '⏱️ 14:30'});
});

test('legacy hashes default to research and preserve explicit workspace tabs', () => {
  assert.equal(shell.legacyTabFromHash(''), 'signals');
  assert.equal(shell.legacyTabFromHash('#unknown'), 'signals');
  assert.equal(shell.legacyTabFromHash('#signals'), 'signals');
  assert.equal(shell.legacyTabFromHash('#holdings'), 'holdings');
  assert.equal(shell.legacyTabFromHash('#news'), 'news');
  assert.equal(shell.legacyTabFromHash('#system'), 'system');
});

test('section mapping makes holdings distinct from the research center', () => {
  assert.equal(shell.sectionForLocation('/', ''), 'decision');
  assert.equal(shell.sectionForLocation('/boards', ''), 'boards');
  assert.equal(shell.sectionForLocation('/legacy', '#holdings'), 'portfolio');
  assert.equal(shell.sectionForLocation('/legacy', '#signals'), 'research');
  assert.equal(shell.sectionForLocation('/legacy', '#news'), 'research');
  assert.equal(shell.sectionForLocation('/workbench/1430', ''), '1430');
  assert.equal(shell.sectionForLocation('/etf/512480.SH', ''), 'detail');
});

test('ETF codes always resolve to the canonical global detail route', () => {
  assert.equal(shell.canonicalEtfPath('512480.SH'), '/etf/512480.SH');
  assert.equal(shell.canonicalEtfPath(' 159915.SZ '), '/etf/159915.SZ');
  assert.equal(shell.canonicalEtfPath(''), '/');
});
