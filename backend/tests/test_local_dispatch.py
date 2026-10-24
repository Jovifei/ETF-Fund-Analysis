from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import json
import pytest

from app.workspace.local_dispatch import dispatch_once, DISPATCH_SLOTS, FULL_SLOTS
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


def test_evening_settlement_retry_slots_are_full():
    # Provider daily bars publish progressively after close (15:15 -> 0/34,
    # 16:10 -> 3-6/34 observed 2026-10-22/23); graded evening retries must
    # exist and run in full mode so the settlement lands the same evening.
    assert {'16:40', '17:40'} <= set(DISPATCH_SLOTS)
    assert {'16:40', '17:40'} <= FULL_SLOTS


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


def fast_parts(at, *, source_time=None):
    """Synthetic data using the real overview/detail quote consumer shape."""
    quote = {'price': 1.1, 'source_time': (source_time or at).isoformat(),
             'fetched_at': at.replace(tzinfo=None).isoformat(), 'source': 'sina:hq_sinajs:v1',
             'is_realtime': True, 'timestamp_verified': True, 'is_mock': False, 'actionable': False}
    row = {'ts_code': '510300.SH', 'grade': '观望', 'research_only': True, 'actionable': False,
           'quote': {key: quote[key] for key in ('source', 'source_time', 'timestamp_verified', 'is_realtime', 'is_mock')}}
    return {'overview': {'rows': [row]},
            'details': {'510300.SH': {'instrument': {'ts_code': '510300.SH'}, 'decision': row,
                        'quote': quote, 'read_as_of': at.isoformat(), 'indicator_values': {},
                        'forecasts': {}, 'support_resistance': None, 'holding': None,
                        'research_only': True, 'actionable': False}},
            'charts': {}, 'sectors': {'sectors': []}}


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


def test_task_run_identity_change_is_not_recorded_as_success(tmp_path):
    now = datetime(2026, 10, 16, 14, 55, tzinfo=TZ)
    def run(mode, **hooks):
        hooks['on_task']('refresh_decision_board', None, 'requested-run')
        hooks['on_task']('refresh_decision_board', {'status': 'succeeded', 'run_id': 'different-queued-run',
                                                  'coverage_complete': True}, 'requested-run')
        return 0
    assert dispatch_once(tmp_path, IDENTITY, calendar=Calendar(), run_job=run,
                         replay=None, now=lambda: now) == 1
    job = LocalJobLedger(tmp_path).summary()['jobs'][0]
    assert job['status'] == 'failed'
    assert job['details']['error_type'] == 'TaskRunIdentityMismatch'


def test_pending_fast_packet_cannot_outlive_quote_freshness(tmp_path):
    from app.workspace.local_dispatch import load_pending_bundle
    from app.workspace.local_display_contract import compute_parts_hashes
    now = datetime(2026, 10, 16, 14, 30, tzinfo=TZ)
    manifest = {**manifest_for(now), 'actionable': False, 'data_origin': 'local_research'}
    parts = fast_parts(now)
    manifest['parts_hashes'] = compute_parts_hashes(parts)
    execution = {'execution_hash': 'd'*64, 'config_file_hash': 'e'*64}
    manifest['execution_lineage'] = {'contract_version': 'local-execution-lineage-v1', 'mode': 'fast',
                                   **execution, 'base_input_hash': 'f'*64, 'quote_batch_hash': 'a'*64}
    ident = {**IDENTITY, 'scope_hash': digest(manifest['universe']), **execution}
    outbox = tmp_path / 'outbox'
    outbox.mkdir()
    (outbox / 'bundle_99.json').write_text(json.dumps({'manifest': manifest, 'parts': parts}))
    attempt = {'bundle_file': 'bundle_99.json', 'bundle_id': digest(manifest), 'slot_id': '2026-10-16 14:30'}
    assert load_pending_bundle(tmp_path, attempt, ident, now=now + timedelta(minutes=2))['manifest'] == manifest
    with pytest.raises(ValueError, match='fast observation expired'):
        load_pending_bundle(tmp_path, attempt, ident, now=now + timedelta(minutes=9))
    with pytest.raises(ValueError):
        load_pending_bundle(tmp_path, {**attempt, 'bundle_file': '../elsewhere.json'}, ident, now=now)


