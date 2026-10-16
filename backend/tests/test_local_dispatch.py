from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import json
import pytest

from app.workspace.local_dispatch import dispatch_once, DISPATCH_SLOTS
from app.workspace.local_job_ledger import LocalJobLedger
from app.workspace.local_schedule import LocalRunLock
from app.workspace.shadow_bundle import digest

TZ = ZoneInfo('Asia/Shanghai')
IDENTITY = {'code_sha': 'a' * 40, 'config_hash': 'b' * 64, 'scope_hash': 'c' * 64}


class Calendar:
    def decision(self, day):
        return SimpleNamespace(verified=True, is_trade_day=True)


def test_dispatch_latest_not_all_missed_slots(tmp_path):
    calls = []
    now = datetime(2026, 10, 16, 14, 56, tzinfo=TZ)
    def run(mode, **hooks):
        calls.append(mode)
        return 1
    assert dispatch_once(tmp_path, IDENTITY, calendar=Calendar(), run_job=run,
                         replay=lambda **kw: None, now=lambda: now) == 1
    summary = LocalJobLedger(tmp_path).summary()
    assert calls == ['fast']
    assert next(s for s in summary['slots'] if s['slot'] == '14:50')['status'] == 'SUPERSEDED'
    assert next(s for s in summary['slots'] if s['slot'] == '14:55')['status'] == 'FAILED'


def test_dispatch_never_steals_live_lock(tmp_path):
    lock = LocalRunLock(tmp_path / '.run.lock')
    assert lock.acquire()
    try:
        def forbidden(*a, **k):
            raise AssertionError('must not execute')
        assert dispatch_once(tmp_path, IDENTITY, calendar=Calendar(), run_job=forbidden,
                             replay=forbidden) == 2
        assert not (tmp_path / 'state' / 'schedule.sqlite3').exists()
    finally:
        lock.release()


def test_dispatch_calendar_unknown_blocks_execution(tmp_path):
    cal = SimpleNamespace(decision=lambda day: SimpleNamespace(verified=False, is_trade_day=True))
    assert dispatch_once(tmp_path, IDENTITY, calendar=cal, run_job=lambda *a, **k: 0,
                         replay=lambda **k: None) == 1
    assert not LocalJobLedger(tmp_path).summary()['attempts']


def test_no_delivered_claim_without_receipt(tmp_path):
    now = datetime(2026, 10, 16, 14, 30, tzinfo=TZ)
    assert dispatch_once(tmp_path, IDENTITY, calendar=Calendar(), run_job=lambda *a, **k: 0,
                         replay=lambda **k: None, now=lambda: now) == 1
    summary = LocalJobLedger(tmp_path).summary()
    assert summary['counts'].get('DELIVERED', 0) == 0


def test_trade_day_skip_and_old_session_not_replayed(tmp_path):
    cal = SimpleNamespace(decision=lambda day: SimpleNamespace(verified=True, is_trade_day=False))
    assert dispatch_once(tmp_path, IDENTITY, calendar=cal, run_job=lambda *a, **k: 0,
                         replay=lambda **k: None) == 0
    assert '13:55' in DISPATCH_SLOTS


def test_execution_failure_is_sanitized_and_retained(tmp_path):
    def broken(*a, **k):
        raise RuntimeError('private URL must not enter ledger')
    now = datetime(2026, 10, 16, 16, 10, tzinfo=TZ)
    assert dispatch_once(tmp_path, IDENTITY, calendar=Calendar(), run_job=broken,
                         replay=lambda **k: None, now=lambda: now) == 1
    summary = LocalJobLedger(tmp_path).summary()
    assert 'private URL' not in str(summary)
    assert summary['attempts'][0]['reason'] == 'RuntimeError'


def manifest_for(now):
    return {'contract_version': 'local-display-v2', 'code_sha': IDENTITY['code_sha'],
            'config_hash': IDENTITY['config_hash'], 'universe': ['510300.SH'], 'sequence': 99,
            'generated_at': now.isoformat(), 'expires_at': (now + timedelta(hours=2)).isoformat()}


def receipt_for(manifest):
    return {'status': 'accepted', 'sequence': manifest['sequence'], 'bundle_id': digest(manifest),
            'manifest_hash': digest(manifest), 'received_at': manifest['generated_at']}


