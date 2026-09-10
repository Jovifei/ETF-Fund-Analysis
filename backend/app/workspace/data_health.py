"""Administrator-only, aggregate data-path diagnostics. No provider calls or writes."""
from datetime import UTC, datetime
from sqlalchemy import func, select

from app.models import (DailyBar, DecisionBoardSnapshot, IndicatorSnapshot, Instrument,
                        MarketContextSnapshot, NewsItem, QuoteSnapshot, SectorSnapshot, TaskRun)
from app.workspace.display_freshness import local_time
from app.workspace.models import WorkspacePreference


def serial(value, *, timezone):
    if value is None:
        return None
    if isinstance(value, datetime):
        # Unknown legacy naive timestamps remain unconverted, not guessed as UTC.
        return local_time(value, timezone).isoformat() if timezone is not None else value.isoformat()
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def read(db, settings, *, now=None):
    now = now or datetime.now(settings.timezone)
    counts = dict(db.execute(select(Instrument.kind, func.count()).where(
        Instrument.kind.in_(('ETF', 'LOF'))).group_by(Instrument.kind)).all())
    tracked = db.scalar(select(func.count()).select_from(Instrument).where(Instrument.enabled.is_(True))) or 0
    panels = []

    def append(key, label, model, date_column, fetch_column, task, retry_task, *, where=None, scope=False, fetch_timezone=None):
        query = select(func.count(), func.max(date_column), func.max(fetch_column)).select_from(model)
        if scope:
            query = query.join(Instrument, model.instrument_id == Instrument.id).where(Instrument.enabled.is_(True))
        if where is not None:
            query = query.where(where)
        rows, latest_source, latest_fetch = db.execute(query).one()
        coverage = None
        oldest_latest = None
        if scope:
            per_asset = select(model.instrument_id, func.max(date_column).label('latest')).join(
                Instrument, model.instrument_id == Instrument.id).where(Instrument.enabled.is_(True)).group_by(
                model.instrument_id).subquery()
            coverage, oldest_latest = db.execute(select(func.count(), func.min(per_asset.c.latest))).one()
        terminal = db.scalar(select(TaskRun).where(TaskRun.task_name == task).order_by(TaskRun.id.desc()).limit(1))
        successful = db.scalar(select(TaskRun).where(TaskRun.task_name == task, TaskRun.status == 'succeeded')
                               .order_by(TaskRun.id.desc()).limit(1))
        panels.append({'key': key, 'label': label, 'rows': rows, 'covered_instruments': coverage,
                       'tracked_instruments': tracked if scope else None,
                       'latest_source': serial(latest_source, timezone=settings.timezone),
                       'oldest_instrument_latest': serial(oldest_latest, timezone=settings.timezone),
                       # The maximum fetch time is NOT necessarily from the row with newest source time.
                       'latest_fetch_in_scope': serial(latest_fetch, timezone=fetch_timezone),
                       'last_success_at': serial(successful.finished_at, timezone=settings.timezone) if successful else None,
                       'last_attempt': ({'status': terminal.status,
                           'started_at': serial(terminal.started_at, timezone=settings.timezone),
                           'finished_at': serial(terminal.finished_at, timezone=settings.timezone),
                           'failed': terminal.status in ('failed', 'partial'),
                           'reason': '请在受控任务详情检查失败步骤；本面板不返回原始错误内容。'
                                      if terminal.status in ('failed', 'partial') else None} if terminal else None),
                       'status': 'stored_not_certified' if rows else 'missing',
                       'retry_task': retry_task})

    append('quotes', 'ETF 现价', QuoteSnapshot, QuoteSnapshot.quote_time, QuoteSnapshot.fetched_at,
           'refresh_quotes', 'quotes', scope=True, fetch_timezone=settings.timezone)
    append('daily', 'ETF 已存日线', DailyBar, DailyBar.trade_date, DailyBar.fetched_at,
           'refresh_bars', 'prices', scope=True)
    append('indicators', '已存指标', IndicatorSnapshot, IndicatorSnapshot.as_of_date, IndicatorSnapshot.generated_at,
           'refresh_indicators', 'recompute', scope=True, fetch_timezone=UTC)
    append('decisions', '决策快照', DecisionBoardSnapshot, DecisionBoardSnapshot.generated_at, DecisionBoardSnapshot.generated_at,
           'refresh_decision_board', 'recompute', fetch_timezone=settings.timezone)
    for kind, label in [('industry', '行业板块'), ('concept', '概念板块'), ('market', '全市场宽度')]:
        append(kind, label, SectorSnapshot, SectorSnapshot.trade_date, SectorSnapshot.fetched_at,
               'refresh_sector_snapshots', 'context', where=SectorSnapshot.board_type == kind, fetch_timezone=settings.timezone)
    append('context', '指数与代理观察', MarketContextSnapshot, MarketContextSnapshot.source_timestamp,
           MarketContextSnapshot.fetched_at, 'refresh_market_context', 'context', fetch_timezone=settings.timezone)
    append('news', '新闻发布时间', NewsItem, NewsItem.published_at, NewsItem.fetched_at,
           'refresh_news', 'news', fetch_timezone=UTC)
    caches = db.scalars(select(WorkspacePreference).where(
        WorkspacePreference.owner_scope.like('system:index-history:%'))).all()
    cache_days = [str((row.settings_json or {}).get('source_as_of')) for row in caches
                  if (row.settings_json or {}).get('source_as_of')]
    panels.append({'key':'index_history','label':'指数 K 线缓存','rows':len(cache_days),
                   'latest_source':max(cache_days) if cache_days else None,
                   'oldest_instrument_latest':min(cache_days) if cache_days else None,
                   'status':'stored_not_certified' if cache_days else 'missing','retry_task':'index_history',
                   'last_attempt':None, 'last_success_at':None, 'latest_fetch_in_scope':None})
    worker = db.get(WorkspacePreference, 'system:workspace-worker')
    return {'as_of': serial(now, timezone=settings.timezone), 'catalog_by_kind': counts,
            'catalog_count': sum(counts.values()), 'tracked_count': tracked, 'panels':panels,
            'worker_last_seen_at': (worker.settings_json or {}).get('last_seen_at') if worker else None,
            'balanced_refresh_enabled': settings.balanced_refresh_enabled,
            'provider_called':False, 'actionable':False,
            'note':'各时间为范围统计，最大抓取时间不一定属于最新源记录。无时区的旧日线抓取时间保留原串、待现场核对。已有记录不等于最新、全量或有交易资格；心跳不等于采集成功。未读取账户/持仓/密钥。'}
