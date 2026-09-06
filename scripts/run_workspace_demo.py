#!/usr/bin/env python3
"""Start the bundled Vue UI with isolated synthetic data and no AI credentials.

Only 127.0.0.1 is supported. The temporary database and reports are removed on
exit. Real holdings, production configuration and the user's Codex home are not
used. Use the separate authenticated Compose deployment for real data.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8081)
    parser.add_argument('--smoke',action='store_true',help='Verify packaged UI and APIs in process, then exit')
    args=parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('port must be 1024..65535')
    root=Path(__file__).resolve().parents[1]
    if any((root/p).exists() for p in ('.env','deploy/.env.production')):
        parser.error('Demo refuses to run beside private dotenv files. Use a fresh extracted delivery directory.')
    if not (root/'backend/app/workspace_dist/index.html').is_file():
        parser.error('Prebuilt UI missing: npm ci --prefix frontend && npm run build --prefix frontend')
    sys.path.insert(0,str(root/'backend'))
    with TemporaryDirectory(prefix='etf-workspace-demo-') as temp:
        os.environ.update(APP_ENV='test',AUTH_ENABLED='false',AUTH_COOKIE_SECURE='false',REGISTRATION_ENABLED='false',AUTO_CREATE_SCHEMA='true',MARKET_PROVIDER='mock',ALLOW_MOCK_FALLBACK='false',ANALYSIS_ENABLED='false',LLM_ENABLED='false',OCR_MODE='disabled',DATABASE_URL=f'sqlite:///{temp}/demo.sqlite3',REPORTS_DIR=f'{temp}/reports',WORKSPACE_UI_ENABLED='true',WORKSPACE_BRIDGE_ENABLED='false',WORKSPACE_DAILY_REVIEW_ENABLED='false')
        from app.db.session import init_db,session_scope
        from app.services.task_service import TaskService
        from app.services.decision_board_service import DecisionBoardService
        from app.main import app
        init_db()
        with session_scope() as db:
            service=TaskService()
            try:service.run(db,'bootstrap',lookback_days=420,report=False);DecisionBoardService().refresh(db)
            finally:service.close()
        if args.smoke:
            from fastapi.testclient import TestClient
            import re
            checked=[]
            with TestClient(app) as client:
                for path in ('/','/etf/512480.SH','/holdings','/ai','/settings'):
                    response=client.get(path)
                    assert response.status_code==200 and '/workspace-assets/' in response.text
                    assert "script-src 'self'" in response.headers.get('Content-Security-Policy','')
                    for asset in re.findall(r'(?:src|href)="(/workspace-assets/[^\"]+)"',response.text):
                        resource=client.get(asset)
                        assert resource.status_code==200 and 'immutable' in resource.headers.get('Cache-Control','')
                    checked.append(path)
                assert client.get('/not-a-real-page').status_code==404
                assert client.get('/workspace-assets/not-there.js').status_code==404
                assert client.get('/api/workspace/not-an-api').status_code==404
                assert client.get('/api/search/instruments?q=512480').json()['items']
                assert client.get('/api/workspace/instruments/512480.SH/chart').json()['actionable'] is False
            print(json.dumps({'status':'passed','mode':'isolated_mock_asgi_smoke','routes':checked,'models_called':False}))
            return
        print(f'Demo only: http://127.0.0.1:{args.port} — synthetic data, no model, no real holdings. Ctrl+C to stop.')
        import uvicorn
        uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')


if __name__=='__main__': main()
