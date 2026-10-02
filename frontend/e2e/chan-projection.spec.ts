import { test, expect } from '@playwright/test'
import fixture from '../tests/fixtures/chan_chart_projection.json' with { type: 'json' }

declare global {
  interface Window { chanZoneDraws: Array<{ width: number; height: number }> }
}

test('persisted timestamp zones actually paint and survive repeated layer toggles', async ({ page }, info) => {
  await page.addInitScript(() => {
    window.chanZoneDraws = []
    const context = document.createElement('canvas').getContext('2d')!
    context.fillStyle = '#b388ff18'
    const zoneFill = context.fillStyle
    const roundRect = CanvasRenderingContext2D.prototype.roundRect
    CanvasRenderingContext2D.prototype.roundRect = function (x, y, width, height, radii) {
      if (this.fillStyle === zoneFill) window.chanZoneDraws.push({ width, height })
      return roundRect.call(this, x, y, width, height, radii)
    }
  })
  await page.route('**/api/workspace/instruments/510300.SH/chart?**', async route => {
    if (new URL(route.request().url()).searchParams.get('interval') !== '1d') return route.continue()
    const response = await route.fetch()
    const payload = await response.json()
    await route.fulfill({ response, json: { ...payload, ...fixture.chart, ts_code: '510300.SH',
      research_bars: undefined, raw_overlay_allowed: true, basis_transition: false,
      sr_overlay_allowed: false, cost_overlay_allowed: false, studies: {},
      price_structures: { boxes: [], qualified: false, actionable: false },
    } })
  })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/etf/510300.SH')
  await expect(page.getByTestId('etf-chart').locator('canvas').first()).toBeVisible()
  const toggle = page.getByRole('checkbox', { name: '缠论笔段中枢', exact: true })
  const painted = () => page.evaluate(() => window.chanZoneDraws.some(rect => rect.width > 0 && rect.height > 0))
  await toggle.check()
  await expect(page.getByTestId('chart-chan-note')).toContainText('已保存缠论')
  await expect.poll(painted).toBe(true)
  await page.screenshot({ path: info.outputPath('persisted-chan-timestamp-zone.png'), fullPage: true })
  for (let repeat = 0; repeat < 2; repeat++) {
    await toggle.uncheck()
    await expect(page.getByTestId('chart-chan-note')).toHaveCount(0)
    await page.evaluate(() => { window.chanZoneDraws = [] })
    await page.getByTestId('chart-reset').click()
    await page.screenshot({ path: info.outputPath(`chan-hidden-${repeat}.png`) })
    expect(await painted()).toBe(false)
    await toggle.check()
    await expect.poll(painted).toBe(true)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await page.evaluate(() => { window.chanZoneDraws = [] })
  await page.getByTestId('chart-reset').click()
  await expect.poll(painted).toBe(true)
  await page.screenshot({ path: info.outputPath('persisted-chan-timestamp-mobile.png'), fullPage: true })
  expect(errors).toEqual([])
})
