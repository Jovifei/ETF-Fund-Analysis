"""Read-only market discovery status and deduplicated, opt-in low-frequency jobs."""
from datetime import UTC, datetime, timedelta
from sqlalchemy import func, select

from app.models import Instrument, SectorSnapshot
from app.workspace import data_jobs
from app.workspace.config import workspace_settings
from app.workspace.jobs import lock_owner, utc
from app.workspace.models import WorkspaceDataJob, WorkspacePreference
from app.workspace.protocol import DataRequest


def latest_job(db, task):
    return db.scalar(select(WorkspaceDataJob).where(WorkspaceDataJob.request_json['task'].as_string() == task).order_by(WorkspaceDataJob.created_at.desc()).limit(1))


def state(db):
    jobs = [latest_job(db, task) for task in ('context','catalog')]
    counts = dict(db.execute(select(Instrument.kind,func.count()).where(Instrument.kind.in_(('ETF','LOF'))).group_by(Instrument.kind)).all())
    boards = dict(db.execute(select(SectorSnapshot.board_type,func.count(func.distinct(SectorSnapshot.sector_name))).group_by(SectorSnapshot.board_type)).all())
    saved = db.get(WorkspacePreference,'system:catalog-discovery')
    worker = db.get(WorkspacePreference,'system:workspace-worker')
    return {'catalog_count':sum(counts.values()),'catalog_by_kind':counts,'boards_by_kind':boards,
        'jobs':[{'job_id':row.job_id,'task':row.request_json['task'],'status':row.status,'created_at':row.created_at.isoformat(),'finished_at':row.finished_at.isoformat() if row.finished_at else None,'current_step':(row.result_json or {}).get('current_step'),'steps':(row.result_json or {}).get('steps',[]),'failure_reason':row.failure_reason} for row in jobs if row],
        'worker_last_seen_at':(worker.settings_json or {}).get('last_seen_at') if worker else None,
        'catalog_warning':'目录仅为当前已入库样本；请检查目录任务和上游失败原因。' if counts.get('ETF',0)<100 else None,
        'catalog_sync':saved.settings_json if saved else None,
        'automatic_discovery':workspace_settings().discovery_enabled,'provider_called':False,'actionable':False}


def enqueue(db, user_id=None, *, manual=False, now=None):
    now = now or datetime.now(UTC)
    lock_owner(db,'workspace-market-discovery')
    submitted = []
    # Context first: slow all-market catalog must not delay industry/concepts.
    for task in ('context','catalog'):
        previous = latest_job(db, task)
        if previous and previous.status in {'queued','running'}:
            submitted.append({'task':task,'job_id':previous.job_id,'created':False});continue
        cooldown = timedelta(minutes=5 if manual else 60 if previous and previous.status in {'failed','partial'} else 720)
        if previous and now - utc(previous.created_at) < cooldown:
            submitted.append({'task':task,'job_id':previous.job_id,'created':False});continue
        # Stable time bucket prevents cross-process duplicate submissions even
        # on SQLite, where transaction-scoped advisory locks are unavailable.
        bucket = int(now.timestamp()) // int(cooldown.total_seconds())
        row, created = data_jobs.enqueue(db,DataRequest(task=task,request_key=f'discovery-{task}-{bucket}'),None)
        submitted.append({'task':task,'job_id':row.job_id,'created':created})
    return {'jobs':submitted,'provider_called':False,'models_called':False}
