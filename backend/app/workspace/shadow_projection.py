"""Public daily chart projection and versioned typed validation."""
from datetime import date, datetime, timezone
from math import isfinite
import re
from zoneinfo import ZoneInfo

VALIDATION_VERSION = "shadow-public-validation-v1.1"
MARKET_TZ = ZoneInfo("Asia/Shanghai")
INDICATORS = {"ma5","ma10","ma20","ma30","ma60","macd_dif","macd_dea","macd_hist","kdj_k","kdj_d","kdj_j","rsi6","rsi12","rsi14","td_buy_setup","td_sell_setup","atr","atr_pct","boll_upper","boll_mid","boll_lower"}
BAR = {"date","open","high","low","close","volume","amount","source","indicators"}
LEVEL = {"price","lower","upper","kind","type","methods","groups","strength","category","confirmations","distance_pct","is_estimate","touch_count"}
TREND_LINE = {"label","method","start_index","end_index","start_price","end_price","projected_price","slope_per_bar"}
CHART = {"ts_code","sr_overlay_allowed","research_sr_overlay_allowed","basis_transition","adjust","bars","research_bars","available","source_as_of","as_of","computed_at","actionable","qualification","research_only","interval","unsupported_intervals","indicator_version","indicator_basis","input_hash","series_id","chart_contract_version","display_price_basis","research_price_basis","research_price_basis_id","raw_overlay_allowed","raw_overlay_reason","history_issue","reason","cost_overlay_allowed","research_cost_overlay_allowed","studies","support_resistance","research_support_resistance"}
STUDY = {"levels","nearest_support","nearest_resistance","current_price","atr14","atr_basis","reason","actionable","qualified","qualification","trend_lines"}
CODE_RE = re.compile(r"[0-9]{6}\.(SH|SZ|BJ)")

def numeric(value, *, nullable=False):
    if value is None and nullable:
        return
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise ValueError("invalid public numeric field")
    try:
        finite=isfinite(value)
    except OverflowError:
        finite=False
    if not finite:
        raise ValueError("invalid public numeric field")

def _string(value, *, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value,str):
        raise ValueError("invalid public string field")

def _daily_date(value, *, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value,str):
        raise ValueError("invalid daily bar date")
    try:
        parsed=date.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid daily bar date") from None
    if parsed.isoformat()!=value:
        raise ValueError("invalid daily bar date")
    return parsed

def _chart_time(value):
    if not isinstance(value,str):
        raise ValueError("invalid chart timestamp")
    try:
        parsed=datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid chart timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("chart timezone required")
    return parsed

def _strings(value):
    if not isinstance(value,list) or any(not isinstance(item,str) for item in value):
        raise ValueError("invalid public string list")

def _integer(value):
    if type(value) is not int or value<0:
        raise ValueError("invalid public integer")

def _validate_level(value):
    if not isinstance(value,dict) or set(value)-LEVEL:
        raise ValueError("nonpublic level fields")
    for key in ("price","lower","upper","strength","distance_pct"):
        if key in value:
            numeric(value[key],nullable=key!="price")
    for key in ("kind","type","category"):
        if key in value:
            _string(value[key])
    for key in ("methods","groups"):
        if key in value:
            _strings(value[key])
    for key in ("confirmations","touch_count"):
        if key in value:
            _integer(value[key])
    if "is_estimate" in value and type(value["is_estimate"]) is not bool:
        raise ValueError("invalid public estimate flag")

def _validate_study(value):
    if not isinstance(value,dict) or set(value)-STUDY:
        raise ValueError("nonpublic studies")
    for key in ("current_price","atr14"):
        if key in value:
            numeric(value[key],nullable=key=="atr14")
    for key in ("atr_basis","reason","qualification"):
        if key in value:
            _string(value[key],nullable=key!="qualification")
    for key in ("actionable","qualified"):
        if key in value and value[key] is not False:
            raise ValueError("unsafe public study")
    if "qualification" in value and value["qualification"]!="UNKNOWN":
        raise ValueError("unsafe public study qualification")
    if "levels" in value:
        if not isinstance(value["levels"],list):
            raise ValueError("invalid public levels")
        for item in value["levels"]:
            _validate_level(item)
    for key in ("nearest_support","nearest_resistance"):
        if key in value and value[key] is not None:
            _validate_level(value[key])
    if "trend_lines" in value:
        if not isinstance(value["trend_lines"],list):
            raise ValueError("invalid public trend lines")
        for line in value["trend_lines"]:
            if not isinstance(line,dict) or set(line)!=TREND_LINE:
                raise ValueError("invalid public trend line")
            for key in ("label","method"):
                _string(line[key])
            for key in ("start_index","end_index"):
                _integer(line[key])
            if line["end_index"]<=line["start_index"]:
                raise ValueError("invalid trend line indices")
            for key in ("start_price","end_price","projected_price","slope_per_bar"):
                numeric(line[key])

def levels(value):
    if value is None:
        return None
    if not isinstance(value,dict):
        raise ValueError("invalid public level")
    return {key:item for key,item in value.items() if key in LEVEL}