def test_replay_uses_source_quote_age_instead_of_new_board_timestamp(tmp_path):
    from app.workspace.local_dispatch import load_pending_bundle
    from app.workspace.local_display_contract import compute_parts_hashes, verify_bundle_integrity
    generated = datetime(2026, 10, 16, 14, 30, tzinfo=TZ)
    parts = fast_parts(generated, source_time=generated-timedelta(minutes=7))
    execution = {'execution_hash': 'd'*64, 'config_file_hash': 'e'*64}
    manifest = {**manifest_for(generated), 'actionable': False, 'data_origin': 'local_research',
                'parts_hashes': compute_parts_hashes(parts), 'execution_lineage': {
                    'contract_version': 'local-execution-lineage-v1', 'mode': 'fast', **execution,
                    'base_input_hash': 'f'*64, 'quote_batch_hash': 'a'*64}}
    bundle = {'manifest': manifest, 'parts': parts}
    now = generated+timedelta(minutes=2)
    assert verify_bundle_integrity(bundle, now=now)
    outbox = tmp_path/'outbox'; outbox.mkdir()
    (outbox/'bundle_99.json').write_text(json.dumps(bundle))
    attempt = {'bundle_file': 'bundle_99.json', 'bundle_id': digest(manifest), 'slot_id': '2026-10-16 14:30'}
    identity = {**IDENTITY, **execution, 'scope_hash': digest(manifest['universe'])}
    assert load_pending_bundle(tmp_path, attempt, identity, now=generated+timedelta(minutes=1))
    with pytest.raises(ValueError, match='fast observation'):
        load_pending_bundle(tmp_path, attempt, identity, now=now)


@pytest.mark.parametrize('case', ['future_source', 'future_fetch', 'stale_fetch', 'previous_session',
    'missing_source_time', 'missing_fetch', 'nonrealtime', 'unverified', 'mock', 'mock_source',
    'zero_price', 'bool_price', 'overview_time', 'overview_mock_type', 'missing_scope', 'duplicate_scope'])
def test_fast_replay_revalidates_every_real_quote_contract_field(tmp_path, case):
    from app.workspace.local_dispatch import load_pending_bundle
    from app.workspace.local_display_contract import compute_parts_hashes
    at = datetime(2026, 10, 16, 14, 30, tzinfo=TZ)
    parts = fast_parts(at)
    quote = parts['details']['510300.SH']['quote']
    summary = parts['overview']['rows'][0]['quote']
    if case == 'future_source': quote['source_time'] = (at+timedelta(minutes=1)).isoformat()
    if case == 'future_fetch': quote['fetched_at'] = (at+timedelta(minutes=1)).isoformat()
    if case == 'stale_fetch': quote['fetched_at'] = (at-timedelta(minutes=9)).isoformat()
    if case == 'previous_session': quote['source_time'] = (at-timedelta(days=1)).isoformat()
    if case == 'missing_source_time': quote.pop('source_time')
    if case == 'missing_fetch': quote.pop('fetched_at')
    if case == 'nonrealtime': quote['is_realtime'] = False
    if case == 'unverified': quote['timestamp_verified'] = False
    if case == 'mock': quote['is_mock'] = True
    if case == 'mock_source': quote['source'] = 'mock-provider'
    if case == 'zero_price': quote['price'] = 0
    if case == 'bool_price': quote['price'] = True
    if case == 'overview_time': summary['source_time'] = (at-timedelta(seconds=1)).isoformat()
    if case == 'overview_mock_type': summary['is_mock'] = 0
    if case == 'missing_scope': parts['details'].clear()
    if case == 'duplicate_scope': parts['overview']['rows'].append(dict(parts['overview']['rows'][0]))
    execution = {'execution_hash': 'd'*64, 'config_file_hash': 'e'*64}
    manifest = {**manifest_for(at), 'actionable': False, 'data_origin': 'local_research',
                'parts_hashes': compute_parts_hashes(parts), 'execution_lineage': {
                    'contract_version': 'local-execution-lineage-v1', 'mode': 'fast', **execution,
                    'base_input_hash': 'f'*64, 'quote_batch_hash': 'a'*64}}
    outbox = tmp_path/'outbox'; outbox.mkdir()
    (outbox/'bundle_99.json').write_text(json.dumps({'manifest': manifest, 'parts': parts}))
    attempt = {'bundle_file': 'bundle_99.json', 'bundle_id': digest(manifest), 'slot_id': '2026-10-16 14:30'}
    with pytest.raises(ValueError):
        load_pending_bundle(tmp_path, attempt, {**IDENTITY, **execution,
                            'scope_hash': digest(manifest['universe'])}, now=at)


