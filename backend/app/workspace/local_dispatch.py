"""One deterministic close-window dispatcher; the OS lock owns execution."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
from math import isfinite

from app.workspace.local_job_ledger import LocalJobLedger
from app.workspace.local_schedule import LOCAL_SCHEDULE_SLOTS, LocalRunLock, SHANGHAI
from app.workspace.local_compute import closed_session_result_accepted, quote_control_coverage, OPTIONAL_TASK_PARTS
from app.workspace.shadow_bundle import digest
from app.workspace.refresh_policy import lunch_close_quote_fresh

DISPATCH_SLOTS = tuple(sorted(('13:55', *LOCAL_SCHEDULE_SLOTS)))
FULL_SLOTS = {'13:55', '15:15', '16:10'}


def utc_now():
    return datetime.now(timezone.utc)


def _validate_fast_replay_quotes(bundle, now):
    """A new board timestamp cannot renew an older exchange observation."""
    from app.workspace.read_model import market_time
    universe = set(bundle['manifest']['universe'])
    parts = bundle['parts']
    rows = parts['overview'].get('rows')
    details = parts['details']
    if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
            or len(rows) != len(universe) or {row.get('ts_code') for row in rows} != universe
            or set(details) != universe):
        raise ValueError('fast observation quote coverage incomplete')
    reference = now.astimezone(SHANGHAI)
    def stamp(value):
        try:
            result = market_time(value)
            if not isinstance(result, datetime):
                raise ValueError
            return result.astimezone(SHANGHAI)
        except (ValueError, TypeError, AttributeError, OverflowError):
            raise ValueError('fast observation timestamp invalid') from None
    for row in rows:
        quote = details[row['ts_code']].get('quote') or {}
        summary = row.get('quote') or {}
        if (not isinstance(quote, dict) or not isinstance(summary, dict)
                or quote.get('is_realtime') is not True or quote.get('timestamp_verified') is not True
                or quote.get('is_mock') is not False or not isinstance(quote.get('source'), str)
                or not quote['source'].strip() or 'mock' in quote['source'].lower()
                or type(quote.get('price')) not in (int, float) or not isfinite(quote['price']) or quote['price'] <= 0):
            raise ValueError('fast observation quote unqualified')
        observed, fetched = stamp(quote.get('source_time')), stamp(quote.get('fetched_at'))
        if (observed.date() != reference.date() or fetched.date() != reference.date()
                or not observed <= fetched <= reference
                or not 0 <= (reference-fetched).total_seconds() <= 8*60
                or not (0 <= (reference-observed).total_seconds() <= 8*60
                        or lunch_close_quote_fresh(observed, reference))):
            raise ValueError('fast observation quote expired or outside session')
        if (stamp(summary.get('source_time')) != observed
                or summary.get('source') != quote['source']
                or any(summary.get(key) is not quote[key] for key in ('is_realtime', 'timestamp_verified', 'is_mock'))
                or ('fetched_at' in summary and stamp(summary['fetched_at']) != fetched)):
            raise ValueError('fast observation overview detail mismatch')


def load_pending_bundle(root: Path, attempt: dict, identity: dict, *, now: datetime):
    """Validate the immutable packet again; display TTL is not quote freshness."""
    from app.workspace.local_display_contract import verify_bundle_integrity, MAX_BUNDLE_BYTES
    from app.workspace.shadow_client import _unique_object
    name = attempt.get('bundle_file')
    if not isinstance(name, str) or not re.fullmatch(r'bundle_[1-9][0-9]*\.json', name):
        raise ValueError('owned bundle basename required')
    outbox = Path(root) / 'outbox'
    path = outbox / name
    for item in (Path(root), outbox, path):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('owned immutable replay path required')
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError('pending bundle over budget')
    bundle = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    manifest = bundle.get('manifest', {})
    if (not verify_bundle_integrity(bundle, now=now) or digest(manifest) != attempt.get('bundle_id')
            or manifest.get('code_sha') != identity['code_sha']
            or manifest.get('config_hash') != identity['config_hash']
            or digest(sorted(manifest.get('universe', []))) != identity['scope_hash']):
        raise ValueError('pending bundle invalid expired or identity mismatch')
    lineage = manifest.get('execution_lineage') or {}
    if (not re.fullmatch(r'[0-9a-f]{64}', identity.get('execution_hash', ''))
            or lineage.get('contract_version') != 'local-execution-lineage-v1'
            or lineage.get('execution_hash') != identity['execution_hash']
            or lineage.get('config_file_hash') != identity.get('config_file_hash')):
        raise ValueError('pending execution configuration mismatch')
    if attempt['slot_id'].rsplit(' ', 1)[-1] not in FULL_SLOTS:
        generated = datetime.fromisoformat(manifest['generated_at'])
        if (now - generated).total_seconds() > 8 * 60:
            raise ValueError('fast observation expired')
        _validate_fast_replay_quotes(bundle, now)
    return bundle


def dispatch_once(root: Path, identity: dict, *, calendar, run_job, replay, now=utc_now,
                  slots=DISPATCH_SLOTS, recover_export=None, execution=None) -> int:
    """Execute at most the newest eligible slot; the next minute catches overruns.

    run_job(mode, on_task, on_export, on_receipt, lock) returns its actual exit
    status. replay(attempt, on_receipt) resends its exact immutable bundle.
    Neither callback may bypass the existing market/admission/upload contracts.
    """
    lock = LocalRunLock(Path(root) / '.run.lock')
    if not lock.acquire():
        return 2
    ledger = None
    attempt = None
    try:
        ledger = LocalJobLedger(root)
        ledger.recover_interrupted(now(), lock_held=True)
        current = now()
        decision = calendar.decision(current.astimezone(SHANGHAI).date())
        verified = decision.verified and decision.is_trade_day
        if not decision.verified:
            return 1
        slot = ledger.plan_due(current, verified_trading=bool(verified), identity=identity, slots=slots)
        if not verified:
            return 0
        recovery_failed = False
        for intent in ledger.export_intents():
            try:
                if recover_export is None:
                    raise ValueError('export resolver unavailable')
                bundle = recover_export(attempt=intent)
                ledger.mark_export(intent['attempt_id'], manifest=bundle['manifest'],
                                   bundle_file=intent['bundle_file'], now=now())
            except Exception as exc:
                ledger.quarantine_export(intent['attempt_id'], reason=type(exc).__name__, now=now())
                recovery_failed = True
        pending = ledger.pending_replay(now=now(), identity=identity)
        # A newer due observation takes priority over retrying an old generation.
        if slot is None and pending:
            attempt = pending
            uploads = [j for j in ledger.summary()['jobs']
                       if j['attempt_id'] == attempt['attempt_id'] and j['job_name'].startswith('upload_')]
            name = f'upload_{len(uploads) + 1}'
            ledger.record_job(attempt['attempt_id'], name, status='running', now=now())
            try:
                replay(attempt=attempt, on_receipt=lambda manifest, receipt: ledger.mark_delivered(
                    attempt['attempt_id'], manifest=manifest, receipt=receipt, now=now()))
                if ledger.get_attempt(attempt['attempt_id'])['status'] != 'DELIVERED':
                    raise ValueError('validated receipt missing')
                ledger.record_job(attempt['attempt_id'], name, status='succeeded', now=now())
            except Exception as exc:
                ledger.record_job(attempt['attempt_id'], name, status='failed', now=now(),
                                  details={'error_type': type(exc).__name__})
                return 1
            return 0 if ledger.get_attempt(attempt['attempt_id'])['status'] == 'DELIVERED' else 1
        if slot is None:
            return 1 if recovery_failed else 0
        attempt = ledger.claim(slot['slot_id'], now(), identity=identity, lock_held=True)
        aid = attempt['attempt_id']
        if execution is not None:
            ledger.record_job(aid, 'execution_identity', status='succeeded', required=False,
                              now=now(), details=execution)

        def on_task(name, result, run_id):
            if result is None:
                ledger.record_job(aid, name, status='running', now=now(), run_id=run_id,
                                  required=name not in OPTIONAL_TASK_PARTS)
                return
            details = {key: result[key] for key in ('requested', 'completed', 'failed_count', 'degraded_count', 'coverage_complete')
                       if key in result}
            details.update({'source_task_status': result.get('status', 'unknown'),
                            'accepted_closed_session': closed_session_result_accepted(result)})
            if name == 'refresh_quotes':
                control = quote_control_coverage(result, scope_hash=identity['scope_hash'], run_id=run_id)
                if control is not None:
                    details.update(control)
            actual_run = result.get('run_id')
            if actual_run is not None and actual_run != run_id:
                ledger.record_job(aid, name, status='failed', now=now(), run_id=run_id,
                    required=name not in OPTIONAL_TASK_PARTS,
                    details={'run_id': actual_run, 'error_type': 'TaskRunIdentityMismatch'})
                raise ValueError('task run identity changed')
            scope = result.get('execution_scope') or {}
            codes = scope.get('target_codes')
            if ('coverage_complete' not in details and result.get('status') == 'succeeded'
                    and isinstance(codes, list) and digest(sorted(codes)) == identity['scope_hash']
                    and type(result.get('requested')) is int and type(result.get('completed')) is int):
                details['coverage_complete'] = result['requested'] == result['completed'] == len(codes)
            status = result.get('status', 'failed')
            if status not in {'succeeded', 'partial', 'failed', 'unavailable', 'interrupted'}:
                status = 'unavailable' if name in OPTIONAL_TASK_PARTS else 'failed'
            ledger.record_job(aid, name, status=status, now=now(), run_id=run_id,
                              required=name not in OPTIONAL_TASK_PARTS, details=details)

        def on_export_intent(bundle, path):
            lineage = bundle['manifest'].get('execution_lineage') or {}
            if execution is not None and any(lineage.get(key) != value for key, value in execution.items()):
                raise ValueError('claimed execution configuration changed')
            details = {key: lineage.get(key) for key in ('execution_hash', 'config_file_hash',
                                                        'base_input_hash', 'quote_batch_hash')}
            details['execution_mode'] = lineage.get('mode')
            ledger.record_job(aid, 'execution_contract', status='succeeded', required=False,
                              now=now(), details=details)
            ledger.mark_export_intent(aid, manifest=bundle['manifest'], bundle_file=Path(path).name, now=now())

        def on_export(bundle, path):
            ledger.mark_export(aid, manifest=bundle['manifest'], bundle_file=Path(path).name, now=now())
            ledger.record_job(aid, 'upload_1', status='running', now=now())

        def on_receipt(manifest, receipt):
            ledger.mark_delivered(aid, manifest=manifest, receipt=receipt, now=now())
            ledger.record_job(aid, 'upload_1', status='succeeded', now=now())

        result = run_job('full' if slot['slot'] in FULL_SLOTS else 'fast', on_task=on_task,
                         on_export_intent=on_export_intent,
                         on_export=on_export, on_receipt=on_receipt, lock=lock)
        latest = ledger.get_attempt(aid)
        if latest['status'] == 'DELIVERED':
            return result
        if latest['status'] == 'EXPORTED':
            # Preserve the package across ambiguous HTTP outcomes; do not recalculate.
            ledger.record_job(aid, 'upload_1', status='failed', now=now(),
                              details={'reason': 'delivery_not_acknowledged'})
        else:
            ledger.fail(aid, reason='run_failed' if result else 'receipt_missing', now=now())
        return result or 1
    except Exception as exc:
        if ledger is not None and attempt is not None:
            latest = ledger.get_attempt(attempt['attempt_id'])
            if latest['status'] in {'RUNNING', 'EXPORTING'}:
                ledger.fail(attempt['attempt_id'], reason=type(exc).__name__, now=now())
        return 1
    finally:
        lock.release()
