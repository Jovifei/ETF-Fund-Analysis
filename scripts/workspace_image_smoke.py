"""Exercise packaged Vue deep links, assets, private API and real 404 semantics."""
from __future__ import annotations
import json
import re
import sys
from urllib.error import HTTPError
from urllib.request import urlopen


def main(origin: str) -> None:
    if not re.fullmatch(r'http://127\.0\.0\.1:\d{2,5}', origin):
        raise SystemExit('smoke target must be an explicit loopback test service')
    def fetch(path: str):
        try:
            with urlopen(origin + path, timeout=10) as response:
                return response.status, response.read().decode(), response.headers
        except HTTPError as exc:
            return exc.code, exc.read().decode(), exc.headers
    code, body, _ = fetch('/api/health')
    assert code == 200 and json.loads(body)['auth_enabled'] is True
    for path in ['/', '/etf/512480.SH', '/holdings', '/ai', '/settings']:
        code, html, headers = fetch(path)
        assert code == 200 and '/workspace-assets/' in html, path
        assert "script-src 'self'" in headers.get('Content-Security-Policy', '')
    assets = re.findall(r'(?:src|href)="(/workspace-assets/[^\"]+)"', html)
    assert assets
    for asset in assets:
        code, body, headers = fetch(asset)
        assert code == 200 and body
        assert 'immutable' in headers['Cache-Control']
    assert fetch('/api/workspace/holdings')[0] == 401
    assert fetch('/workspace-assets/missing.js')[0] == 404
    assert fetch('/api/workspace/does-not-exist')[0] in (401, 404)
    assert fetch('/does-not-exist')[0] == 404
    print('Packaged Vue / CSP / assets / private API / 404 smoke passed.')


if __name__ == '__main__':
    main(sys.argv[1])
