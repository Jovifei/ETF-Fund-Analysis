const test = require('node:test');
const assert = require('node:assert/strict');
const {reconcile} = require('./decision_refresh');
const pending = {taskId: 'owned', status: 'queued', startedAt: 1000};
test('unrelated successful task or new snapshot cannot clear pending', () => {
  assert.equal(reconcile(pending, {run_id:'other',status:'succeeded',snapshot_id:'new'}, 2000).terminal, false);
});
test('own failed/partial/cancelled/skipped/succeeded outcome releases UI waiting', () => {
  for (const status of ['failed','partial','cancelled','skipped','succeeded']) {
    const got = reconcile(pending,{run_id:'owned',status},2000);
    assert.equal(got.terminal,true); assert.equal(got.status,status);
  }
});
test('unreachable worker terminates bounded UI wait but never fabricates task failure', () => {
  const got = reconcile(pending,null,601001);
  assert.equal(got.status,'status_unconfirmed'); assert.equal(got.terminal,true);
});
