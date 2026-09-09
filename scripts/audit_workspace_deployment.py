#!/usr/bin/env python3
"""Audit a running instance without login secrets or changing its database.

Reports the observed HTTP deployment only. A passing loopback demo does not
prove production, PostgreSQL, authenticated browser flows or provider access.
"""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8082')
    parser.add_argument('--expected-version',default='1.0.1')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    target=urlsplit(args.url)
    if target.scheme not in {'http','https'} or target.username or target.password or target.query or target.fragment or target.path not in {'','/'}:
        parser.error('Use a bare origin without credentials or query parameters')
    if target.scheme=='http' and target.hostname not in {'127.0.0.1','localhost','::1'}:
        parser.error('Unencrypted audit is restricted to loopback')
    import httpx
    checks=[];health={}
    with httpx.Client(base_url=args.url,timeout=8,follow_redirects=False) as client:
        try:
            response=client.get('/api/health');response.raise_for_status();health=response.json()
            checks.append({'name':'version','passed':health.get('version')==args.expected_version})
            for route in ('/','/matrix','/classic/etf-board','/settings'):
                page=client.get(route)
                checks.append({'name':route,'passed':page.status_code==200,'csp_present':bool(page.headers.get('content-security-policy'))})
                assets=re.findall(r'(?:src|href)="(/workspace-assets/[^\"]+)"',page.text)[:5]
                for asset in assets:
                    if not re.fullmatch(r'/workspace-assets/[a-zA-Z0-9_.-]+',asset):continue
                    res=client.get(asset)
                    checks.append({'name':'built_asset','passed':res.status_code==200 and 'text/html' not in res.headers.get('content-type','')})
            checks.append({'name':'no_api_spa_fallback','passed':client.get('/api/workspace/not-real').status_code in {401,404}})
        except (httpx.HTTPError,ValueError) as exc:
            checks.append({'name':'http_access','passed':False,'failure_class':type(exc).__name__})
    result={'as_of':datetime.now(UTC).isoformat(),'scope':'unauthenticated_http_smoke_only','checks':checks,
        'version':health.get('version'),'provider':health.get('provider'),'auth_enabled':health.get('auth_enabled'),
        'demo_only':health.get('provider')=='mock','passed':bool(checks) and all(c['passed'] for c in checks),
        'not_verified':['actual provider permissions and continuity','authenticated UI and user isolation','PostgreSQL migration and backup','production TLS and cookies'],
        'mutations':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'version':result['version'],'demo_only':result['demo_only']}))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
