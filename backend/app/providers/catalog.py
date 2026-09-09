"""Exchange-listed ETF/LOF discovery, independent from the calculation pool.

Identity comes from a dedicated category/ETF endpoint, not an industry list.
Read-side search never invokes this module. Every source call uses the existing
bounded SDK and composite trace; fallback does not imply complete coverage.
"""
from __future__ import annotations

import re
from app.providers.bounded_sdk import first
from app.utils.numbers import finite_or_none
from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.types import InstrumentRecord


class CatalogRows(list):
    def __init__(self, rows=(), *, coverage=None):
        super().__init__(rows)
        self.coverage = coverage or {}


def _identity(raw):
    value = str(raw or '').strip().upper()
    if re.fullmatch(r'(SH|SZ)\d{6}', value):
        value = value[2:] + '.' + value[:2]
    if re.fullmatch(r'[15]\d{5}', value):
        value += '.SH' if value.startswith('5') else '.SZ'
    return value if re.fullmatch(r'(5\d{5}\.SH|1\d{5}\.SZ)', value) else None


def _record(raw, title, kind, source, **metadata):
    code = _identity(raw)
    title = str(title or '').strip()
    if not code or not title or title.lower() in {'nan', 'none', 'null'}:
        return None
    return InstrumentRecord(ts_code=code, symbol=code[:6], name=title[:128], kind=kind,
        exchange=code[-2:], enabled=False,
        metadata={'catalog_source':source, 'catalog_only':True, **metadata})


def _composite_catalog(provider):
    selected, coverage, partials = {}, {}, {}

    def attempt(child):
        rows = catalog_records(child)
        for row in rows:
            selected.setdefault(row.ts_code, row)
        for kind, detail in getattr(rows, 'coverage', {}).items():
            if kind not in coverage or detail.get('source'):
                coverage[kind] = detail
        result = CatalogRows(sorted(selected.values(), key=lambda row: row.ts_code), coverage=dict(coverage))
        if not getattr(rows, 'coverage', {}) or ((rows.coverage.get('ETF') or {}).get('source') and (rows.coverage.get('ETF') or {}).get('status') != 'small_sample'):
            return result
        # A few names containing ETF are not a category catalog. Preserve the
        # useful rows, but continue the existing audited provider fallback.
        partials[child.name] = len(rows)
        raise CapabilityUnavailable('ETF category catalog missing')

    try:
        return provider._invoke('list_etf_catalog', attempt)
    except ProviderError:
        if not selected:
            raise
        return CatalogRows(sorted(selected.values(), key=lambda row: row.ts_code), coverage=coverage)
    finally:
        for trace in provider.last_trace:
            if trace.provider in partials:
                trace.status = 'partial'
                trace.record_count = partials[trace.provider]
                trace.reason = 'ETF_category_missing_name_fallback_only'


def catalog_records(provider) -> list[InstrumentRecord]:
    name = getattr(provider, 'name', '')
    if name == 'composite':
        return _composite_catalog(provider)
    if name in {'mock', 'ftshare'}:
        return provider.list_instruments()
    result, coverage = [], {}
    if name == 'akshare':
        for kind, primary, category in [('ETF','fund_etf_spot_em','ETF基金'),('LOF','fund_lof_spot_em','LOF基金')]:
            errors = []
            for function, params in [(primary,{}),('fund_etf_category_sina',{'symbol':category}),('fund_etf_category_ths',{'symbol':kind,'date':''})]:
                try:
                    rows = provider._records(getattr(provider.ak,function)(**params))
                    parsed = [_record(first(row,'代码','基金代码'), first(row,'名称','基金简称','基金名称','name'), kind, f'akshare:{function}', market_cap_cny=finite_or_none(row.get('总市值')), turnover_cny=finite_or_none(row.get('成交额')), catalog_as_of=str(first(row,'数据日期','最新-交易日','查询日期') or ''), scale_basis='market_cap_not_NAV_AUM') for row in rows]
                    parsed = [row for row in parsed if row is not None]
                    if not parsed:
                        raise ProviderError('empty_catalog_category')
                    result.extend(parsed)
                    coverage[kind] = {'source':f'akshare:{function}', 'count':len(parsed), 'fallback':function!=primary, 'status':'observed' if len(parsed)>=(100 if kind=='ETF' else 25) else 'small_sample', 'attempt_errors':list(errors)}
                    if len(parsed)>=(100 if kind=='ETF' else 25):
                        break
                except Exception as exc:
                    errors.append(type(exc).__name__)
            else:
                if kind not in coverage:
                    coverage[kind] = {'source':None, 'count':0, 'errors':errors}
                else:
                    coverage[kind]['attempt_errors'] = errors
    elif name == 'tushare':
        # Dedicated endpoint includes funds whose short names contain no "ETF".
        try:
            rows = provider._records(provider.pro.etf_basic(list_status='L'))
            parsed = [_record(row.get('ts_code'), row.get('extname') or row.get('csname') or row.get('cname'), 'ETF', 'tushare:etf_basic', list_date=row.get('list_date'), index_name=row.get('index_name')) for row in rows]
            parsed = [row for row in parsed if row is not None]
            result.extend(parsed)
            coverage['ETF'] = {'source':'tushare:etf_basic' if parsed else None,'count':len(parsed)}
        except Exception as exc:
            coverage['ETF'] = {'source':None,'count':0,'errors':[type(exc).__name__]}
        try:
            rows = provider._records(provider.pro.fund_basic(market='E',status='L'))
            existing = {row.ts_code for row in result}
            added = 0
            for row in rows:
                title = str(row.get('name') or '')
                kind = 'LOF' if 'LOF' in title.upper() else 'ETF' if 'ETF' in title.upper() and '联接' not in title else None
                if not kind or _identity(row.get('ts_code')) in existing:
                    continue
                item = _record(row.get('ts_code'),title,kind,'tushare:fund_basic:E:L', classification='name_fallback',list_date=row.get('list_date'))
                if item:
                    result.append(item);added+=1
            coverage['fund_basic'] = {'source':'tushare:fund_basic:E:L','added':added,'classification':'name_fallback_partial'}
        except Exception as exc:
            coverage['fund_basic'] = {'source':None,'count':0,'errors':[type(exc).__name__]}
    else:
        raise CapabilityUnavailable('ETF catalog not supported')
    if not result:
        raise ProviderError('ETF catalog returned no usable records')
    if len(result) > 10000:
        raise ProviderError('ETF catalog exceeds safety bound')
    seen = {}
    for row in result:
        if row.ts_code in seen:
            if seen[row.ts_code].kind != row.kind:
                raise ProviderError('ETF catalog contains conflicting identities')
            # Same exchange code, different provider short names: retain first
            # identity plus aliases. A spelling difference must not lose a catalog.
            existing=seen[row.ts_code]
            aliases=set(existing.metadata.get('name_aliases', []))
            aliases.add(row.name)
            existing.metadata['name_aliases']=sorted(aliases)[:8]
            continue
        seen[row.ts_code] = row
    return CatalogRows(sorted(seen.values(),key=lambda item:item.ts_code), coverage=coverage)
