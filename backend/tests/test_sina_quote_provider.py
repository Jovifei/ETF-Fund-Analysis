from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from app.core.config import Settings
from app.models import Instrument, QuoteSnapshot
from app.providers.base import ProviderError
from app.providers.composite import CompositeProvider
from app.providers.factory import build_provider
from app.providers.sina import SinaProvider
from app.services.market_service import MarketService
from app.workspace.read_model import quote_view
from sqlalchemy import select


class OversizedQuoteStream(httpx.SyncByteStream):
    def __init__(self):
        self.chunks_read = 0

    def __iter__(self):
        for chunk in (b'x' * 600_000, b'y' * 600_000, b'z'):
            self.chunks_read += 1
            yield chunk

    def close(self):
        pass


def test_public_composite_registers_sina_as_quote_fallback():
    settings = Settings(
        _env_file=None,
        app_env='test',
        market_provider='public_composite',
        tushare_token='',
        ftshare_enabled=False,
    )
    provider = build_provider(settings)
    try:
        assert 'sina' in [item.name for item in provider.providers]
    finally:
        provider.close()


def _quote_payload(code: str, *, source_time: str = '2026-09-24,10:00:00') -> str:
    prefix, symbol = ('sh' if code.endswith('.SH') else 'sz'), code.split('.')[0]
    fields = ['ETF'] + ['2.10', '1.90', '2.10', '2.20', '1.80'] + ['0'] * 24 + source_time.split(',')
    return f'var hq_str_{prefix}{symbol}="{",".join(fields)}";'


def test_sina_quote_parser_uses_source_time_and_leaves_unqualified_volume_empty():
    from app.providers.sina import SinaProvider

    request_seen = []
    body = '\n'.join((_quote_payload('512480.SH'), _quote_payload('159915.SZ')))

    def respond(request):
        request_seen.append(request)
        return httpx.Response(200, content=body.encode('gb18030'))

    client = httpx.Client(transport=httpx.MockTransport(respond))
    provider = SinaProvider(client=client)
    try:
        rows = provider.fetch_spot_quotes(['512480.SH', '159915.SZ'])
    finally:
        client.close()

    assert [row.ts_code for row in rows] == ['512480.SH', '159915.SZ']
    assert all(row.quote_time == datetime(2026, 9, 24, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai')) for row in rows)
    assert all(row.is_realtime and row.degraded_reason is None for row in rows)
    assert all(row.volume is None and row.amount is None for row in rows)
    assert all(row.source == 'sina:hq_sinajs:v1' for row in rows)
    assert len(request_seen) == 1 and str(request_seen[0].url).startswith('https://')
    assert request_seen[0].url.path == '/list=sh512480,sz159915'
    assert request_seen[0].url.query == b''


def test_sina_missing_or_bad_source_time_stays_degraded():
    from app.providers.sina import SinaProvider

    body = _quote_payload('512480.SH', source_time=',')
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body.encode())))
    provider = SinaProvider(client=client)
    try:
        rows = provider.fetch_spot_quotes(['512480.SH'])
    finally:
        client.close()
    assert len(rows) == 1
    assert rows[0].is_realtime is False
    assert rows[0].degraded_reason == 'source_timestamp_missing_observed_at_fetch'
    assert rows[0].volume is None and rows[0].amount is None


def test_sina_http_error_does_not_expose_response_body():
    from app.providers.sina import SinaProvider

    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(403, content=b'private token or user data')
    ))
    provider = SinaProvider(client=client)
    try:
        with pytest.raises(ProviderError, match='sina_quote_upstream_rejected') as error:
            provider.fetch_spot_quotes(['512480.SH'])
    finally:
        client.close()
    assert 'private token' not in str(error.value)


def test_sina_response_limit_stops_streaming_before_reading_the_rest():
    stream = OversizedQuoteStream()
    client = httpx.Client(transport=httpx.MockTransport(
        lambda _request: httpx.Response(200, stream=stream)
    ))
    provider = SinaProvider(client=client)
    try:
        with pytest.raises(ProviderError, match='sina_quote_response_too_large'):
            provider.fetch_spot_quotes(['512480.SH'])
    finally:
        client.close()
    assert stream.chunks_read == 2


def test_sina_quote_flows_to_display_without_qualifying_decision(db_session):
    code = '998001.SH'
    settings = Settings(_env_file=None, app_env='test', market_provider='public_composite')
    observed_at = datetime.now(ZoneInfo('Asia/Shanghai'))
    body = _quote_payload(code, source_time=observed_at.strftime('%Y-%m-%d,%H:%M:%S'))
    client = httpx.Client(transport=httpx.MockTransport(
        lambda _request: httpx.Response(200, content=body.encode('gb18030'))
    ))
    provider = CompositeProvider([SinaProvider(settings, client=client)])
    db_session.add(Instrument(ts_code=code, symbol='998001', name='fixture ETF', kind='ETF', enabled=True))
    db_session.flush()

    try:
        result = MarketService(provider, settings, persist_provider_audits=False).refresh_quotes(
            db_session, codes=[code], run_id='sina-quote-flow-test'
        )
    finally:
        client.close()

    stored = db_session.scalar(
        select(QuoteSnapshot).join(Instrument).where(Instrument.ts_code == code)
    )
    assert result['received'] == result['realtime'] == 1
    assert stored is not None
    assert stored.timestamp_verified is True
    assert stored.volume is None and stored.amount is None
    view = quote_view(stored, settings)
    assert view['source'] == 'sina:hq_sinajs:v1'
    assert view['status'] == 'observed' and view['is_realtime'] is True
    assert view['actionable'] is False
