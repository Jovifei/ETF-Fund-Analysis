import { expect, test } from '@playwright/test'

test('detail shows a newly read snapshot within one visible refresh interval', async ({ page }) => {
  let detailReads = 0
  let chartReads = 0
  const writes: string[] = []
  page.on('request', request => {
    if (request.method() !== 'GET') writes.push(request.method())
  })
  await page.route('**/api/workspace/instruments/512480.SH', async route => {
    detailReads += 1
    await route.fulfill({
      json: {
        instrument: { ts_code: '512480.SH', name: '半导体ETF', kind: 'ETF', theme_l1: '科技', theme_l2: '半导体' },
        decision: null, snapshot_id: `snapshot-${detailReads}`, decision_time: `2026-09-23T10:00:${String(detailReads).padStart(2, '0')}+08:00`,
        quote: { price: 1 + detailReads / 100, change_ratio: 0, status: 'recent_observation', source_time: `2026-09-23T10:00:${String(detailReads).padStart(2, '0')}+08:00`, fetched_at: `2026-09-23T10:00:${String(detailReads).padStart(2, '0')}+08:00`, source: 'fixture' },
        indicator_values: {}, indicator_version: null, indicator_as_of: '2026-09-22', forecasts: {},
        support_resistance: null, holding: null, forecast_scenario: null,
      },
    })
  })
  await page.route('**/api/workspace/instruments/512480.SH/chart?*', async route => {
    chartReads += 1
    await route.fulfill({
      json: {
        ts_code: '512480.SH', interval: '1d', available: false, bars: [], reason: 'fixture',
        source_as_of: `2026-09-2${2 + chartReads}`, as_of: '2026-09-23T10:00:00+08:00',
        computed_at: `2026-09-23T10:00:${String(chartReads).padStart(2, '0')}+08:00`,
      },
    })
  })

  await page.clock.install({ time: new Date('2026-09-23T10:00:00+08:00') })
  await page.goto('/etf/512480.SH')
  const freshness = page.getByTestId('detail-freshness')
  await expect(freshness).toContainText('snapshot-1')
  await expect(freshness).toContainText('10:00:01')
  await page.clock.fastForward(60_000)
  await expect(freshness).toContainText('snapshot-2')
  await expect(freshness).toContainText('10:00:02')
  expect(detailReads).toBe(2)
  expect(chartReads).toBe(2)
  expect(writes).toEqual([])
})
