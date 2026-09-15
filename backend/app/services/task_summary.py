"""Bounded safe diagnostics shared by workers and administrator health views."""
from __future__ import annotations

import math
import re

SCALARS = frozenset({
    'inserted', 'updated', 'unchanged', 'instruments', 'count', 'status', 'received',
    'requested', 'completed', 'coverage_complete', 'target_trade_date', 'reason',
    'missing', 'degraded', 'realtime', 'source_timestamp_verified', 'created',
    'skipped', 'qualified', 'unavailable', 'selected',
})
_CODE = re.compile(r'^[0-9]{6}\.(SH|SZ|BJ)$')
_CONTEXT = re.compile(r'^[a-z][a-z0-9-]{0,95}$')
_REASON = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,95}$')
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def bounded_step_summary(outcome: dict) -> dict:
    summary = {}
    for key, value in outcome.items():
        if key not in SCALARS:
            continue
        if isinstance(value, (bool, int)) or isinstance(value, float) and math.isfinite(value):
            summary[key] = value
        elif isinstance(value, str):
            if key == 'target_trade_date' and _DATE.fullmatch(value):
                summary[key] = value
            elif _REASON.fullmatch(value):
                summary[key] = value
    failures = outcome.get('failures')
    if not isinstance(failures, (dict, list)):
        return summary
    summary['failures_total'] = len(failures)
    summary['failures'] = safe = []
    # Iterate without copying an unbounded producer list. Identity plus reason
    # codes are the complete public contract; raw exception text is never kept.
    entries = ({'ts_code': key, 'reason': value} for key, value in failures.items()) if isinstance(failures, dict) else iter(failures)
    for index, item in enumerate(entries):
        if index >= 256 or len(safe) >= 32:
            break
        if not isinstance(item, dict):
            continue
        code, context = item.get('ts_code'), item.get('context_id')
        identity = ({'ts_code': code} if isinstance(code, str) and _CODE.fullmatch(code)
                    else {'context_id': context} if isinstance(context, str) and _CONTEXT.fullmatch(context) else None)
        if identity is None:
            continue
        reason = item.get('reason')
        safe.append({**identity, 'reason': reason if isinstance(reason, str) and _REASON.fullmatch(reason) else 'ProviderError'})
    summary['failures_omitted'] = len(failures) - len(safe)
    return summary
