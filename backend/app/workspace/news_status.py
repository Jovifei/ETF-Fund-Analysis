"""Public publication age and collector health; no network calls or feed URLs."""
from datetime import UTC,datetime
from sqlalchemy import func,select
from app.models import NewsItem
from app.workspace.models import WorkspaceDataJob
from app.workspace.jobs import utc

def read(db):
    now=datetime.now(UTC)
    rows=db.execute(select(NewsItem.source,func.count(),func.max(NewsItem.published_at),func.max(NewsItem.fetched_at)).group_by(NewsItem.source).limit(100)).all()
    sources=[]
    for source,count,published,fetched in rows:
        age=max(0,(now-utc(published)).total_seconds()/3600) if published else None
        sources.append({'source':source,'count':count,'latest_published_at':utc(published).isoformat() if published else None,
            'last_fetched_at':utc(fetched).isoformat() if fetched else None,'age_hours':round(age,1) if age is not None else None,
            'freshness':'older_than_24h' if age is not None and age>24 else 'within_24h' if age is not None else 'unknown'})
    task=db.scalar(select(WorkspaceDataJob).where(WorkspaceDataJob.request_json['task'].as_string().in_(['news','refresh'])).order_by(WorkspaceDataJob.created_at.desc()).limit(1))
    return {'sources':sources,'as_of':now.isoformat(),'provider_called':False,'task':None if task is None else {
        'status':task.status,'created_at':task.created_at.isoformat(),'finished_at':task.finished_at.isoformat() if task.finished_at else None,
        'steps':[{k:s.get(k) for k in ('task','status','reason')} for s in (task.result_json or {}).get('steps',[]) if s.get('task')=='refresh_news']},
        'note':'24小时标记只是发布时间年龄，不是今日全量覆盖证明。抓取成功可以返回旧消息；重新读取页面不会抓取新消息。'}
