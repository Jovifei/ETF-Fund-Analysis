"""One deterministic close-window dispatcher; the OS lock owns execution."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re

from app.workspace.local_job_ledger import LocalJobLedger
from app.workspace.local_schedule import LOCAL_SCHEDULE_SLOTS, LocalRunLock, SHANGHAI
from app.workspace.local_compute import closed_session_result_accepted, OPTIONAL_TASK_PARTS
from app.workspace.shadow_bundle import digest

DISPATCH_SLOTS = ('13:55', *LOCAL_SCHEDULE_SLOTS)
FULL_SLOTS = {'13:55', '15:15', '16:10'}


def utc_now():
    return datetime.now(timezone.utc)


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
    if attempt['slot_id'].rsplit(' ', 1)[-1] not in FULL_SLOTS:
        generated = datetime.fromisoformat(manifest['generated_at'])
        if (now - generated).total_seconds() > 8 * 60:
            raise ValueError('fast observation expired')
    return bundle


def dispatch_once(root: Path, identity: dict, *, calendar, run_job, replay, now=utc_now,
                  slots=DISPATCH_SLOTS) -> int:
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
            return 0
        attempt = ledger.claim(slot['slot_id'], now(), identity=identity, lock_held=True)
        aid = attempt['attempt_id']

        def on_task(name, result, run_id):
            if result is None:
                ledger.record_job(aid, name, status='running', now=now(), run_id=run_id,
                                  required=name not in OPTIONAL_TASK_PARTS)
                return
            details = {key: result[key] for key in ('requested', 'completed', 'failed_count', 'degraded_count', 'coverage_complete')
                       if key in result}
            details.update({'source_task_status': result.get('status', 'unknown'),
                            'accepted_closed_session': closed_session_result_accepted(result)})
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

        def on_export(bundle, path):
            ledger.mark_export(aid, manifest=bundle['manifest'], bundle_file=Path(path).name, now=now())
            ledger.record_job(aid, 'upload_1', status='running', now=now())

        def on_receipt(manifest, receipt):
            ledger.mark_delivered(aid, manifest=manifest, receipt=receipt, now=now())
            ledger.record_job(aid, 'upload_1', status='succeeded', now=now())

        result = run_job('full' if slot['slot'] in FULL_SLOTS else 'fast', on_task=on_task,
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
            if latest['status'] == 'RUNNING':
                ledger.fail(attempt['attempt_id'], reason=type(exc).__name__, now=now())
        return 1
    finally:
        lock.release()
