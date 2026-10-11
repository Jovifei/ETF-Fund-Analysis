from datetime import datetime,timezone,timedelta
import pytest
from app.workspace.shadow_auth import signed_headers,verify_request
NOW=datetime(2026,10,11,12,0,tzinfo=timezone.utc)
def test_sign_verify_replay_rotation_body_and_time(tmp_path):
    body=b'{"public":true}';headers=signed_headers(body,'key-1','s'*32,now=NOW,nonce='a'*32)
    verify_request(body,headers,tmp_path,'key-1','s'*32,now=NOW)
    with pytest.raises(ValueError):verify_request(body,headers,tmp_path,'key-1','s'*32,now=NOW)
    for payload,key,secret,time in [(body+b' ','key-1','s'*32,NOW),(body,'key-2','s'*32,NOW),(body,'key-1','t'*32,NOW),(body,'key-1','s'*32,NOW+timedelta(seconds=121))]:
        with pytest.raises(ValueError):verify_request(payload,headers,tmp_path,key,secret,now=time)

def test_nonce_budget_and_malformed_timestamp(tmp_path):
    headers=signed_headers(b'{}','key-1','s'*32,now=NOW,nonce='a'*32)
    verify_request(b'{}',headers,tmp_path,'key-1','s'*32,now=NOW,max_nonces=1)
    second=signed_headers(b'{}','key-1','s'*32,now=NOW,nonce='b'*32)
    with pytest.raises(ValueError):verify_request(b'{}',second,tmp_path,'key-1','s'*32,now=NOW,max_nonces=1)
    second['X-Shadow-Timestamp']='2026-10-11T12:00:00'
    with pytest.raises(ValueError):verify_request(b'{}',second,tmp_path,'key-1','s'*32,now=NOW)

def test_nonce_ttl_releases_capacity_but_future_signatures_reject(tmp_path):
    original=signed_headers(b'{}','key-1','s'*32,now=NOW,nonce='a'*32)
    verify_request(b'{}',original,tmp_path,'key-1','s'*32,now=NOW,max_nonces=1)
    later=NOW+timedelta(seconds=300)
    fresh=signed_headers(b'{}','key-1','s'*32,now=later,nonce='b'*32)
    verify_request(b'{}',fresh,tmp_path,'key-1','s'*32,now=later,max_nonces=1)
    assert len([p for p in (tmp_path/'nonces').iterdir() if len(p.name)==64])==1
    future=signed_headers(b'{}','key-1','s'*32,now=later+timedelta(seconds=121),nonce='c'*32)
    with pytest.raises(ValueError):verify_request(b'{}',future,tmp_path,'key-1','s'*32,now=later)
