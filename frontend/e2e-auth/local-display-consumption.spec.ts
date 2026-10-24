import { test, expect } from '@playwright/test'

test('authenticated controlled replay pins one generation and hides cloud collection', async ({ page }, info) => {
  const generation = 101, requested: string[] = [], writes: string[] = [], indexHistory: string[] = [], minuteHistory: string[] = []
  const asOf = '2026-10-23T07:00:00+00:00'
  const meta = { generation, research_source: 'local_bundle', is_stale: true, actionable: false }
  const context = { ...meta, read_contract: 'local-display-context-read-v1',
    generated_at: asOf, expires_at: '2026-10-23T07:05:00+00:00', read_at: '2026-10-23T08:00:00+00:00',
    source_as_of: '2026-10-23', refreshed_at: '2026-10-23T06:30:00+00:00', refreshed_in_slot: false,
    is_expired: true, historical_identity: true, available: true,
    availability: 'carried_forward', reason: 'fast_slot_reuses_same_day_refresh',
    research_only: true, provider_called: false, calibration_status: 'not_calibrated', index_history_available: false }
  const observations = [{ context_id: 'cn-csi300', context_kind: 'index', label: '受控指数观测', observed_value: 100,
    source: 'controlled-replay', source_timestamp: asOf, freshness: 'historical' }]
  page.on('request', request => {
    if (/\/api\/(workspace\/(market-context|sectors|indexes|instruments\/510300\.SH(?:\/chart)?)|decision-board)\?/.test(request.url())) requested.push(request.url())
    if (request.method() === 'POST' && /\/api\/workspace\//.test(request.url())) writes.push(request.url())
    if (request.method() === 'GET' && /\/api\/workspace\/indexes\//.test(request.url())) indexHistory.push(request.url())
    if (request.method() === 'GET' && /\/api\/workspace\/instruments\/510300\.SH\/chart\?/.test(request.url()) &&
      ['30m', '60m'].includes(new URL(request.url()).searchParams.get('interval') ?? '')) minuteHistory.push(request.url())
  })
  await page.route('**/api/workspace/overview?*', route => route.fulfill({ json: { ...meta, rows: [], total: 0 } }))
  await page.route('**/api/workspace/market-context?*', route => route.fulfill({ json: {
    ...context, latest_view: observations } }))
  await page.route('**/api/workspace/sectors?*', route => route.fulfill({ json: {
    ...meta, boards: [], availability: 'unavailable', reason: 'optional_refresh_failed' } }))
  await page.route('**/api/workspace/indexes?*', route => route.fulfill({ json: { ...context, items: observations } }))
  await page.route('**/api/decision-board?*', route => route.fulfill({ json: {
    ...meta, rows: [], snapshot_id: 'controlled-101', generated_at: asOf, counts: {}, horizons: [1,3,7,20,60] } }))
  await page.goto('/')
  await page.getByLabel('账户', { exact: true }).fill('browser-admin')
  await page.getByLabel('密码', { exact: true }).fill('test-only-browser-pass')
  await page.getByRole('button', { name: '登录并进入总览' }).click()
  await expect(page.getByTestId('local-bundle-generation')).toContainText('101')
  expect((await page.request.get('/api/auth/me')).ok()).toBeTruthy()
  const contextStatus = page.getByTestId('market-context-status')
  await expect(contextStatus).toContainText('沿用既有数据')
  await expect(contextStatus).toContainText('本时段沿用同日已存观察，未重新采集。')
  await expect(contextStatus).toContainText('展示包已过期')
  await expect(contextStatus).toContainText('历史版本')
  await expect(contextStatus).toContainText('批次 101 · 来源日期 2026-10-23')
  await expect(contextStatus).toContainText('生成 10/23 15:00')
  await expect(contextStatus).toContainText('上下文更新 10/23 14:30')
  await expect(contextStatus).toContainText('读取 10/23 16:00')
  await expect(page.getByTestId('sector-status')).toContainText('采集失败')
  await expect(page.getByRole('button', { name: '同步市场目录与板块' })).toHaveCount(0)
  const contextCard = page.locator('.market-context-card').filter({ hasText: '受控指数观测' })
  await expect(contextCard).toContainText('最近历史收盘 · controlled-replay · 2026-10-23 · 历史日线观察')
  await expect(contextCard).toContainText('本地展示包未发布指数历史')
  await expect(contextCard).not.toHaveAttribute('role', 'button')
  await expect(contextCard).not.toHaveAttribute('tabindex', '0')
  await expect(page.getByRole('button', { name: '查看受控指数观测历史数据' })).toHaveCount(0)
  await contextCard.click()
  await expect(page.getByRole('button', { name: '下载指数历史' })).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('controlled-local-bundle.png') })
  expect(requested.length).toBeGreaterThanOrEqual(4)
  expect(requested.every(url => new URL(url).searchParams.get('generation') === String(generation))).toBe(true)
  expect(indexHistory).toEqual([])
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
  await expect(page.getByRole('button', { name: '小时 K', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '日 K', exact: true })).toBeVisible()
  expect(requested.some(url => new URL(url).pathname === '/api/workspace/instruments/510300.SH')).toBe(true)
  expect(requested.some(url => new URL(url).pathname === '/api/workspace/instruments/510300.SH/chart')).toBe(true)
  expect(requested.every(url => new URL(url).searchParams.get('generation') === String(generation))).toBe(true)
  expect(indexHistory).toEqual([])
  expect(minuteHistory).toEqual([])
  expect(writes).toEqual([])
})
