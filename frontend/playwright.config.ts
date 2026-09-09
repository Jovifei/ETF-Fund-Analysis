import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'
import os from 'node:os'
const directory = path.join(os.tmpdir(), 'etf-workspace-e2e')
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, retries: 0, timeout: 45000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}, baseURL: 'http://127.0.0.1:18082', viewport: { width: 1440, height: 1050 }, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: {
    command: 'python ../scripts/workspace_smoke_seed.py && python -m uvicorn app.main:app --host 127.0.0.1 --port 18082',
    url: 'http://127.0.0.1:18082/api/health', timeout: 150000, reuseExistingServer: false,
    env: { ...process.env as Record<string,string>, PYTHONPATH: path.resolve('../backend'), APP_ENV: 'test', AUTH_ENABLED: 'false', AUTH_COOKIE_SECURE: 'false', MARKET_PROVIDER: 'mock', AUTO_CREATE_SCHEMA: 'true', ALLOW_MOCK_FALLBACK: 'false', ANALYSIS_ENABLED: 'false', LLM_ENABLED: 'false', OCR_MODE: 'disabled', LOG_LEVEL: 'ERROR', WORKSPACE_UI_ENABLED: 'true', WORKSPACE_BRIDGE_ENABLED: 'true', DATABASE_URL: `sqlite:///${path.join(os.tmpdir(), 'workspace-e2e.sqlite3')}`, REPORTS_DIR: directory },
  },
})