def studies(value):
    if value is None:
        return None
    if not isinstance(value,dict):
        raise ValueError("invalid public study")
    result={key:item for key,item in value.items() if key in STUDY and key not in {"levels","nearest_support","nearest_resistance","trend_lines"}}
    raw=value.get("levels",[])
    if not isinstance(raw,list):
        raise ValueError("invalid public levels")
    result["levels"]=[levels(item) for item in raw]
    for key in ("nearest_support","nearest_resistance"):
        result[key]=levels(value.get(key))
    lines=value.get("trend_lines",[])
    if not isinstance(lines,list) or any(not isinstance(line,dict) for line in lines):
        raise ValueError("invalid public trend lines")
    result["trend_lines"]=[{key:item for key,item in line.items() if key in TREND_LINE} for line in lines]
    result.update(actionable=False,qualified=False,qualification="UNKNOWN")
    return result

def project_chart(source):
    if not isinstance(source,dict):
        raise ValueError("invalid chart source")
    result={key:value for key,value in source.items() if key in CHART and key not in {"bars","research_bars","studies","support_resistance","research_support_resistance"}}
    for key in ("bars","research_bars"):
        rows=source.get(key,[])
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
            raise ValueError("invalid public bars")
        result[key]=[]
        for row in rows:
            indicators=row.get("indicators") or {}
            if not isinstance(indicators,dict):
                raise ValueError("invalid public indicators")
            bar={k:v for k,v in row.items() if k in BAR and k!="indicators"}
            bar["indicators"]={k:v for k,v in indicators.items() if k in INDICATORS}
            result[key].append(bar)
    for key in ("studies","support_resistance","research_support_resistance"):
        result[key]=studies(source.get(key))
    result.update(interval="1d",unsupported_intervals=["1w","1mo","5m","15m"],qualification="UNKNOWN",research_only=True,actionable=False,cost_overlay_allowed=False,research_cost_overlay_allowed=False)
    return result

def validate_public_chart(chart, *, code=None, generated_at=None, partial=False):
    """Sparse legacy charts inherit identity/cutoff from their enclosing manifest."""
    if not isinstance(chart,dict) or set(chart)-CHART:
        raise ValueError("nonpublic chart fields")
    if code is not None and (not isinstance(code,str) or not CODE_RE.fullmatch(code)):
        raise ValueError("invalid chart universe code")
    if "ts_code" in chart:
        if not isinstance(chart["ts_code"],str) or not CODE_RE.fullmatch(chart["ts_code"]):
            raise ValueError("invalid chart code")
        if code is not None and chart["ts_code"]!=code:
            raise ValueError("chart code mismatch")
    if chart.get("interval","1d")!="1d":
        raise ValueError("chart scope violation")
    for key,expected in (("actionable",False),("research_only",True),("cost_overlay_allowed",False),("research_cost_overlay_allowed",False)):
        if key in chart and chart[key] is not expected:
            raise ValueError("unsafe public chart flag")
    if "qualification" in chart and chart["qualification"]!="UNKNOWN":
        raise ValueError("unsafe public chart qualification")
    for key in ("available","sr_overlay_allowed","research_sr_overlay_allowed","basis_transition","raw_overlay_allowed"):
        if key in chart and type(chart[key]) is not bool:
            raise ValueError("invalid public chart flag")
    for key in ("adjust","indicator_version","indicator_basis","input_hash","series_id","chart_contract_version","display_price_basis","research_price_basis","research_price_basis_id","raw_overlay_reason","history_issue","reason"):
        if key in chart:
            _string(chart[key],nullable=True)
    if "unsupported_intervals" in chart:
        _strings(chart["unsupported_intervals"])
    as_of=_chart_time(chart["as_of"]) if "as_of" in chart else generated_at
    if generated_at is not None and as_of is not None and as_of>generated_at:
        raise ValueError("chart as_of after bundle generated_at")
    if "computed_at" in chart and chart["computed_at"] is not None:
        _chart_time(chart["computed_at"])
    cutoff=as_of.astimezone(MARKET_TZ).date() if as_of is not None else None
    source=_daily_date(chart["source_as_of"],nullable=True) if "source_as_of" in chart else None
    if source is not None and cutoff is not None and source>cutoff:
        raise ValueError("future chart source date")
    series={}
    for key in ("bars","research_bars"):
        rows=chart.get(key,[])
        if not isinstance(rows,list):
            raise ValueError("invalid public bars")
        dates=[]
        for bar in rows:
            if not isinstance(bar,dict) or set(bar)-BAR:
                raise ValueError("nonpublic bar fields")
            day=_daily_date(bar.get("date"))
            if cutoff is not None and day>cutoff:
                raise ValueError("future chart bar")
            if dates and day<=dates[-1]:
                raise ValueError("duplicate or out-of-order chart date")
            dates.append(day)
            for field in ("open","high","low","close"):
                if not partial or field in bar:
                    numeric(bar.get(field))
            for field in ("volume","amount"):
                numeric(bar.get(field),nullable=True)
            if "source" in bar:
                _string(bar["source"],nullable=True)
            indicators=bar.get("indicators",{})
            if not isinstance(indicators,dict) or set(indicators)-INDICATORS:
                raise ValueError("nonpublic indicator fields")
            for value in indicators.values():
                numeric(value,nullable=True)
        series[key]=dates
    if series["bars"] and series["research_bars"] and series["bars"]!=series["research_bars"]:
        raise ValueError("chart series dates mismatch")
    dates=series["bars"] or series["research_bars"]
    if dates and "source_as_of" in chart and source!=dates[-1]:
        raise ValueError("chart source_as_of does not match bars")
    for key in ("studies","support_resistance","research_support_resistance"):
        if chart.get(key) is not None:
            _validate_study(chart[key])
