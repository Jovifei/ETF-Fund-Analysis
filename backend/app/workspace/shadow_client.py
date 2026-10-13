"""HTTPS-only producer client; bearer credential is never logged or read back."""
import json,os,ssl
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPSHandler,HTTPRedirectHandler
from app.workspace.shadow_bundle import canonical
from app.workspace.shadow_auth import signed_headers

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('sync redirects prohibited')

def upload_bundle(url,bundle,*,opener=None,compress=True):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path!='/api/shadow/sync':raise ValueError('exact HTTPS sync endpoint required')
    token=os.environ.get('SHADOW_PRODUCER_TOKEN','')
    if len(token)<32:raise ValueError('producer credential unavailable')
    body=canonical(bundle)
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
    if compress:
        import gzip
        body=gzip.compress(body)
        headers['Content-Encoding']='gzip'
    signing=signed_headers(body,os.environ.get('SHADOW_SIGNING_KEY_ID',''),os.environ.get('SHADOW_SIGNING_SECRET',''))
    headers.update(signing)
    request=Request(url,data=body,headers=headers,method='POST')
    transport=opener or (lambda req,**kwargs:build_opener(HTTPSHandler(context=ssl.create_default_context()),NoRedirect()).open(req,timeout=60))
    with transport(request,timeout=60,context=ssl.create_default_context()) as response:
        body=response.read(4097)
        if len(body)>4096:raise ValueError('invalid sync receipt')
        return json.loads(body)
