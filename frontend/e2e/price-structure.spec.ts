import { test, expect } from '@playwright/test'

test('daily box evidence renders as bounded candidate and confirmed overlays', async ({ page }, info) => {
  await page.route('**/api/workspace/instruments/510300.SH/chart?**', async route => {
    if (new URL(route.request().url()).searchParams.get('interval') !== '1d') return route.continue()
    const response = await route.fetch()
    const payload = await response.json()
    const bars = payload.research_bars?.length ? payload.research_bars : payload.bars
    const origin = bars.at(-30)?.date?.slice(0, 10)
    const confirmed = bars.at(-25)?.date?.slice(0, 10)
    const last = bars.at(-1)
    if (origin && confirmed && last) {
      const lower = Number(last.close) * 0.98
      const upper = Number(last.close) * 1.02
      const structures = { qualified: true, interval: '1d', actionable: false, source_as_of_date: last.date.slice(0, 10),
        price_basis_id: payload.research_price_basis_id, input_hash: 'browser-structure-fixture', boxes: [{
          kind: 'daily_box', structure_id: 'browser-box', lower, upper, mid: (lower + upper) / 2,
          origin_at: origin, confirmed_at: confirmed, state: 'confirmed', source_ids: ['upper-touch', 'lower-touch'],
          touch_count: 2, upper_touch_count: 1, lower_touch_count: 1, volume_confirmation_available: false,
          intraday_state: { state: 'breakout_attempt', side: 'upper', observed_at: '2026-09-25T10:20:00+08:00', source_id: 'provisional-observation' },
        }] }
      payload.price_structures = structures
      payload.research_price_structures = structures
    }
    await route.fulfill({ response, json: payload })
  })
  await page.goto('/etf/510300.SH')
  await expect(page.getByTestId('etf-chart').locator('canvas').first()).toBeVisible()
  await expect(page.getByTestId('chart-box-evidence')).toContainText('已确认')
  await expect(page.getByTestId('chart-box-evidence')).toContainText('量能确认不可用')
  await expect(page.getByTestId('chart-box-intraday-attempt')).toContainText('盘中上沿越界尝试')
  await expect(page.getByTestId('chart-box-evidence')).toContainText('状态：confirmed')
  await expect(page.getByTestId('etf-chart')).toHaveAttribute('aria-label', /K线/)
  await page.screenshot({ path: info.outputPath('daily-box-evidence.png'), fullPage: true })
  await page.getByRole('button', { name: '周 K', exact: true }).click()
  await expect(page.getByTestId('chart-box-evidence')).toContainText('本批仅支持日线结构')
})
