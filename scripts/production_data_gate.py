"""Offline, fail-closed checks of sanitized production evidence (v2).

No database, Provider, account or model is accessed. A passing receipt is NOT
source certification, trading permission or deployment approval. See
``docs/qa/PRODUCTION_FRESHNESS_V2.md`` for the evidence contract. Legacy summary
receipts remain readable but fail on missing evidence; do not invent defaults.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from zoneinfo import ZoneInfo

VERSION = 'production-data-gate-v2'
MAX_BYTES = 2_000_000
MAX_ITEMS = 200
QUOTE_AGE_SECONDS = 480
RECEIPT_AGE_SECONDS = 900
CODE = re.compile(r'^\d{6}\.(SH|SZ|BJ)$')
HEX40 = re.compile(r'^[0-9a-f]{40}$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')
SHANGHAI = ZoneInfo('Asia/Shanghai')


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def _day(value: object) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _text(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= 128


def _matches(pattern, value):
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def evaluate_snapshot(snapshot: dict, *, now: datetime | None = None,
                      require_realtime: bool = False) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    now = now.astimezone(timezone.utc)
    root = snapshot if isinstance(snapshot, dict) else {}
    target = root.get('target_trade_date')
    target_day = _day(target)
    global_blockers = []
    if root.get('schema_version') != 'production-freshness-v2':
        global_blockers.append('evidence_schema_missing_or_unsupported')
    if target_day is None or target_day > now.astimezone(SHANGHAI).date():
        global_blockers.append('invalid_or_future_target_trade_date')
    local_now = now.astimezone(SHANGHAI)
    if target_day == local_now.date() and local_now.time().replace(tzinfo=None) < time(15, 15):
        global_blockers.append('target_session_not_settled')
    if root.get('calendar_verified') is not True:
        global_blockers.append('target_calendar_unverified')
    if not _matches(HEX40, root.get('source_tree')):
        global_blockers.append('source_tree_missing')
    captured = _timestamp(root.get('captured_at'))
    if captured is None or not 0 <= (now - captured).total_seconds() <= RECEIPT_AGE_SECONDS:
        global_blockers.append('receipt_time_missing_future_or_stale')
    expected = root.get('expected_codes')
    if not (isinstance(expected, list) and 1 <= len(expected) <= MAX_ITEMS
            and all(_matches(CODE, code) for code in expected)
            and len(set(expected)) == len(expected)):
        expected = []
        global_blockers.append('expected_universe_missing_or_invalid')
    versions = root.get('expected_versions')
    versions = versions if isinstance(versions, dict) else {}
    if not (all(_text(versions.get(key)) for key in ('indicator', 'forecast', 'feature_schema'))
            and _matches(HEX64, versions.get('config_hash'))):
        global_blockers.append('expected_version_contract_missing')
    decision = root.get('decision')
    decision = decision if isinstance(decision, dict) else {}
    decision_time = _timestamp(decision.get('generated_at'))
    if (decision.get('target_trade_date') != target or decision.get('input_dates_verified') is not True
            or decision.get('config_hash') != versions.get('config_hash')
            or decision_time is None or captured is None or decision_time > captured
            or (target_day is not None and decision_time.astimezone(SHANGHAI).date() < target_day)):
        global_blockers.append('decision_target_or_input_contract_unverified')
    raw_items = root.get('items')
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= MAX_ITEMS:
        raw_items = []
        global_blockers.append('invalid_instrument_list')
    codes = [item.get('ts_code') for item in raw_items if isinstance(item, dict)]
    if (len(codes) != len(raw_items) or not all(_matches(CODE, code) for code in codes)
            or len(set(code for code in codes if isinstance(code, str))) != len(codes)
            or set(code for code in codes if isinstance(code, str)) != set(expected)):
        global_blockers.append('instrument_identities_do_not_match_universe')
    results = []
    for raw in raw_items:
        item = raw if isinstance(raw, dict) else {}
        code = item.get('ts_code') if _matches(CODE, item.get('ts_code')) else 'unknown'
        blockers = []
        rows = item.get('daily_rows')
        if not _count(rows) or rows == 0:
            blockers.append('daily_history_count_missing_or_invalid')
        for field, reason in (('missing_volume', 'volume_missing'), ('missing_amount', 'amount_missing')):
            count = item.get(field)
            if not _count(count) or (_count(rows) and count > rows):
                blockers.append(field + '_count_unknown_or_invalid')
            elif count > 0:
                blockers.append(reason)
        for field in ('ohlc_valid', 'price_basis_verified', 'units_verified', 'indicator_input_hash_verified'):
            if item.get(field) is not True:
                blockers.append(field + '_not_proven')
        history_blockers = item.get('history_blockers')
        if not isinstance(history_blockers, list) or history_blockers:
            blockers.append('history_checks_missing_or_blocked')
        if item.get('daily_latest') != target:
            blockers.append('daily_target_not_covered')
        if item.get('indicator_latest') != target:
            blockers.append('indicator_target_not_covered')
        for field, key in (('indicator_version', 'indicator'), ('indicator_config_hash', 'config_hash'),
                           ('indicator_feature_schema', 'feature_schema')):
            if not _text(item.get(field)) or item[field] != versions.get(key):
                blockers.append(field + '_mismatch')
        if item.get('forecast_latest') != target:
            blockers.append('forecast_target_not_covered')
        forecasts = item.get('forecasts')
        valid_forecasts = isinstance(forecasts, list) and len(forecasts) == 4 and all(isinstance(f, dict) for f in forecasts)
        if (not valid_forecasts or not _count(item.get('forecast_horizons')) or item['forecast_horizons'] != 4
                or any(type(f.get('horizon')) is not int for f in forecasts)
                or sorted(f['horizon'] for f in forecasts) != [1, 3, 5, 10]):
            blockers.append('forecast_horizons_incomplete')
        elif any(f.get('as_of_date') != target or f.get('model_version') != versions.get('forecast')
                 or f.get('config_hash') != versions.get('config_hash')
                 or f.get('feature_schema') != versions.get('feature_schema')
                 or f.get('input_hash_verified') is not True or f.get('values_valid') is not True for f in forecasts):
            blockers.append('forecast_per_horizon_contract_unverified')
        quote_time = _timestamp(item.get('quote_latest'))
        if quote_time is None:
            blockers.append('quote_source_time_missing')
        elif quote_time > now:
            blockers.append('quote_source_time_in_future')
        if require_realtime:
            if item.get('quote_realtime') is not True or item.get('quote_timestamp_verified') is not True:
                blockers.append('quote_not_realtime_or_verified')
            if quote_time is not None and (quote_time.astimezone(SHANGHAI).date() != now.astimezone(SHANGHAI).date()
                                          or (now - quote_time).total_seconds() > QUOTE_AGE_SECONDS):
                blockers.append('quote_source_time_stale_or_wrong_session')
        results.append({'ts_code': code, 'blockers': sorted(set(blockers)),
                        'checks_passed': not blockers, 'qualification_granted': False, 'actionable': False})
    blocked = sum(bool(item['blockers']) for item in results)
    passed = bool(results) and blocked == 0 and not global_blockers
    return {'gate_version': VERSION, 'status': 'pass' if passed else 'fail', 'checks_passed': passed,
            'qualification_granted': False, 'actionable': False, 'deployment_approved': False,
            'global_blockers': sorted(set(global_blockers)),
            'summary': {'tracked_instruments': len(expected), 'received_instruments': len(results),
                        'blocked_instruments': blocked, 'require_realtime': require_realtime,
                        'invalid_snapshot': bool(global_blockers)}, 'items': results}


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate_json_key')
        value[key] = item
    return value


def _invalid_constant(_):
    raise ValueError('nonfinite_json')


def _private_file_path(path):
    absolute = path.absolute()
    for part in (absolute, *absolute.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('linked_evidence_path')
    return absolute


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--require-realtime', action='store_true')
    args = parser.parse_args()
    try:
        source = _private_file_path(args.input)
        target = _private_file_path(args.output)
        descriptor = os.open(source, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(descriptor, 'rb') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError('regular_file_required')
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('input_too_large')
        snapshot = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_invalid_constant)
        if not isinstance(snapshot, dict):
            raise ValueError('object_required')
        result = evaluate_snapshot(snapshot, require_realtime=args.require_realtime)
        result['evidence_sha256'] = hashlib.sha256(raw).hexdigest()
        output = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(output)
        print(json.dumps({'status': result['status'], **result['summary']}, ensure_ascii=False))
        return 0 if result['status'] == 'pass' else 3
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({'status': 'failed', 'reason': type(exc).__name__}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
