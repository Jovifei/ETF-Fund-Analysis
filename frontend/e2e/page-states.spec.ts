import { test, expect } from '@playwright/test'

const fail = (status: number) => ({ status, contentType: 'application/json', body: JSON.stringify({ detail: 'isolated_page_state_fixture' }) })

test('news API failures are visible and retry reloads the saved list', async ({ page }) => {
  let attempts = 0
  await page.route(url => url.pathname === '/api/news', route => {
    attempts += 1
    return attempts === 1 ? route.fulfill(fail(500)) : route.fulfill({ json: [] })
  })
  await page.goto('/research/news')
  await expect(page.getByRole('alert').filter({ hasText: '暂时无法载入' })).toBeVisible()
  await page.getByRole('alert').getByRole('button', { name: '重新读取' }).click()
  await expect(page.getByText('暂无匹配的新闻记录')).toBeVisible()
  expect(attempts).toBe(2)
})

test('news source-status failure has its own retry explanation', async ({ page }) => {
  await page.route(url => url.pathname === '/api/workspace/news-status', route => route.fulfill(fail(500)))
  await page.goto('/research/news')
  await expect(page.getByRole('alert').filter({ hasText: '采集状态读取失败' })).toBeVisible()
  await expect(page.getByRole('button', { name: '重新读取状态' })).toBeVisible()
})

test('factor diagnostics and research archive distinguish endpoint failures from empty state', async ({ page }) => {
  await page.route(url => url.pathname === '/api/workspace/factor-diagnostics', route => route.fulfill(fail(500)))
  await page.goto('/factors')
  await expect(page.getByRole('alert').filter({ hasText: '暂时无法载入' })).toBeVisible()

  await page.route(url => url.pathname === '/api/workspace/research-jobs', route => route.fulfill(fail(404)))
  await page.goto('/history')
  await expect(page.getByRole('alert').filter({ hasText: '暂时无法载入' })).toBeVisible()
})

test('factor and archive pages show explicit empty states when endpoints return valid empty payloads', async ({ page }) => {
  await page.route(url => url.pathname === '/api/workspace/factors', route => route.fulfill({ json: { registry: [], name_count: 0, note: 'empty fixture', report: null } }))
  await page.route(url => url.pathname === '/api/workspace/factor-diagnostics', route => route.fulfill({ json: { report: null } }))
  await page.route(url => url.pathname === '/api/workspace/research-styles', route => route.fulfill({ json: { templates: [] } }))
  await page.goto('/factors')
  await expect(page.getByText('尚无该期限的诊断结果')).toBeVisible()

  await page.route(url => url.pathname === '/api/workspace/research-jobs', route => route.fulfill({ json: { items: [] } }))
  await page.goto('/history')
  await expect(page.getByText('还没有研究任务')).toBeVisible()
})

test('review read timeout remains visible without saving a draft', async ({ page }) => {
  await page.route(url => url.pathname.startsWith('/api/workspace/review-notes/'), route => route.abort('timedout'))
  await page.goto('/review')
  const status = page.locator('[data-testid="manual-review"] p[role="status"]')
  await expect(status).not.toHaveText('')
  await expect(page.getByRole('button', { name: '保存人工复盘' })).toBeVisible()
})
