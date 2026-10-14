import pytest
from app.workspace.shadow_bundle import ShadowStore,digest
from app.workspace.shadow_projection import project_chart, validate_public_chart
from test_shadow_bundle import bundle,NOW

@pytest.mark.parametrize('field,value',[('date','0000-invalid'),('open',True),('source',{'api_key':'synthetic-private'})])
def test_chart_scalar_types_reject_nested_or_malformed(tmp_path,field,value):
    data=bundle();bar={'date':'2026-10-11','open':1.0,'high':1.1,'low':0.9,'close':1.0,'source':'mock','indicators':{}};bar[field]=value
    chart=data['blobs']['charts']['510300.SH'];chart['bars']=[bar];chart['research_bars']=[bar.copy()];chart['source_as_of']='2026-10-11'
    data['manifest']['parts']['charts']=digest(data['blobs']['charts'])
    with pytest.raises(ValueError):ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64).publish(data,now=NOW)


@pytest.mark.parametrize('mutation', ['study-number', 'level-number'])
def test_public_chart_rejects_unclosed_nested_types(tmp_path, mutation):
    data=bundle()
    chart=data['blobs']['charts']['510300.SH']
    if mutation=='study-number':
        chart['support_resistance']={'current_price': {'unexpected': 1}}
    elif mutation=='level-number':
        chart['support_resistance']={'levels': [{'price': True}]}
    data['manifest']['parts']['charts']=digest(data['blobs']['charts'])
    with pytest.raises(ValueError):
        ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64).publish(data,now=NOW)


def test_public_projection_preserves_only_typed_trend_lines():
    bar={'date':'2026-10-10','open':1.0,'high':1.1,'low':0.9,'close':1.0,'volume':100,'amount':100,'source':'fixture','indicators':{}}
    line={'label':'support','method':'confirmed_pivot_trendline','start_index':1,'end_index':4,
          'start_price':0.8,'end_price':0.9,'projected_price':1.0,'slope_per_bar':0.025,
          'private_note':'must be removed'}
    projected=project_chart({
        'ts_code':'510300.SH','as_of':NOW.isoformat(),'source_as_of':'2026-10-10','available':True,
        'bars':[bar],'research_bars':[bar],
        'studies':{'trend_lines':[line],'levels':[],'nearest_support':None,'nearest_resistance':None,
                   'current_price':1.0,'atr14':None,'atr_basis':None},
    })
    assert projected['studies']['trend_lines']==[{key:value for key,value in line.items() if key!='private_note'}]
    validate_public_chart(projected)


def test_public_chart_rejects_malformed_trend_line_values(tmp_path):
    data=bundle()
    data['blobs']['charts']['510300.SH']['support_resistance']={'trend_lines':[{
        'label':'support','method':'confirmed_pivot_trendline','start_index':1,'end_index':4,
        'start_price':0.8,'end_price':0.9,'projected_price':True,'slope_per_bar':0.025,
    }]}
    data['manifest']['parts']['charts']=digest(data['blobs']['charts'])
    with pytest.raises(ValueError):
        ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64).publish(data,now=NOW)


@pytest.mark.parametrize('mutation', ['chart-code', 'bad-as-of', 'future-as-of', 'source-date', 'duplicate-date'])
def test_chart_identity_and_dates_are_bound(tmp_path, mutation):
    data=bundle()
    chart=data['blobs']['charts']['510300.SH']
    if mutation=='chart-code':
        chart['ts_code']='510301.SH'
    elif mutation=='bad-as-of':
        chart['as_of']='not-a-timestamp'
    elif mutation=='future-as-of':
        from datetime import timedelta
        chart['as_of']=(NOW+timedelta(minutes=1)).isoformat()
    elif mutation in {'source-date','duplicate-date'}:
        bar={'date':'2026-10-10','open':1.0,'high':1.1,'low':0.9,'close':1.0,'source':'fixture'}
        chart['bars']=[bar,bar.copy()] if mutation=='duplicate-date' else [bar]
        chart['research_bars']=[bar.copy() for _ in chart['bars']]
        chart['source_as_of']='2026-10-09' if mutation=='source-date' else '2026-10-10'
    data['manifest']['parts']['charts']=digest(data['blobs']['charts'])
    with pytest.raises(ValueError):
        ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64).publish(data,now=NOW)


class _ReceiptResponse:
    def __init__(self, payload):
        import json
        self.body=json.dumps(payload).encode()
        self.status=200
    def __enter__(self):return self
    def __exit__(self,*args):return None
    def read(self,size):return self.body[:size]


def _fake_upload(monkeypatch, response):
    from app.workspace.shadow_client import upload_bundle
    monkeypatch.setenv('SHADOW_PRODUCER_TOKEN','x'*32)
    monkeypatch.setenv('SHADOW_SIGNING_KEY_ID','fixture-key')
    monkeypatch.setenv('SHADOW_SIGNING_SECRET','s'*32)
    data=bundle()
    return upload_bundle('https://receiver.example/api/shadow/sync',data,opener=lambda *_args,**_kwargs:response),data


def test_http_200_receipt_with_wrong_bundle_id_is_rejected(monkeypatch):
    from app.workspace.shadow_bundle import digest
    value=bundle()
    wrong='0'*64 if digest(value['manifest'])!='0'*64 else '1'*64
    with pytest.raises(ValueError):
        _fake_upload(monkeypatch,_ReceiptResponse({'bundle_id':wrong}))


def test_http_200_receipt_with_matching_bundle_id_is_accepted(monkeypatch):
    from app.workspace.shadow_bundle import digest
    value=bundle()
    receipt,data=_fake_upload(monkeypatch,_ReceiptResponse({'bundle_id':digest(value['manifest'])}))
    assert data==value
    assert receipt=={'bundle_id':digest(value['manifest'])}

