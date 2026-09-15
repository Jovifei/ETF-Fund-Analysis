import { defineConfig } from '@playwright/test'
import path from 'node:path'
import os from 'node:os'
import base from './playwright.config'
export default defineConfig({
  ...base,
  testDir: './e2e-responsive', workers: 1, retries: 0, timeout: 90000,
  outputDir: 'test-results-responsive',
  reporter: [['list'], ['json', { outputFile: 'responsive-results.json' }],
    ['html', { outputFolder: 'playwright-report-responsive', open: 'never' }]],
  webServer: {
    ...base.webServer as object,
    command: 'python ../scripts/workspace_smoke_seed.py && python -m uvicorn app.main:app --host 127.0.0.1 --port 18085',
    url: 'http://127.0.0.1:18085/api/health', timeout: 150000, reuseExistingServer: false,
    env: { ...(base.webServer as {env: Record<string, string>}).env,
      DATABASE_URL: `sqlite:///${path.join(os.tmpdir(), 'workspace-e2e-responsive.sqlite3')}`,
      REPORTS_DIR: path.join(os.tmpdir(), 'workspace-responsive-e2e-reports') },
  },
  use: { ...base.use, baseURL: 'http://127.0.0.1:18085' },
})
