"""Versioned HTTPS producer delivery; receipt identity is independent of compression."""
import json, os, ssl
from datetime import datetime
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from app.workspace.shadow_bundle import canonical, digest
from app.workspace.shadow_auth import signed_headers

RECEIPT_VALIDATION_VERSION = "shadow-receipt-validation-v1.1-v2.1"

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError("sync redirects prohibited")

def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate sync receipt field")
        result[key]=value
    return result

def _validate_receipt(receipt,manifest,contract):
    if not isinstance(receipt,dict) or receipt.get("bundle_id")!=digest(manifest):
        raise ValueError("sync receipt bundle mismatch")
    allowed={"bundle_id"} if contract=="shadow-display-v1" else {"bundle_id","manifest_hash","status","sequence","received_at"}
    if set(receipt)!=allowed:
        raise ValueError("invalid sync receipt fields")
    if contract=="local-display-v2":
        if receipt["manifest_hash"]!=digest(manifest):
            raise ValueError("sync receipt manifest mismatch")
        if type(receipt["sequence"]) is not int or type(manifest.get("sequence")) is not int or receipt["sequence"]<1 or receipt["sequence"]!=manifest["sequence"]:
            raise ValueError("sync receipt sequence mismatch")
        if not isinstance(receipt["status"],str) or receipt["status"] not in {"accepted","already_accepted"}:
            raise ValueError("invalid sync receipt outcome")
        try:
            time=datetime.fromisoformat(receipt["received_at"])
        except (TypeError,ValueError):
            raise ValueError("invalid sync receipt timestamp") from None
        if time.tzinfo is None or time.utcoffset() is None:
            raise ValueError("sync receipt timezone required")
    return receipt

def upload_bundle(url,bundle,*,opener=None,compress=True):
    parsed=urlsplit(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path!="/api/shadow/sync":
        raise ValueError("exact HTTPS sync endpoint required")
    if not isinstance(bundle,dict) or not isinstance(bundle.get("manifest"),dict):
        raise ValueError("invalid sync manifest")
    manifest=bundle["manifest"]
    contract=manifest.get("contract_version") or manifest.get("contract")
    if not isinstance(contract,str) or contract not in {"shadow-display-v1","local-display-v2"}:
        raise ValueError("unsupported sync receipt contract")
    token=os.environ.get("SHADOW_PRODUCER_TOKEN","")
    if len(token)<32:
        raise ValueError("producer credential unavailable")
    body=canonical(bundle)
    headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"}
    if compress:
        import gzip
        body=gzip.compress(body)
        headers["Content-Encoding"]="gzip"
    headers.update(signed_headers(body,os.environ.get("SHADOW_SIGNING_KEY_ID",""),os.environ.get("SHADOW_SIGNING_SECRET","")))
    request=Request(url,data=body,headers=headers,method="POST")
    transport=opener or (lambda req,**kwargs:build_opener(HTTPSHandler(context=ssl.create_default_context()),NoRedirect()).open(req,timeout=60))
    with transport(request,timeout=60,context=ssl.create_default_context()) as response:
        status=getattr(response,"status",None)
        if status is None and callable(getattr(response,"getcode",None)):
            status=response.getcode()
        if not isinstance(status,int) or isinstance(status,bool) or status!=200:
            raise ValueError("invalid sync receipt HTTP status")
        body=response.read(4097)
        if len(body)>4096:
            raise ValueError("invalid sync receipt size")
        try:
            result=json.loads(body,object_pairs_hook=_unique_object)
        except (UnicodeDecodeError,json.JSONDecodeError):
            raise ValueError("invalid sync receipt JSON") from None
    return _validate_receipt(result,manifest,contract)
