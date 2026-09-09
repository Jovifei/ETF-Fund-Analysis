"""Versioned 1/5/20-session price-only research, separate from current actions.

Persisted on explicit worker jobs, never computed by GET or by a language model.
No calibration/promotion is inferred from cache existence or a long sample.
"""
from datetime import UTC, datetime, time, date
import math
import pandas as pd
from sqlalchemy import select
from app.models import DailyBar, Instrument
from app.utils.feature_store import build_feature_frame
from app.services.forecast_service import similarity_forecast
from app.workspace.models import WorkspacePreference
from app.workspace.protocol import content_hash

VERSION='price-similarity-research-v104-1-5-20'
FEATURES=('return_5d','return_20d','ma_gap_5_20','macd_norm','kdj_j','rsi14','atr_pct')
HORIZONS=(1,5,20)
PREFIX='v104:outlook:'


def compute(rows, settings):
    cfg=settings.load_strategy()['indicator']
    # Reject invalid/contradictory inputs before fitting. No hidden dedup, fills,
    # mixed price bases, or mock+real historical ensembles.
    unique={}
    for r in rows:
        day=date.fromisoformat(r['date']).isoformat()
        prices=[float(r[k]) for k in ('open','high','low','close')]
        o,h,l,c=prices
        if not all(math.isfinite(v) and v>0 for v in prices) or not l<=min(o,c)<=max(o,c)<=h:
            raise ValueError('invalid_historical_ohlc')
        if day in unique: raise ValueError('duplicate_historical_date')
        unique[day]=r
    rows=[unique[k] for k in sorted(unique)]
    bases={r.get('adjust','none') for r in rows}
    mocks={'mock' in str(r.get('source','')).lower() for r in rows}
    if len(bases)>1 or len(mocks)>1: raise ValueError('mixed_historical_basis_or_mock')
    now=datetime.now(settings.timezone)
    rows=[r for r in rows if r['date']<now.date().isoformat() or r['date']==now.date().isoformat() and now.time()>=time(15)]
    if len(rows)<250:
        return {'status':'unavailable','reason':'至少250根已结束日K；短样本不补预测','forecasts':{},'source_as_of':rows[-1]['date'] if rows else None,'actionable':False}
    raw=pd.DataFrame(rows).rename(columns={'date':'trade_date'})
    # Price-only feature selection is explicit. Unknown volume is not evidence.
    raw['volume']=0.;raw['amount']=0.
    rich=build_feature_frame(raw,cfg).frame
    results={}
    for horizon in HORIZONS:
        value=similarity_forecast(rich,horizon=horizon,neighbors=60,minimum_neighbors=25,maximum_confidence=40,feature_columns=FEATURES)
        results[str(horizon)]={k:getattr(value,k) for k in ('p_up','expected_return','q10','q50','q90','sample_count','confidence')}
        results[str(horizon)].update(horizon=horizon,model_version=VERSION,calibration_status='not_calibrated',
            probability_label='historical_frequency',as_of_date=rows[-1]['date'],actionable=False,
            diagnostics=value.diagnostics,**{k:v for k,v in value.corridor.items() if k.startswith('terminal_price')},
            explanation='以同一标的历史价格状态找相似样本，目标为未来'+str(horizon)+'个交易日的收盘收益；量能、新闻及执行成本未纳入。相似样本有重叠，不能当独立样本或校准概率。')
    return {'status':'research','forecasts':results,'model_version':VERSION,'source_as_of':rows[-1]['date'],
        'input_hash':content_hash(rows),'source_bar_count':len(rows),'feature_names':list(FEATURES),'created_at':datetime.now(UTC).isoformat(),
        'actionable':False,'not_strategy_output':True,'qualification':'mock' if settings.market_provider=='mock' or True in mocks else 'not_qualified'}


def refresh(db,settings,codes):
    query=select(Instrument).where(Instrument.kind.in_(('ETF','LOF')))
    query=query.where(Instrument.ts_code.in_(codes)) if codes else query.where(Instrument.enabled.is_(True))
    instruments=db.scalars(query.order_by(Instrument.ts_code).limit(30)).all()
    failures=[];saved=0
    for inst in instruments:
        try:
            with db.begin_nested():
                basis=db.scalars(select(DailyBar.adjust).where(DailyBar.instrument_id==inst.id).distinct()).all()
                adjust='none' if 'none' in basis else basis[0] if len(basis)==1 else None
                bars=list(reversed(db.scalars(select(DailyBar).where(DailyBar.instrument_id==inst.id,DailyBar.adjust==adjust).order_by(DailyBar.trade_date.desc()).limit(2000)).all())) if adjust else []
                rows=[dict(date=b.trade_date.isoformat(),open=b.open,high=b.high,low=b.low,close=b.close,source=b.source,adjust=b.adjust) for b in bars]
                result=compute(rows,settings)
                key=PREFIX+inst.ts_code;cache=db.get(WorkspacePreference,key)
                if cache is None:cache=WorkspacePreference(owner_scope=key,user_id=None);db.add(cache)
                cache.settings_json={**result,'ts_code':inst.ts_code}
                db.flush();saved+=1
        except Exception as exc:
            failures.append({'ts_code':inst.ts_code,'reason':type(exc).__name__})
    return {'status':'partial' if failures else 'succeeded','instruments':saved,'requested':len(instruments),'failures':failures,'actionable':False}


def read(db,codes):
    rows=db.scalars(select(WorkspacePreference).where(WorkspacePreference.owner_scope.in_([PREFIX+c for c in codes]))) if codes else []
    result={}
    for r in rows:
        if r.settings_json.get('model_version') not in (None,VERSION): continue
        value=dict(r.settings_json);code=value['ts_code']
        # Cache is never silently called current: disclose its as-of boundary.
        forecasts={k:{**v,'cache_note':'冻结于 '+str(value.get('source_as_of'))+'；新行情入库或历史修订后请重算'} for k,v in value.get('forecasts',{}).items()}
        result[code]={**value,'forecasts':forecasts}
    return result
