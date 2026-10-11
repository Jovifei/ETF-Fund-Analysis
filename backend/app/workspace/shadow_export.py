"""Public, persisted-only export from a dedicated local SQLite database."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.models import MarketContextSnapshot
from app.services.decision_board_service import DecisionBoardService
from app.workspace.read_model import overview,chart_data
from app.workspace.shadow_bundle import make_bundle,timestamp
from app.utils.hashing import stable_hash
from app.workspace.shadow_projection import project_chart
from app.workspace.candle_periods import transform_chart

ROW_FIELDS={'ts_code','name','kind','grade','grade_reason','freshness','data_status','price','price_basis','theme_l1','theme_l2','research_only','actionable'}
BAR_FIELDS={'date','open','high','low','close','volume','amount','source'}
def local_settings(root,database):
    original_root=Path(root);original_database=Path(database)
    if original_root.is_symlink() or original_database.is_symlink():raise ValueError('symlink database rejected')
    root=original_root.resolve();database=original_database.resolve()
    if not (root/'.shadow-local').is_file() or database.name!='research.sqlite3':raise ValueError('local ownership marker required')
    if root==root.parent or root not in database.parents or database.suffix!='.sqlite3' or not database.exists():raise ValueError('dedicated existing local SQLite database required')
    if root.is_symlink() or database.is_symlink():raise ValueError('symlink database rejected')
    import os
    os.environ['WORKSPACE_BRIDGE_ENABLED']='false'
    os.environ['WORKSPACE_DAILY_REVIEW_ENABLED']='false'
    return Settings(_env_file=None,app_env='test',market_provider='mock',allow_mock_fallback=False,auto_create_schema=False,database_url='sqlite:///'+database.as_posix(),auth_enabled=False,llm_enabled=False,analysis_enabled=False,ocr_mode='disabled')
def export_local(settings,*,sequence,code_sha,now=None):
    now=now or datetime.now(timezone.utc)
    if settings.app_env!='test' or settings.market_provider!='mock' or not settings.database_url.startswith('sqlite:///'):raise ValueError('offline dedicated local mode required')
    engine=create_engine(settings.database_url)
    try:
        with Session(engine) as db, db.begin():
            # Explicit read transaction holds one SQLite snapshot across all projections.
            db.connection().exec_driver_sql('BEGIN')
            original=DecisionBoardService(settings).read_latest(db) or {}
            if original.get('read_contract')!='version_matched':raise ValueError('local board runtime mismatch')
            generated=timestamp(original.get('generated_at'))
            if generated>now or (now-generated).total_seconds()>7200:raise ValueError('local board stale or future')
            view=overview(db,settings,limit=1000)
            if view['total']>1000:raise ValueError('bounded universe exceeded')
            rows=[{**{k:v for k,v in row.items() if k in ROW_FIELDS},'research_only':True,'actionable':False} for row in view['rows']]
            board={'rows':rows,'snapshot_id':view['snapshot_id'],'generated_at':view['generated_at'],'contains_mock':view['contains_mock'],'actionable':False}
            charts={}
            for row in rows:
                chart=chart_data(db,settings,row['ts_code'],'1d',250,as_of=generated) or {}
                charts[row['ts_code']]=project_chart(transform_chart(chart,'1d',settings.load_strategy().get('indicator',{}),limit=250,now=generated))
            refs=[]
            # Only evidence identities; no private users, raw payloads or account queries.
            for item in db.scalars(select(MarketContextSnapshot).limit(200)).all():
                source_time=item.source_timestamp
                if source_time is None:
                    refs.append({'id':item.id,'source':item.source,'source_timestamp':None,'reason':'source_time_unknown'})
                    continue
                if source_time.tzinfo is None:source_time=source_time.replace(tzinfo=settings.timezone)
                if source_time>generated:continue
                refs.append({'id':item.id,'source':item.source,'source_timestamp':source_time.isoformat()})
            return make_bundle(board,charts,{'references':refs},sequence=sequence,generated_at=generated,expires_at=generated+timedelta(hours=2),code_sha=code_sha,config_hash=stable_hash(settings.load_strategy()))
    finally:engine.dispose()
def offline_result_ready(task, result):
    """Transport readiness only; Mock quotes remain degraded, never qualified."""
    if result.get('status') == 'succeeded':
        return True
    return (task == 'refresh_quotes' and result.get('status') == 'partial'
            and type(result.get('requested')) is int and result['requested'] > 0
            and result.get('received') == result['requested']
            and result.get('degraded') == result['requested']
            and result.get('missing') == 0 and result.get('realtime') == 0)

def compute_local(settings):
    if settings.app_env!='test' or settings.market_provider!='mock' or not settings.database_url.startswith('sqlite:///'):raise ValueError('offline local computation only')
    from app.services.task_service import TaskService
    from app.services.settlement import settled_session
    mock_date = settled_session(settings)
    engine=create_engine(settings.database_url);service=TaskService(settings);results=[]
    try:
        for task in ['refresh_bars','refresh_quotes','refresh_sector_snapshots','refresh_indicators','refresh_forecasts','refresh_signals','refresh_decision_board']:
            with Session(engine) as db,db.begin():
                result=service.run(db,task,**({'lookback_days':420, 'mock_settled_date':mock_date} if task=='refresh_bars' else {}))
                result = {**result, 'task_name': task, 'display_ready': offline_result_ready(task, result)}
                results.append(result)
                if not result['display_ready']:break
    finally:service.close();engine.dispose()
    return results
