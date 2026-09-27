"""Read-only chart research. Calendar candles and price levels are not forecasts."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from app.utils.hashing import stable_hash
from app.utils.support_resistance import build_support_resistance
from app.workspace.chart import cached_indicator_series, number

PERIODS=('1d','1w','1mo')
TZ=ZoneInfo('Asia/Shanghai')


def aggregate_bars(rows: list[dict], period: str, *, now: datetime | None=None) -> list[dict]:
    if period not in PERIODS:
        raise ValueError('unsupported_calendar_period')
    if period=='1d':
        return [dict(row) for row in rows]
    now=(now or datetime.now(TZ)).astimezone(TZ)
    groups: dict[date,list[dict]]={}
    for row in sorted(rows,key=lambda r:r['date']):
        day=date.fromisoformat(row['date'][:10])
        key=day-timedelta(days=day.weekday()) if period=='1w' else day.replace(day=1)
        groups.setdefault(key,[]).append(row)
    result=[]
    for start,bars in groups.items():
        end=start+timedelta(days=4) if period=='1w' else start.replace(day=monthrange(start.year,start.month)[1])
        # Timestamp is the last observed session, not an invented Friday/month end.
        # Closed periods may still have data gaps; that is independent of partial.
        while end.weekday()>4: end-=timedelta(days=1)
        def total(key):
            values=[number(row.get(key)) for row in bars]
            return sum(values) if all(value is not None for value in values) else None
        result.append(dict(date=bars[-1]['date'],open=bars[0]['open'],high=max(r['high'] for r in bars),
            low=min(r['low'] for r in bars),close=bars[-1]['close'],volume=total('volume'),amount=total('amount'),
            source=' + '.join(sorted({str(r.get('source','unknown')) for r in bars})),
            period_start=start.isoformat(),period_end=end.isoformat(),source_bar_count=len(bars),
            is_partial=any(r.get('is_partial',False) for r in bars) or now.date()<end or (now.date()==end and now.time()<time(15,15)),
            coverage_note='仅聚合已有交易日；缺失日不补K线，首尾周期可能不完整'))
    return result


def indicator_readings(series: list[dict]) -> list[dict]:
    if not series: return []
    current=series[-1]['indicators']; previous=series[-2]['indicators'] if len(series)>1 else {}
    labels={'macd_dif':'MACD DIF','macd_dea':'MACD DEA','macd_hist':'MACD 柱','kdj_k':'KDJ K','kdj_d':'KDJ D','kdj_j':'KDJ J','rsi14':'RSI14','atr':'ATR14','boll_upper':'布林上轨','boll_lower':'布林下轨'}
    output=[]
    for key in ('ma5','ma10','ma20','ma60','macd_dif','macd_dea','macd_hist','kdj_k','kdj_d','kdj_j','rsi14','atr','boll_upper','boll_lower'):
        value=number(current.get(key)); prior=number(previous.get(key)); change=value-prior if value is not None and prior is not None else None
        required=60 if key=='ma60' else 20 if key.startswith('boll') else 14 if key in ('rsi14','atr') else 9 if key.startswith('kdj') else 26 if key.startswith('macd') else int(key[2:]) if key.startswith('ma') else 1
        ready=len(series)>=required
        if not ready or value is None:
            explanation=f'该周期有效K线不足或字段缺失，需要至少 {required} 根；不是中性或零值。'
            value=prior=change=None
        elif key.startswith('kdj'):
            zone='低位区' if value<20 else '高位区' if value>90 else '中间区'
            explanation=f'{zone}；'+('较上根走高' if change is not None and change>0 else '较上根走低' if change is not None and change<0 else '变化不明显')+'。应结合K/D交叉和趋势；指标数值不是价格支撑位，单值不构成买卖理由。'
        elif key.startswith('rsi'):
            explanation=('超买区，强趋势也可能持续' if value>70 else '超卖区，不等于已经见底' if value<30 else '中间区，结合方向判断强弱')+'；50附近本身没有买卖结论。'
        elif key.startswith('macd'):
            explanation=('零轴上方' if value>0 else '零轴下方' if value<0 else '零轴附近')+'；结合DIF/DEA交叉、柱体增减及价格背离。振荡器轴不是价格轴。'
        elif key.startswith('ma'):
            explanation=('收盘高于均线' if series[-1]['close']>value else '收盘低于均线')+'；均线是动态参考，不保证触线反转。'
        elif key=='atr': explanation='平均真实波幅，量度波动而非涨跌方向；波幅带不保证价格被限制在其中。'
        else: explanation='基于20根均值与波动的通道；触及通道不等于反转，突破可能延续。'
        output.append(dict(key=key,label=labels.get(key,key.upper()),value=value,previous=prior,change=change,
            change_ratio=change/abs(prior) if change is not None and prior not in (None,0) else None,explanation=explanation))
    return output


def chart_studies(rows: list[dict], config: dict, period: str) -> dict:
    series=rows if rows and 'indicators' in rows[-1] else cached_indicator_series(rows,config)
    frame=pd.DataFrame([{**row,**row.get('indicators',{}),'trade_date':row['date'],'atr14':row.get('indicators',{}).get('atr')} for row in series])
    if len(frame) and 'volume' in frame:
        values=pd.to_numeric(frame['volume'],errors='coerce')
        frame['volume']=values
    result=build_support_resistance(frame)
    # Existing deterministic price algorithm is reused, without promoting any
    # cached/manual/aggregated source to actionable or PIT backtest qualification.
    result.update(qualified=False,actionable=False,period=period,readings=indicator_readings(series),
        basis='current_period_price_research',known_at=series[-1]['date'] if series else None)
    for line in (result.get('trend_lines') or []):
        if isinstance(line,dict):
            for endpoint in ('start','end'):
                index=line.get(endpoint+'_index')
                if isinstance(index,int) and 0<=index<len(series): line[endpoint+'_date']=series[index]['date']
    for level in result.get('levels',[]):
        methods=level.get('methods',[])
        groups=[]
        for group,words in {'MA':['MA'],'MACD':['MACD'],'KDJ':['KDJ'],'RSI':['RSI'],'BOLL':['布林'],'ATR':['ATR'],'FIB':['Fibonacci'],'CHAN':['缠论'],'PIVOT':['分形','趋势线','区间','TD9','成交']}.items():
            if any(word in str(methods) for word in words): groups.append(group)
        level['groups']=groups or ['PIVOT']
    return result


def transform_chart(result: dict, period: str, config: dict, limit: int=500, *, now: datetime | None=None) -> dict:
    assessed_at=now or datetime.now(TZ)
    raw_bars=aggregate_bars(result.get('bars',[]),period,now=assessed_at)
    research_source=result.get('research_bars') or result.get('bars',[])
    research_bars=aggregate_bars(research_source,period,now=assessed_at)
    if result.get("history_issue"):
        research_series = [{**bar, "indicators": {}} for bar in research_bars]
        studies = {"levels": [], "readings": [], "qualified": False, "actionable": False, "reason": result["history_issue"]}
    else:
        research_series=(research_bars if period=="1d" and research_bars and "indicators" in research_bars[-1]
                         else cached_indicator_series(research_bars,config)) if research_bars else []
        studies=chart_studies(research_series,config,period)
    research_by_date={bar['date']:bar for bar in research_series}
    raw_overlay_allowed=bool(result.get('raw_overlay_allowed',True)) and all(bar['date'] in research_by_date for bar in raw_bars)
    bars=[{**bar,"indicators":research_by_date[bar['date']].get('indicators',{}) if raw_overlay_allowed else {}}
          for bar in raw_bars]
    research_support=studies
    raw_support=research_support if raw_overlay_allowed else None
    series_id=stable_hash({"base_input_hash":result.get("input_hash"),"interval":period,
                           "research_price_basis_id":result.get("research_price_basis_id"),
                           "indicator_version":result.get("indicator_version"),
                           "chart_contract_version":"chart-read-v1.2.0"})
    studies={**studies,"input_hash":result.get("input_hash"),"series_id":series_id,
             "price_basis_id":result.get("research_price_basis_id"),"interval":period}
    payload = {**result, 'interval': period, 'bars': bars[-limit:],
        'research_bars': research_series[-limit:], 'studies': studies,
        'series_id': series_id, 'computed_at': datetime.now(TZ).isoformat(),
        'core_snapshot_match': result.get('core_snapshot_match') if period == '1d' else None,
        'indicator_basis': f"server_formulas_{period}_on_{result.get('research_price_basis', 'source_price')}",
        'support_resistance': raw_support, 'research_support_resistance': research_support,
        'sr_overlay_allowed': bool(raw_overlay_allowed and studies.get('levels')),
        'research_sr_overlay_allowed': bool(studies.get('levels')),
        'raw_overlay_allowed': raw_overlay_allowed,
        'raw_overlay_reason': result.get('raw_overlay_reason') or (None if raw_overlay_allowed else 'price_basis_mismatch'),
        'basis_transition': bool(result.get('raw_overlay_reason') == 'price_basis_mismatch'),
        'research_cost_overlay_allowed': bool(result.get('research_cost_overlay_allowed')),
        'price_structures': (result.get('price_structures') if period == '1d' else {
            'qualified': False, 'reason': 'interval_unsupported', 'boxes': [], 'actionable': False, 'interval': period}),
        'research_price_structures': (result.get('research_price_structures') if period == '1d' else {
            'qualified': False, 'reason': 'interval_unsupported', 'boxes': [], 'actionable': False, 'interval': period}),
        'actionable': False,
        'indicator_note': '日/周/月K按实际历史OHLC聚合；指标按同一拆分调整研究序列重算。价位为当前研究参考，不是历史当时已知的交易信号。'}
    if payload['basis_transition'] and result.get('indicator_note'):
        payload['indicator_note'] = result['indicator_note']
    return payload
