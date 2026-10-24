import { test, expect } from '@playwright/test'

test('authenticated controlled replay pins one generation and hides cloud collection', async ({ page }, info) => {
  const generation = 101, requested: string[] = [], writes: string[] = [], indexCharts: string[] = []
  const asOf = '2026-10-23T07:00:00+00:00'
  const meta = { generation, research_source: 'local_bundle', is_stale: true, actionable: false }
  page.on('request', request => {
    if (/\/api\/(workspace\/(market-context|sectors|indexes)|decision-board)\?/.test(request.url())) requested.push(request.url())
    if (/\/api\/workspace\/indexes\/[^/]+\/chart(?:\?|$)/.test(request.url())) indexCharts.push(request.url())
    if (request.method() === 'POST' && /\/api\/workspace\/(data-jobs|onboard|discovery\/refresh)/.test(request.url())) writes.push(request.url())
  })
  await page.route('**/api/workspace/overview?*', route => route.fulfill({ json: { ...meta, rows: [], total: 0 } }))
  await page.route('**/api/workspace/market-context?*', route => route.fulfill({ json: {
    ...meta, read_contract: 'local-display-context-read-v1', index_history_available: false,
    generated_at: asOf, read_at: asOf, source_as_of: '2026-10-23', refreshed_at: asOf,
    latest_view: [{ context_id: 'cn-csi300', context_kind: 'index', label: '受控指数观测', observed_value: 100,
      source_timestamp: asOf, freshness: 'historical' }], availability: 'carried_forward', reason: 'fast_slot_reuses_same_day_refresh' } }))
  await page.route('**/api/workspace/sectors?*', route => route.fulfill({ json: {
    ...meta, boards: [], availability: 'unavailable', reason: 'optional_refresh_failed' } }))
  await page.route('**/api/workspace/indexes?*', route => route.fulfill({ json: { ...meta, items: [] } }))
  await page.route('**/api/decision-board?*', route => route.fulfill({ json: {
    ...meta, rows: [], snapshot_id: 'controlled-101', generated_at: asOf, counts: {}, horizons: [1,3,7,20,60] } }))
  await page.goto('/')
  await page.getByLabel('账户', { exact: true }).fill('browser-admin')
  await page.getByLabel('密码', { exact: true }).fill('test-only-browser-pass')
  await page.getByRole('button', { name: '登录并进入总览' }).click()
  await expect(page.getByTestId('local-bundle-generation')).toContainText('101')
  expect((await page.request.get('/api/auth/me')).ok()).toBeTruthy()
  await expect(page.getByTestId('market-context-status')).toContainText('沿用同日')
  await expect(page.getByTestId('sector-status')).toContainText('采集失败')
  await expect(page.getByRole('button', { name: '同步市场目录与板块' })).toHaveCount(0)
  // In local-bundle mode, index observations are read-only cards, not a synthetic OHLC entrypoint.
  await expect(page.getByRole('button', { name: '查看受控指数观测历史数据' })).toHaveCount(0)
  await expect(page.locator('.market-context-card')).toContainText('本地展示包未发布指数历史')
  await expect(page.locator('.market-context-detail')).toHaveCount(0)
  expect(indexCharts).toEqual([])
  await expect(page.getByRole('button', { name: '下载指数历史' })).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('controlled-local-bundle.png') })
  expect(requested.length).toBeGreaterThanOrEqual(4)
  expect(requested.every(url => new URL(url).searchParams.get('generation') === String(generation))).toBe(true)
  expect(indexCharts).toEqual([])
  expect(writes).toEqual([])

  await page.route(/\/api\/workspace\/instruments\/510300\.SH(?:\?.*)?$/, route => route.fulfill({ json: {
    ...meta, instrument: { ts_code: '510300.SH', name: '受控标的', kind: 'ETF', theme_l1: '测试', theme_l2: '' },
    quote: { price: null, status: 'stale' }, decision: null, snapshot_id: 'controlled-101', decision_time: asOf,
    read_as_of: asOf, indicator_values: {}, indicator_version: null, indicator_as_of: null,
    forecasts: {}, support_resistance: null, holding: null, forecast_scenario: null } }))
  await page.route('**/api/workspace/instruments/510300.SH/chart?*', route => route.fulfill({ json: {
    ...meta, ts_code: '510300.SH', interval: '1d', available: false, bars: [], as_of: asOf } }))
  await page.goto('/etf/510300.SH?generation=101')
  await expect(page.getByTestId('local-history-read-only')).toBeVisible()
  await expect(page.getByRole('button', { name: '补齐历史并加入研究池' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '30 分钟', exact: true })).toHaveCount(0)
  expect(writes).toEqual([])
})
