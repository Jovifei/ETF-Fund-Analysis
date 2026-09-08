import { defineConfig } from '@playwright/test'
import path from 'node:path'
import os from 'node:os'
export default defineConfig({
  testDir: './e2e-auth', workers:1, retries:0, timeout:45000,
  outputDir:'test-results-auth', reporter:[['list'], ['html',{outputFolder:'playwright-report-auth',open:'never'}]],
  use:{baseURL:'http://127.0.0.1:18083',viewport:{width:1440,height:1050},screenshot:'only-on-failure',trace:'retain-on-failure',
    launchOptions:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{}},
  webServer:{command:'python ../scripts/workspace_auth_smoke_seed.py && python -m uvicorn app.main:app --host 127.0.0.1 --port 18083',
    url:'http://127.0.0.1:18083/api/health',timeout:150000,reuseExistingServer:false,
    env:{...process.env as Record<string,string>,PYTHONPATH:path.resolve('../backend'),APP_ENV:'test',AUTH_ENABLED:'true',AUTH_COOKIE_SECURE:'false',
      MARKET_PROVIDER:'mock',AUTO_CREATE_SCHEMA:'true',ALLOW_MOCK_FALLBACK:'false',WORKSPACE_UI_ENABLED:'true',LLM_ENABLED:'false',ANALYSIS_ENABLED:'false',
      REGISTRATION_ENABLED:'true',REGISTRATION_INVITE_CODE:'browser-test-invite',LOG_LEVEL:'ERROR',
      DATABASE_URL:`sqlite:///${path.join(os.tmpdir(),'workspace-e2e-auth.sqlite3')}`,REPORTS_DIR:path.join(os.tmpdir(),'workspace-e2e-auth-reports')}}
})
