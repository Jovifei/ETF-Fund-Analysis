'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

require('./legacy_route.js');

const router = globalThis.LegacyRouteUi;

test('old research hashes resolve to the intended first-class task route', () => {
  assert.ok(router);
  assert.equal(router.destinationKeyForLocation('/research', ''), 'signals');
  assert.equal(router.destinationKeyForLocation('/research', '#signals'), 'signals');
  assert.equal(router.destinationKeyForLocation('/research', '#holdings'), 'holdings');
  assert.equal(router.destinationKeyForLocation('/research', '#news'), 'news');
  assert.equal(router.destinationKeyForLocation('/research', '#system'), 'system');
});

test('first-class task paths win over unrelated hashes', () => {
  assert.equal(router.destinationKeyForLocation('/holdings', '#news'), 'holdings');
  assert.equal(router.destinationKeyForLocation('/research/news', '#holdings'), 'news');
  assert.equal(router.destinationKeyForLocation('/system', '#holdings'), 'system');
});

test('legacy hash destinations canonicalize to clean task URLs', () => {
  assert.equal(router.canonicalPathForDestination('signals'), '/research');
  assert.equal(router.canonicalPathForDestination('holdings'), '/holdings');
  assert.equal(router.canonicalPathForDestination('news'), '/research/news');
  assert.equal(router.canonicalPathForDestination('system'), '/system');
});

test('research ETF surfaces share the single global detail route', () => {
  assert.equal(router.canonicalEtfPath('512480.SH'), '/etf/512480.SH');
  assert.equal(router.canonicalEtfPath(' 159915.SZ '), '/etf/159915.SZ');
  assert.deepEqual(router.researchEtfSelectors(), [
    '#gradeGroups tr[data-code]',
    '#boardGrid .board-card[data-code]',
    '#frontList .front-item[data-code]',
  ]);
});
