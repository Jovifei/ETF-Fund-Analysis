import pytest
from app.workspace.shadow_bundle import ShadowStore,digest
from test_shadow_bundle import bundle,NOW

@pytest.mark.parametrize('field,value',[('date','0000-invalid'),('open',True),('source',{'api_key':'synthetic-private'})])
def test_chart_scalar_types_reject_nested_or_malformed(tmp_path,field,value):
    data=bundle();bar={'date':'2026-10-11','open':1.0,'high':1.1,'low':0.9,'close':1.0,'source':'mock'};bar[field]=value;data['blobs']['charts']['510300.SH']['bars']=[bar]
    data['manifest']['parts']['charts']=digest(data['blobs']['charts'])
    with pytest.raises(ValueError):ShadowStore(tmp_path,code_sha='a'*40,config_hash='b'*64).publish(data,now=NOW)

