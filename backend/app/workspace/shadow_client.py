"""HTTPS-only producer client; bearer credential is never logged or read back."""
import json,os,ssl
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPSHandler,HTTPRedirectHandler
from app.workspace.shadow_bundle import canonical

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('sync redirects prohibited')

def upload_bundle(url,bundle,*,opener=None):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path!='/api/shadow/sync':raise ValueError('exact HTTPS sync endpoint required')
    token=os.environ.get('SHADOW_PRODUCER_TOKEN','')
    if len(token)<32:raise ValueError('producer credential unavailable')
    request=Request(url,data=canonical(bundle),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
    transport=opener or (lambda req,**kwargs:build_opener(HTTPSHandler(context=ssl.create_default_context()),NoRedirect()).open(req,timeout=30))
    with transport(request,timeout=30,context=ssl.create_default_context()) as response:
        body=response.read(4097)
        if len(body)>4096:raise ValueError('invalid sync receipt')
        return json.loads(body)
