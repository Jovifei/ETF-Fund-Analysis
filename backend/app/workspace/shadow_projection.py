"""Explicit public daily-chart projection; private/cost overlays never cross sync."""
from datetime import date
from math import isfinite

def numeric(value, *, nullable=False):
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError('invalid public numeric field')

INDICATORS={'ma5','ma10','ma20','ma30','ma60','macd_dif','macd_dea','macd_hist','kdj_k','kdj_d','kdj_j','rsi6','rsi12','rsi14','td_buy_setup','td_sell_setup','atr','atr_pct','boll_upper','boll_mid','boll_lower'}
BAR={'date','open','high','low','close','volume','amount','source','indicators'}
LEVEL={'price','lower','upper','kind','type','methods','groups','strength','category','confirmations','distance_pct','is_estimate','touch_count'}
CHART={'ts_code','sr_overlay_allowed','research_sr_overlay_allowed','basis_transition','adjust','bars','research_bars','available','source_as_of','as_of','computed_at','actionable','qualification','research_only','interval','unsupported_intervals','indicator_version','indicator_basis','input_hash','series_id','chart_contract_version','display_price_basis','research_price_basis','research_price_basis_id','raw_overlay_allowed','raw_overlay_reason','history_issue','reason','cost_overlay_allowed','research_cost_overlay_allowed','studies','support_resistance','research_support_resistance'}
STUDY={'levels','nearest_support','nearest_resistance','current_price','atr14','atr_basis','reason','actionable','qualified','qualification'}
def levels(value):
    return {key:item for key,item in value.items() if key in LEVEL} if isinstance(value,dict) else None
def studies(value):
    if not isinstance(value,dict):return None
    result={key:item for key,item in value.items() if key in STUDY and key not in {'levels','nearest_support','nearest_resistance'}}
    result['levels']=[levels(item) for item in value.get('levels',[]) if isinstance(item,dict)]
    for key in ('nearest_support','nearest_resistance'):result[key]=levels(value.get(key))
    result.update(actionable=False,qualified=False,qualification='UNKNOWN')
    return result
def project_chart(source):
    result={key:value for key,value in source.items() if key in CHART and key not in {'bars','research_bars','studies','support_resistance','research_support_resistance'}}
    for key in ('bars','research_bars'):
        result[key]=[]
        for row in source.get(key,[]):
            bar={k:v for k,v in row.items() if k in BAR and k!='indicators'}
            bar['indicators']={k:v for k,v in (row.get('indicators') or {}).items() if k in INDICATORS}
            result[key].append(bar)
    for key in ('studies','support_resistance','research_support_resistance'):result[key]=studies(source.get(key))
    result.update(interval='1d',unsupported_intervals=['1w','1mo','5m','15m'],qualification='UNKNOWN',research_only=True,actionable=False,cost_overlay_allowed=False,research_cost_overlay_allowed=False)
    return result

def validate_public_chart(chart):
    if not isinstance(chart,dict) or set(chart)-CHART:raise ValueError('nonpublic chart fields')
    if chart.get('interval','1d')!='1d' or chart.get('cost_overlay_allowed',False) is not False or chart.get('research_cost_overlay_allowed',False) is not False:raise ValueError('chart scope violation')
    for key in ('bars','research_bars'):
        for bar in chart.get(key,[]):
            if not isinstance(bar,dict) or set(bar)-BAR or not isinstance(bar.get('indicators',{}),dict) or set(bar.get('indicators',{}))-INDICATORS:raise ValueError('nonpublic bar fields')
            try:
                if not isinstance(bar.get('date'), str) or date.fromisoformat(bar['date']).isoformat() != bar['date']:
                    raise ValueError('invalid daily bar date')
            except (ValueError, TypeError):
                raise ValueError('invalid daily bar date') from None
            for field in ('open', 'high', 'low', 'close'):
                numeric(bar.get(field))
            for field in ('volume', 'amount'):
                numeric(bar.get(field), nullable=True)
            if bar.get('source') is not None and not isinstance(bar['source'], str):
                raise ValueError('invalid public source')
            for value in bar.get('indicators', {}).values():
                numeric(value, nullable=True)
    for key in ('studies','support_resistance','research_support_resistance'):
        value=chart.get(key)
        if value is None:continue
        if not isinstance(value,dict) or set(value)-STUDY:raise ValueError('nonpublic studies')
        for level in [*value.get('levels',[]),value.get('nearest_support'),value.get('nearest_resistance')]:
            if level is not None and (not isinstance(level,dict) or set(level)-LEVEL):raise ValueError('nonpublic level fields')
