"""Render real Vue components against an in-process ASGI test app.

This harness does not navigate to a network URL or alter managed browser policy.
It is NOT a replacement claim for production HTTP/CSP/TLS browser E2E testing.
Only a new temporary mock database is touched; no model is ever called.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from datetime import datetime,UTC


def main():
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument('--bundle-dir',type=Path,required=True)
    args.add_argument('--output-dir',type=Path,required=True)
    args.add_argument('--browser',default='/usr/bin/chromium')
    opt=args.parse_args()
    out=opt.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/'backend'))
    with TemporaryDirectory(prefix='etf-offline-validation-') as temp:
        os.environ.update(APP_ENV='test',AUTH_ENABLED='false',AUTH_COOKIE_SECURE='false',MARKET_PROVIDER='mock',ALLOW_MOCK_FALLBACK='false',AUTO_CREATE_SCHEMA='true',ANALYSIS_ENABLED='false',LLM_ENABLED='false',OCR_MODE='disabled',LOG_LEVEL='ERROR',WORKSPACE_UI_ENABLED='true',WORKSPACE_BRIDGE_ENABLED='true',DATABASE_URL=f'sqlite:///{temp}/test.sqlite3',REPORTS_DIR=f'{temp}/reports')
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.session import init_db,session_scope
        from app.services.task_service import TaskService
        from app.services.decision_board_service import DecisionBoardService
        from playwright.sync_api import sync_playwright,expect
        init_db()
        with session_scope() as db:
            tasks=TaskService()
            try: tasks.run(db,'bootstrap',lookback_days=420,report=False);DecisionBoardService().refresh(db)
            finally: tasks.close()
        checks=[];console_errors=[];api_calls=[]
        with TestClient(app) as client,sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=opt.browser,headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
            page.on('pageerror',lambda e:console_errors.append(str(e)))
            page.on('dialog',lambda d:d.accept())
            def exchange(source, request):
                path=request['path'];method=request.get('method','GET')
                if not path.startswith('/api/') or '://' in path or '\\' in path:
                    raise ValueError('validation API scope violation')
                api_calls.append({'method':method,'path':path})
                response=client.request(method,path,headers=request.get('headers',{}),content=request.get('body'))
                return {'status':response.status_code,'headers':dict(response.headers),'body':base64.b64encode(response.content).decode()}
            page.expose_binding('__asgiFetch',exchange)
            page.set_content('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"></head><body><div id="app"></div></body></html>')
            page.add_script_tag(content='''if (!crypto.randomUUID) { crypto.randomUUID=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('') };
            window.fetch = async (path, options={}) => {
              if (options.signal?.aborted) throw new DOMException('aborted','AbortError');
              if (options.body instanceof FormData) throw new Error('Multipart is tested separately, not emulated here');
              const r=await window.__asgiFetch({path:String(path),method:options.method||'GET',headers:options.headers||{},body:options.body});
              if(options.signal?.aborted) throw new DOMException('aborted','AbortError');
              const body=Uint8Array.from(atob(r.body),c=>c.charCodeAt(0));
              return new Response(r.status===204?null:body,{status:r.status,headers:r.headers});
            };''')
            for css in opt.bundle_dir.glob('*.css'): page.add_style_tag(content=css.read_text())
            page.add_script_tag(content=(opt.bundle_dir/'validation.js').read_text())
            expect(page.get_by_role('heading',name='市场总览',exact=True)).to_be_visible(timeout=15000)
            expect(page.locator('tbody tr').first).to_be_visible()
            page.screenshot(path=str(out/'overview.png'),full_page=True)
            checks.append('real overview component consumes real ASGI mock snapshots')
            search=page.get_by_role('combobox',name='搜索 ETF 或 LOF')
            search.fill('512480')
            expect(page.get_by_role('button',name='加自选',exact=True).first).to_be_visible()
            page.get_by_role('button',name='加自选',exact=True).first.click()
            expect(page.get_by_role('button',name='已自选',exact=True).first).to_be_visible()
            page.evaluate("window.validationRouter.push('/etf/512480.SH')")
            expect(page.get_by_test_id('etf-chart')).to_be_visible(timeout=15000)
            expect(page.locator('[data-testid=etf-chart] canvas').first).to_be_visible()
            page.get_by_role('button',name='60 根',exact=True).click()
            page.get_by_test_id('chart-reset').click()
            box=page.get_by_test_id('etf-chart').bounding_box()
            page.mouse.move(box['x']+box['width']/2,box['y']+100)
            page.mouse.wheel(0,-300)
            page.mouse.down();page.mouse.move(box['x']+box['width']/2+80,box['y']+100,steps=5);page.mouse.up()
            page.get_by_test_id('etf-chart').dblclick(position={'x':200,'y':100})
            page.screenshot(path=str(out/'detail.png'),full_page=True)
            checks.append('search/watchlist/detail/canvas zoom drag reset without model tasks')
            assert not any(v['method']=='POST' and '/research-jobs' in v['path'] for v in api_calls)
            page.evaluate("window.validationRouter.push('/holdings?code=512480.SH')")
            expect(page.locator('[name=holding-code]')).to_have_value('512480.SH')
            page.locator('[name=holding-shares]').fill('1234');page.locator('[name=holding-cost]').fill('4.551')
            page.get_by_role('button',name='生成录入预览').click()
            try: expect(page.get_by_test_id('import-preview')).to_be_visible()
            except AssertionError:
                print('Preview form errors:', page.locator('.form-error').all_text_contents())
                page.screenshot(path=str(out/'preview-failure.png'),full_page=True)
                raise
            page.get_by_role('button',name='确认导入 1 条').click()
            expect(page.get_by_role('button',name='撤销这次导入')).to_be_visible()
            after=client.get('/api/workspace/holdings').json()
            assert next(r for r in after['items'] if r['ts_code']=='512480.SH')['shares']==1234
            page.screenshot(path=str(out/'holdings.png'),full_page=True)
            page.evaluate("window.validationRouter.push('/etf/512480.SH')")
            expect(page.get_by_test_id('chart-cost-label')).to_contain_text('4.551')
            page.screenshot(path=str(out/'cost-line.png'),full_page=True)
            checks.append('holding preview confirmation persisted and canonical chart shows cost')
            # External Vibe-shaped artifact intake, never an actual model report.
            page.evaluate("window.validationRouter.push('/ai?code=512480.SH')")
            page.locator('.external-import summary').click()
            text='# Offline validation fixture\nNot an investment recommendation.\n'
            artifacts=[{'name':name,'text':body,'sha256':hashlib.sha256(body.encode()).hexdigest()} for name,body in [('manifest.json','{"status":"complete"}'),('report.md',text)]]
            packet={'schema_version':'etf-external-research-v1','producer':'vibe','producer_version':'fixture','run_id':'offline-render-fixture','kind':'etf','ts_code':'512480.SH','model':'none-fixture','upstream_status':'complete','source_as_of':datetime.now(UTC).isoformat(),'artifacts':artifacts}
            page.get_by_label('选择外部研究包').set_input_files({'name':'external.json','mimeType':'application/json','buffer':json.dumps(packet).encode()})
            expect(page.get_by_test_id('external-preview')).to_be_visible()
            page.locator('.external-import input[type=checkbox]').check()
            page.get_by_role('button',name='确认导入外部候选').click()
            expect(page.get_by_text('外部来源未验证',exact=True).first).to_be_visible()
            page.screenshot(path=str(out/'research.png'),full_page=True)
            checks.append('native-artifact preview and explicit unverified candidate import')
            page.evaluate("window.validationRouter.push('/factors')")
            expect(page.get_by_role('heading',name='风格研究模板',exact=True)).to_be_visible()
            page.screenshot(path=str(out/'factors.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.get_by_role('button',name='打开导航',exact=True).click()
            expect(page.locator('.workspace')).to_have_class(__import__('re').compile('mobile-open'))
            page.screenshot(path=str(out/'mobile.png'),full_page=True)
            page.keyboard.press('Escape')
            checks.append('factor templates and responsive mobile drawer')
            assert not console_errors, console_errors
            browser.close()
        (out/'result.json').write_text(json.dumps({'validation_kind':'offline_browser_with_in_process_asgi','mock':True,'models_called':False,'network_navigation':False,'production_http_e2e':'not_run_in_this_harness','checks':checks,'page_errors':console_errors,'api_calls':len(api_calls)},ensure_ascii=False,indent=2))
        print(json.dumps({'checks_passed':len(checks),'page_errors':console_errors,'api_calls':len(api_calls)}))


if __name__=='__main__':main()
