"""Bounded durable index chart cache in the existing system KV table.

No schema fork, no writes from GET, no dependency on a user's laptop being on.
A full batch is validated before atomic replace; failed refresh preserves cache.
"""
from datetime import UTC, datetime, timedelta
from sqlalchemy import select

from app.models import MarketContextRegistry
from app.services.audit_service import AuditTimer, record_provider_audit
from app.services.market_service import MarketService
from app.workspace.chart import cached_indicator_series
from app.workspace.models import WorkspacePreference
from app.workspace.protocol import content_hash
from app.providers.index_history import INDEX_CODES

PREFIX = 'system:index-history:'
MAX_ROWS = 1500


def refresh(db, settings, provider, run_id, lookback_days=1200):
    now = datetime.now(settings.timezone)
    end = now.date()
    start = end-timedelta(days=min(1800,max(30,lookback_days)))
    registries = db.scalars(select(MarketContextRegistry).where(
        MarketContextRegistry.context_kind=='index', MarketContextRegistry.enabled.is_(True),
        MarketContextRegistry.source_symbol.in_(list(INDEX_CODES)))).all()
    failures, saved = [], 0
    for registry in registries:
        timer, error, records = AuditTimer(), None, []
        try:
            records = provider.fetch_index_bars(registry.source_symbol,start,end)
            batch = MarketService._validated_bar_batch(records,registry.source_symbol,start,end)
            if not batch:
                raise ValueError('empty_index_history')
            key=PREFIX+registry.context_id
            with db.begin_nested():
                cache=db.get(WorkspacePreference,key)
                old=(cache.settings_json if cache else {}) or {}
                old_rows=old.get('bars',[])
                if old.get('data_hash') != content_hash(old_rows): old_rows=[]
                bars={row['date']:row for row in old_rows}
                for (day,_), (bar,_) in batch.items():
                    bars[day.isoformat()]={
                        'date':day.isoformat(),'open':bar.open,'high':bar.high,'low':bar.low,
                        'close':bar.close,'volume':bar.volume,'amount':bar.amount,'source':bar.source,
                        'is_partial':day==end and (now.hour,now.minute)<(15,0)}
                ordered=[bars[day] for day in sorted(bars)][-MAX_ROWS:]
                data={'context_id':registry.context_id,'label':registry.label,
                      'ts_code':registry.source_symbol,'bars':ordered,
                      'fetched_at':datetime.now(UTC).isoformat(),'data_hash':content_hash(ordered),
                      'cache_version':'index-ohlc-v103','source_as_of':ordered[-1]['date']}
                if cache is None:
                    cache=WorkspacePreference(owner_scope=key,user_id=None);db.add(cache)
                cache.settings_json=data
                db.flush()
            saved+=1
        except Exception as exc:
            error=exc
            failures.append({'context_id':registry.context_id,'reason':type(exc).__name__})
        finally:
            record_provider_audit(db,run_id=run_id,operation='fetch_index_bars',provider=provider,
                result=records,error=error,latency_ms=timer.elapsed_ms)
    return {'status':'succeeded' if saved and not failures else 'partial',
            'instruments':saved,'failures':failures,'requested':len(registries),'actionable':False}


def read(db, settings, context_id, limit=500):
    registry=db.scalar(select(MarketContextRegistry).where(
        MarketContextRegistry.context_id==context_id,MarketContextRegistry.context_kind=='index'))
    if registry is None:
        return None
    cache=db.get(WorkspacePreference,PREFIX+context_id)
    data=dict(cache.settings_json or {}) if cache else {}
    bars=data.get('bars',[])
    if bars and data.get('data_hash') != content_hash(bars):
        bars=[]
    series=cached_indicator_series(bars,settings.load_strategy()['indicator']) if bars else []
    last=series[-1] if series else None
    pct=last['close']/series[-2]['close']-1 if len(series)>1 else None
    return {**data,'context_id':context_id,'ts_code':registry.source_symbol or context_id,
        'label':registry.label,'interval':'1d','available':bool(series),'bars':series[-limit:],
        'reason':None if series else 'index_history_not_synced',
        'summary':{'price':last['close'] if last else None,'change_ratio':pct,
            'source_time':last['date'] if last else None,'price_basis':'historical_close',
            'is_partial':last.get('is_partial',False) if last else False},
        'adjust':'none','cost_overlay_allowed':False,'sr_overlay_allowed':False,
        'qualification':'mock' if any('mock' in str(row.get('source','')).lower() for row in bars) else 'historical_index','actionable':False,'provider_called':False,
        'indicator_version':settings.load_strategy()['indicator_version'],
        'indicator_note':'指数历史 OHLC，不是 ETF 代理；日线并非盘中实时报价。'}
