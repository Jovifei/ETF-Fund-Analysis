#!/usr/bin/env python3
"""Read-only bounded capability probes. No DB write, auto-qualification or secrets export.

Use --public-only for credential-free CI. Without it, only operator-provided
process environment credentials are used; no legacy config/history is searched.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def probe(provider, operation, call):
    started=time.monotonic()
    try:
        records=call()
        rows=list(records or [])
        result={'provider':provider,'operation':operation,'status':'readable' if rows else 'empty','records':len(rows)}
        if rows and hasattr(rows[0],'trade_date'):
            result.update(first_date=str(min(row.trade_date for row in rows)),last_date=str(max(row.trade_date for row in rows)),
                          volume_present=sum(row.volume is not None for row in rows),amount_present=sum(row.amount is not None for row in rows),
                          sources=sorted(set(row.source for row in rows)))
        if rows and hasattr(rows[0],'quote_time'):
            result.update(source_timestamps_reported=sum(bool(row.is_realtime and not row.degraded_reason) for row in rows),
                          degraded=sum(bool(row.degraded_reason) for row in rows))
        encoded=json.dumps([r.to_dict() for r in rows],default=str,sort_keys=True).encode()
        result['response_hash']=hashlib.sha256(encoded).hexdigest()
    except Exception as exc:
        # Never write raw exception text, URLs, bodies or environment variables.
        result={'provider':provider,'operation':operation,'status':'unavailable','records':0,'failure_class':type(exc).__name__}
    result.update(duration_seconds=round(time.monotonic()-started,3),actionable=False,qualification='not_qualified')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--public-only',action='store_true')
    parser.add_argument('--timeout',type=float,default=8)
    parser.add_argument('--include-catalog',action='store_true')
    parser.add_argument('--include-news',action='store_true')
    parser.add_argument('--code',action='append',default=[])
    args=parser.parse_args()
    if not 0.5 <= args.timeout <= 30:parser.error('timeout must be 0.5..30 seconds per call')
    import re
    codes=args.code or ['510300.SH','512480.SH']
    if len(codes)>3 or any(not re.fullmatch(r'\d{6}\.(SH|SZ)',c) for c in codes):parser.error('at most 3 explicit ETF/LOF exchange codes')
    from app.core.config import Settings
    from app.providers.akshare import AKShareProvider
    from app.providers.tushare import TushareProvider
    from app.providers.catalog import catalog_records
    from app.services.trading_calendar_service import TradingCalendarService
    from app.services.market_service import MarketService
    # Ignore dotenv files. The process environment is explicit caller config.
    settings=Settings(_env_file=None,market_provider='public_composite',akshare_timeout_seconds=args.timeout,tushare_timeout_seconds=args.timeout)
    if args.public_only:settings=settings.model_copy(update={'tushare_token':'','news_rss_urls':'','ftshare_enabled':False})
    now=datetime.now(settings.timezone)
    date=now.date() if now.hour>=16 else now.date()-timedelta(days=1)
    end=TradingCalendarService(settings).effective_trade_date(date)
    start=end-timedelta(days=365)
    rows=[]
    for name,cls in [('akshare',AKShareProvider),('tushare',TushareProvider)]:
        if name=='tushare' and not settings.tushare_token:
            rows.append({'provider':name,'operation':'all','status':'not_configured','reason':'credentials_missing','called':False})
            continue
        try:provider=cls(settings)
        except Exception as exc:
            rows.append({'provider':name,'operation':'all','status':'unavailable','reason':type(exc).__name__,'called':False})
            continue
        try:
            if args.include_catalog:rows.append(probe(name,'catalog',lambda:catalog_records(provider)))
            for code in codes:
                def history(code=code):
                    items=provider.fetch_daily_bars(code,start,end)
                    MarketService._validated_bar_batch(items,code,start,end)
                    return items
                result=probe(name,'daily',history);result['code']=code;rows.append(result)
            rows.append(probe(name,'quotes',lambda:provider.fetch_spot_quotes(codes)))
            if args.include_news:rows.append(probe(name,'news',lambda:provider.fetch_news(72)))
        finally:provider.close()
    # Probes never opt an unqualified source into the provider fallback chain.
    rows.extend([{'provider':'ftshare','operation':'all','status':'not_probed','reason':'qualification_unchanged','called':False},
                 {'provider':'rss','operation':'news','status':'not_probed','reason':'use_explicit_private_feed_configuration','called':False}])
    attempted = [row for row in rows if row.get('called') is not False]
    report={'schema_version':'data-probe-v1.0.1','as_of':datetime.now(UTC).isoformat(),'scope':'read_only_samples_not_service_sla',
        'source_version':'1.0.1','public_only':args.public_only,'probe_complete':True,
        'all_requested_readable':bool(attempted) and all(row['status']=='readable' for row in attempted),
        'probes':rows,'database_written':False,'credentials_exported':False,'qualification_changed':False,'actionable':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'probe_complete':True,'readable_calls':sum(r['status']=='readable' for r in rows),'unavailable_calls':sum(r['status']=='unavailable' for r in rows),'qualification_changed':False}))
    return 0


if __name__=='__main__':raise SystemExit(main())