def test_full_closed_research_replay_does_not_gain_or_require_fast_flags(tmp_path):
    from app.workspace.local_dispatch import load_pending_bundle
    from app.workspace.local_display_contract import compute_parts_hashes
    at = datetime(2026, 10, 16, 16, 10, tzinfo=TZ)
    parts = fast_parts(at, source_time=at.replace(hour=15, minute=0))
    parts['details']['510300.SH']['quote'].update(is_realtime=False, timestamp_verified=False)
    parts['overview']['rows'][0]['quote'].update(is_realtime=False, timestamp_verified=False)
    execution = {'execution_hash': 'd'*64, 'config_file_hash': 'e'*64}
    manifest = {**manifest_for(at), 'actionable': False, 'data_origin': 'local_research',
                'source_qualification': 'UNKNOWN', 'parts_hashes': compute_parts_hashes(parts),
                'execution_lineage': {'contract_version': 'local-execution-lineage-v1', 'mode': 'full', **execution,
                                     'base_input_hash': 'f'*64, 'quote_batch_hash': 'a'*64}}
    outbox = tmp_path/'outbox'; outbox.mkdir()
    (outbox/'bundle_99.json').write_text(json.dumps({'manifest': manifest, 'parts': parts}))
    attempt = {'bundle_file': 'bundle_99.json', 'bundle_id': digest(manifest), 'slot_id': '2026-10-16 16:10'}
    restored = load_pending_bundle(tmp_path, attempt, {**IDENTITY, **execution,
                                  'scope_hash': digest(manifest['universe'])}, now=at+timedelta(minutes=2))
    assert restored['parts']['details']['510300.SH']['quote']['is_realtime'] is False
    assert restored['manifest']['source_qualification'] == 'UNKNOWN'


@pytest.mark.parametrize('write_completed', [True, False])
@pytest.mark.parametrize('exception_type', [SystemExit, RuntimeError])
def test_crash_between_packet_write_and_export_confirmation_recovers_or_quarantines(tmp_path, write_completed, exception_type):
    from app.workspace.local_dispatch import load_pending_bundle
    from app.workspace.local_display_contract import compute_parts_hashes
    clock = [datetime(2026, 10, 16, 14, 55, tzinfo=TZ)]
    manifest = {**manifest_for(clock[0]), 'actionable': False, 'data_origin': 'local_research'}
    parts = fast_parts(clock[0])
    execution = {'execution_hash': 'd'*64, 'config_file_hash': 'e'*64}
    manifest.update(parts_hashes=compute_parts_hashes(parts), execution_lineage={
        'contract_version': 'local-execution-lineage-v1', 'mode': 'fast', **execution,
        'base_input_hash': 'f'*64, 'quote_batch_hash': 'a'*64})
    ident = {**IDENTITY, 'scope_hash': digest(manifest['universe'])}
    bundle = {'manifest': manifest, 'parts': parts}
    def crash(mode, **hooks):
        path = tmp_path / 'outbox' / 'bundle_99.json'
        hooks['on_export_intent'](bundle, path)
        if write_completed:
            path.parent.mkdir()
            path.write_text(json.dumps(bundle))
        raise exception_type('process failed before export confirmation')
    if exception_type is SystemExit:
        with pytest.raises(SystemExit):
            dispatch_once(tmp_path, ident, calendar=Calendar(), run_job=crash, replay=None, now=lambda: clock[0])
    else:
        assert dispatch_once(tmp_path, ident, calendar=Calendar(), run_job=crash, replay=None, now=lambda: clock[0]) == 1
    assert LocalJobLedger(tmp_path).summary()['attempts'][0]['status'] == 'EXPORTING'
    clock[0] += timedelta(seconds=61)
    def recover(*, attempt):
        return load_pending_bundle(tmp_path, attempt, {**ident, **execution}, now=clock[0])
    deliveries = []
    def replay(*, attempt, on_receipt):
        deliveries.append(attempt['sequence'])
        on_receipt(manifest, receipt_for(manifest))
    def forbidden(*a, **k):
        raise AssertionError('an immutable pending package must not be recomputed')
    result = dispatch_once(tmp_path, ident, calendar=Calendar(), run_job=forbidden, replay=replay,
                           recover_export=recover, now=lambda: clock[0])
    state = LocalJobLedger(tmp_path).summary()
    assert len(state['attempts']) == 1
    assert state['attempts'][0]['status'] == ('DELIVERED' if write_completed else 'QUARANTINED')
    assert deliveries == ([99] if write_completed else [])
    assert result == (0 if write_completed else 1)
