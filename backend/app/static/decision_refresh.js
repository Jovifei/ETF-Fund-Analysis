/* Task identity and terminal state, never a guess based on another snapshot. */
(function(root) {
  const terminal = new Set(['succeeded', 'partial', 'failed', 'cancelled', 'skipped']);
  function reconcile(pending, task, now = Date.now()) {
    if (!pending) return null;
    const same = task && String(task.run_id || task.task_id) === String(pending.taskId);
    const status = same ? task.status : null;
    if (terminal.has(status)) return {...pending, status, terminal: true};
    if (now - Number(pending.startedAt || now) >= 10 * 60 * 1000)
      return {...pending, status: 'status_unconfirmed', terminal: true};
    return {...pending, status: status === 'running' ? 'running' : pending.status, terminal: false};
  }
  const exports = {reconcile};
  if (typeof module !== 'undefined' && module.exports) module.exports = exports;
  if (root) root.ETFDecisionRefresh = exports;
})(typeof window === 'undefined' ? globalThis : window);