def test_upload_failure_replays_same_package_without_recompute(tmp_path):
    clock = [datetime(2026, 10, 16, 14, 55, tzinfo=TZ)]
    manifest = manifest_for(clock[0])
    ident = {**IDENTITY, 'scope_hash': digest(manifest['universe'])}
    def compute(mode, **hooks):
        hooks['on_task']('refresh_quotes', None, 'real-task-id')
        hooks['on_task']('refresh_quotes', {'status': 'succeeded', 'coverage_complete': True}, 'real-task-id')
        hooks['on_export']({'manifest': manifest}, tmp_path / 'outbox' / 'bundle_99.json')
        return 1
    assert dispatch_once(tmp_path, ident, calendar=Calendar(), run_job=compute,
                         replay=None, now=lambda: clock[0]) == 1
    ledger = LocalJobLedger(tmp_path)
    first = ledger.summary()['attempts'][0]
    assert first['status'] == 'EXPORTED' and first['sequence'] == 99
    clock[0] += timedelta(seconds=61)
    def replay(*, attempt, on_receipt):
        assert attempt['attempt_id'] == first['attempt_id']
        assert attempt['bundle_id'] == digest(manifest)
        on_receipt(manifest, receipt_for(manifest))
    def forbidden(*a, **k):
        raise AssertionError('must not recompute')
    assert dispatch_once(tmp_path, ident, calendar=Calendar(), run_job=forbidden,
                         replay=replay, now=lambda: clock[0]) == 0
    result = ledger.summary()
    assert len(result['attempts']) == 1 and result['attempts'][0]['status'] == 'DELIVERED'
    assert [j['status'] for j in result['jobs'] if j['job_name'].startswith('upload_')] == ['failed', 'succeeded']


def test_new_slot_takes_priority_over_old_pending_upload(tmp_path):
    clock = [datetime(2026, 10, 16, 14, 50, tzinfo=TZ)]
    manifest = manifest_for(clock[0])
    ident = {**IDENTITY, 'scope_hash': digest(manifest['universe'])}
    def first(mode, **hooks):
        hooks['on_export']({'manifest': manifest}, 'bundle_99.json')
        return 1
    assert dispatch_once(tmp_path, ident, calendar=Calendar(), run_job=first,
                         replay=None, now=lambda: clock[0]) == 1
    clock[0] += timedelta(minutes=6, seconds=38)
    calls = []
    def next_run(mode, **hooks):
        calls.append(mode)
        return 1
    assert dispatch_once(tmp_path, ident, calendar=Calendar(), run_job=next_run,
                         replay=lambda **k: (_ for _ in ()).throw(AssertionError('old replay')),
                         now=lambda: clock[0]) == 1
    summary = LocalJobLedger(tmp_path).summary()
    assert calls == ['fast']
    assert next(s for s in summary['slots'] if s['slot'] == '14:50')['status'] == 'SUPERSEDED'
    assert len(summary['attempts']) == 2


def test_skipped_optional_task_keeps_original_status_without_aborting_run(tmp_path):
    now = datetime(2026, 10, 16, 13, 55, tzinfo=TZ)
    calls = []
    def run(mode, **hooks):
        hooks['on_task']('refresh_market_context', None, 'optional-task')
        hooks['on_task']('refresh_market_context', {'status': 'skipped'}, 'optional-task')
        calls.append('continued')
        return 1
    assert dispatch_once(tmp_path, IDENTITY, calendar=Calendar(), run_job=run,
                         replay=None, now=lambda: now) == 1
    job = LocalJobLedger(tmp_path).summary()['jobs'][0]
    assert calls == ['continued']
    assert job['status'] == 'unavailable' and job['required'] is False
    assert job['details']['source_task_status'] == 'skipped'


def test_pending_fast_packet_cannot_outlive_quote_freshness(tmp_path):
    from app.workspace.local_dispatch import load_pending_bundle
    from app.workspace.local_display_contract import compute_parts_hashes
    now = datetime(2026, 10, 16, 14, 30, tzinfo=TZ)
    manifest = {**manifest_for(now), 'actionable': False, 'data_origin': 'local_research'}
    parts = {'overview': {'rows': []}, 'details': {}, 'charts': {}, 'sectors': {'sectors': []}}
    manifest['parts_hashes'] = compute_parts_hashes(parts)
    ident = {**IDENTITY, 'scope_hash': digest(manifest['universe'])}
    outbox = tmp_path / 'outbox'
    outbox.mkdir()
    (outbox / 'bundle_99.json').write_text(json.dumps({'manifest': manifest, 'parts': parts}))
    attempt = {'bundle_file': 'bundle_99.json', 'bundle_id': digest(manifest), 'slot_id': '2026-10-16 14:30'}
    assert load_pending_bundle(tmp_path, attempt, ident, now=now + timedelta(minutes=2))['manifest'] == manifest
    with pytest.raises(ValueError, match='fast observation expired'):
        load_pending_bundle(tmp_path, attempt, ident, now=now + timedelta(minutes=9))
    with pytest.raises(ValueError):
        load_pending_bundle(tmp_path, {**attempt, 'bundle_file': '../elsewhere.json'}, ident, now=now)
