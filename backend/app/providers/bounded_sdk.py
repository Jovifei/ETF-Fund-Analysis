"""Hard, cross-platform deadlines for public provider calls.

Owned child processes, not unkillable timeout threads. Children return bounded
JSON records and sanitized failure codes, never raw responses or credentials.
No network request is made by constructing a client or opening a workspace GET.
"""
from __future__ import annotations

import importlib
import json
import multiprocessing as mp
import os
import re
from functools import partial

from app.providers.base import CapabilityUnavailable, ProviderError

MAX_BYTES = 8_000_000
TUSHARE_ENDPOINT = 'https://api.tushare.pro'
TUSHARE_APIS = frozenset({'index_daily','etf_basic','fund_basic','fund_daily','rt_etf_k','etf_mins','trade_cal','news','major_news','cctv_news'})
AKSHARE_APIS = frozenset({
    'fund_etf_spot_em','fund_lof_spot_em','fund_etf_hist_em','fund_lof_hist_em','fund_etf_hist_sina',
    'fund_etf_hist_min_em','fund_lof_hist_min_em','fund_etf_category_sina','fund_etf_category_ths',
    'stock_board_industry_name_em','stock_board_industry_summary_ths','stock_board_concept_name_em',
    'stock_sector_spot','stock_board_concept_summary_ths','stock_zh_a_spot_em','stock_zh_a_spot','stock_info_a_code_name','stock_zh_index_daily',
    'stock_zh_index_daily_em','index_zh_a_hist','stock_zh_index_daily_tx','index_us_stock_sina','stock_news_em','stock_info_global_em','stock_info_global_sina',
    'stock_info_global_cls','stock_info_global_ths',
})


class ProviderTimeout(ProviderError):
    pass


def first(row, *keys):
    """None/empty are missing; zero is a real observation."""
    for key in keys:
        value = row.get(key)
        if value is not None and value != '':
            return value
    return None


def _https_query(name, params, token, timeout):
    import httpx
    if not token:
        raise CapabilityUnavailable('credentials_missing')
    fields = params.pop('fields','')
    body = {'api_name':name,'token':token,'params':params,'fields':fields}
    # Never send the token to an HTTP endpoint, redirect, query string or log.
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        with client.stream('POST',TUSHARE_ENDPOINT,json=body) as response:
            if response.status_code != 200:
                raise ProviderError('upstream_http_rejected')
            data=bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data)>MAX_BYTES: raise ProviderError('response_too_large')
    result=json.loads(data)
    if result.get('code') != 0:
        # Use the message only to classify; it may echo a submitted credential.
        text=str(result.get('msg','')).lower()
        if any(w in text for w in ('权限','积分','permission','token')):
            raise CapabilityUnavailable('permission_or_credentials_denied')
        if any(w in text for w in ('频次','频率','每分钟','每小时','rate')):
            raise ProviderError('rate_limited')
        raise ProviderError('upstream_rejected')
    table=result.get('data') or {}
    columns,items=table.get('fields',[]),table.get('items',[])
    if not isinstance(columns,list) or not all(isinstance(c,str) for c in columns) or len(set(columns)) != len(columns) or not isinstance(items,list) or len(items)>20000:
        raise ProviderError('invalid_response_schema')
    if any(not isinstance(row,list) or len(row)!=len(columns) for row in items):
        raise ProviderError('invalid_response_schema')
    return [dict(zip(columns,row)) for row in items]


def _child(conn, module, name, params, token, timeout):
    try:
        # Library prints can expose returned data. Only bounded structured
        # output through the private pipe is used; stderr is not a log channel.
        import contextlib
        with open(os.devnull,'w') as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
            if module=='tushare':
                result=_https_query(name,dict(params),token,timeout)
            else:
                function=getattr(importlib.import_module('akshare'),name,None)
                if not callable(function): raise CapabilityUnavailable('endpoint_unavailable')
                result=function(**params)
            frame = hasattr(result,'to_json')
            if frame:
                result=json.loads(result.to_json(orient='records',date_format='iso',force_ascii=False))
            payload=json.dumps({'ok':True,'records':result,'frame':frame},ensure_ascii=False,allow_nan=False,default=str).encode()
            if len(payload)>MAX_BYTES: raise ProviderError('response_too_large')
    except BaseException as exc:
        allowed={'credentials_missing','permission_or_credentials_denied','rate_limited','upstream_rejected','response_too_large','invalid_response_schema','endpoint_unavailable','upstream_http_rejected'}
        code=str(exc) if str(exc) in allowed else 'provider_failed'
        payload=json.dumps({'ok':False,'code':code,'unsupported':isinstance(exc,CapabilityUnavailable)}).encode()
    try:
        conn.send_bytes(payload)
    finally:
        conn.close()


def bounded_call(module, name, params, *, timeout=20.0, token=None):
    allowed=TUSHARE_APIS if module=='tushare' else AKSHARE_APIS if module=='akshare' else ()
    if name not in allowed: raise CapabilityUnavailable('endpoint_not_allowlisted')
    ctx=mp.get_context('spawn')
    receiver,sender=ctx.Pipe(duplex=False)
    process=ctx.Process(target=_child,args=(sender,module,name,params,token,timeout),daemon=True)
    try:
        process.start();sender.close()
        if not receiver.poll(timeout): raise ProviderTimeout('provider_deadline_exceeded')
        try:
            payload=json.loads(receiver.recv_bytes(MAX_BYTES))
        except (EOFError,OSError,ValueError):
            raise ProviderError('invalid_worker_response') from None
        if not payload['ok']:
            error=CapabilityUnavailable if payload.get('unsupported') else ProviderError
            raise error(payload['code'])
        if payload.get('frame'):
            import pandas as pd
            return pd.DataFrame(payload['records'])
        return payload['records']
    finally:
        sender.close();receiver.close()
        if process.pid is not None:
            process.join(timeout=0.05)
            if process.is_alive(): process.terminate();process.join(timeout=1)
            if process.is_alive(): process.kill();process.join(timeout=1)
            process.close()


class BoundedSDK:
    def __init__(self,module,timeout,token=None):
        self.module,self.timeout,self._token=module,timeout,token
    def __getattr__(self,name):
        allowed=TUSHARE_APIS if self.module=='tushare' else AKSHARE_APIS
        if name not in allowed: raise AttributeError(name)
        return partial(self._call,name)
    def _call(self,name,**kwargs):
        return bounded_call(self.module,name,kwargs,timeout=self.timeout,token=self._token)
