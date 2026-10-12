"""HTTPS-only producer client; bearer credential is never logged or read back."""
import json,os,ssl
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPSHandler,HTTPRedirectHandler
from app.workspace.shadow_bundle import canonical,digest
from app.workspace.shadow_auth import signed_headers

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('sync redirects prohibited')

def upload_bundle(url,bundle,*,opener=None):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path!='/api/shadow/sync':raise ValueError('exact HTTPS sync endpoint required')
    if not isinstance(bundle,dict) or not isinstance(bundle.get('manifest'),dict):raise ValueError('invalid sync bundle')
    expected_bundle_id=digest(bundle['manifest'])
    token=os.environ.get('SHADOW_PRODUCER_TOKEN','')
    if len(token)<32:raise ValueError('producer credential unavailable')
    body=canonical(bundle)
    signing=signed_headers(body,os.environ.get('SHADOW_SIGNING_KEY_ID',''),os.environ.get('SHADOW_SIGNING_SECRET',''))
    request=Request(url,data=body,headers={**signing,'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
    transport=opener or (lambda req,**kwargs:build_opener(HTTPSHandler(context=ssl.create_default_context()),NoRedirect()).open(req,timeout=30))
    with transport(request,timeout=30,context=ssl.create_default_context()) as response:
        status=getattr(response,'status',None)
        if status is None and callable(getattr(response,'getcode',None)):status=response.getcode()
        if status!=200:raise ValueError('invalid sync receipt status')
        body=response.read(4097)
        if len(body)>4096:raise ValueError('invalid sync receipt')
        try:receipt=json.loads(body)
        except (json.JSONDecodeError,UnicodeDecodeError):raise ValueError('invalid sync receipt') from None
        if not isinstance(receipt,dict) or set(receipt)!={'bundle_id'} or receipt['bundle_id']!=expected_bundle_id:raise ValueError('sync receipt bundle mismatch')
        return receipt
