"""Index OHLC adapters. No ETF proxy or fabricated OHLC from point snapshots."""
from datetime import datetime

from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.bounded_sdk import first
from app.providers.types import BarRecord
from app.utils.numbers import finite_or_none

INDEX_CODES = {
    'sh000001': '000001.SH',
    'sh000300': '000300.SH',
    'sh000985': '000985.CSI',
}


def decode(rows, symbol, start, end, source, *, tushare=False):
    output = []
    for row in rows:
        if tushare and row.get('ts_code') != INDEX_CODES[symbol]:
            raise ProviderError('index_identity_mismatch')
        raw = str(first(row, 'trade_date', 'date', '日期'))[:10]
        try:
            day = datetime.strptime(raw, '%Y%m%d' if len(raw) == 8 else '%Y-%m-%d').date()
        except ValueError:
            raise ProviderError('index_date_invalid') from None
        if not start <= day <= end:
            continue
        values = [finite_or_none(first(row, key, cn)) for key, cn in
                  [('open','开盘'),('high','最高'),('low','最低'),('close','收盘')]]
        if any(v is None or isinstance(v, bool) or v <= 0 for v in values):
            raise ProviderError('index_ohlc_missing')
        vol, amount = finite_or_none(row.get('vol')), finite_or_none(row.get('amount'))
        # AKShare index volume units vary by endpoint; don't guess. It does not
        # prevent rendering real OHLC. Tushare index_daily documents hand/1000 CNY.
        output.append(BarRecord(ts_code=symbol, trade_date=day, open=values[0],
            high=values[1], low=values[2], close=values[3],
            volume=vol*100 if tushare and vol is not None else None,
            amount=amount*1000 if tushare and amount is not None else None,
            source=source, adjust='none'))
    return output


def akshare_index(provider, symbol, start, end):
    if symbol not in INDEX_CODES:
        raise CapabilityUnavailable('index_not_supported')
    # Eastmoney's A-share index history endpoint uses the bare index code and
    # returns full OHLC.  Keep it ahead of the older Sina endpoint, which can
    # return a truncated historical series for 000985.
    attempts = [
        ('index_zh_a_hist', {'symbol': INDEX_CODES[symbol].split('.')[0], 'period': 'daily',
            'start_date': start.strftime('%Y%m%d'), 'end_date': end.strftime('%Y%m%d'),
            'source': 'akshare:index:zh-a-v103'}),
        ('stock_zh_index_daily_em', {'symbol': 'csi000985' if symbol=='sh000985' else symbol,
            'start_date':start.strftime('%Y%m%d'), 'end_date':end.strftime('%Y%m%d')}),
        ('stock_zh_index_daily_tx', {'symbol': symbol, 'start_date': start.strftime('%Y%m%d'),
            'end_date': end.strftime('%Y%m%d')}),
        ('stock_zh_index_daily', {'symbol':symbol}),
    ]
    for name, params in attempts:
        try:
            source = params.pop('source', {
                'index_zh_a_hist': 'akshare:index:zh-a-v103',
                'stock_zh_index_daily_em': 'akshare:index:em-v103',
                'stock_zh_index_daily_tx': 'akshare:index:tx-v103',
                'stock_zh_index_daily': 'akshare:index:sina-v103',
            }[name])
            frame = getattr(provider.ak, name)(**params)
            rows = provider._records(frame)
            if len(rows) > 20000:
                raise ProviderError('index_history_too_large')
            result = decode(rows, symbol, start, end, source)
            if result:
                return result
        except (Exception,):
            # Raw upstream errors can contain credentials/URLs. The outer
            # Composite/Task audit keeps a sanitized failure classification.
            continue
    raise CapabilityUnavailable('index_history_unavailable')


def tushare_index(provider, symbol, start, end):
    if symbol not in INDEX_CODES:
        raise CapabilityUnavailable('index_not_supported')
    frame = provider.pro.index_daily(ts_code=INDEX_CODES[symbol],
        start_date=start.strftime('%Y%m%d'),end_date=end.strftime('%Y%m%d'),
        fields='ts_code,trade_date,open,high,low,close,vol,amount')
    rows = provider._records(frame)
    if len(rows) > 20000:
        raise ProviderError('index_history_too_large')
    return decode(rows,symbol,start,end,'tushare:index:v103',tushare=True)
