import { test, expect } from '@playwright/test'
import fixture from '../tests/fixtures/chan_chart_projection.json' with { type: 'json' }

declare global {
  interface Window { chanSettlementStrokes: number[][] }
}

for (const sample of [
  { interval: '1w', status: 'temporary', label: '输入暂定', dashed: true },
  { interval: '1w', status: 'settled', label: '输入已结算', dashed: false },
  { interval: '1mo', status: null, label: '输入结算状态未知', dashed: true },
]) test(`Chan ${sample.interval} ${sample.status ?? 'unknown'} input status paints matching boundaries`, async ({ page }, info) => {
  await page.addInitScript(() => {
    window.chanSettlementStrokes = []
    const context = document.createElement('canvas').getContext('2d')!
    context.strokeStyle = '#b388ff'
    const chanColor = context.strokeStyle
    const stroke = CanvasRenderingContext2D.prototype.stroke
    CanvasRenderingContext2D.prototype.stroke = function (...args: [] | [Path2D]) {
      if (this.strokeStyle === chanColor) window.chanSettlementStrokes.push(this.getLineDash())
      return Reflect.apply(stroke, this, args)
    }
  })
  await page.route('**/api/workspace/instruments/510300.SH/chart?**', async route => {
    const response = await route.fetch()
    const payload = await response.json()
    await route.fulfill({ response, json: { ...payload, ...fixture.chart, ts_code: '510300.SH', interval: sample.interval,
      chan_observation: { ...fixture.chart.chan_observation, settlement_status: sample.status },
      research_bars: undefined, raw_overlay_allowed: true, basis_transition: false,
      sr_overlay_allowed: false, cost_overlay_allowed: false, studies: {},
      price_structures: { boxes: [], qualified: false, actionable: false },
    } })
  })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/etf/510300.SH')
  const toggle = page.getByRole('checkbox', { name: '缠论笔段中枢', exact: true })
  await toggle.check()
  await expect(page.getByTestId('chart-chan-note')).toContainText(sample.label)
  await expect(page.getByTestId('chart-chan-note')).toContainText('引擎确认未知')
  await expect.poll(() => page.evaluate(() => window.chanSettlementStrokes.length)).toBeGreaterThan(0)
  expect(await page.evaluate(() => window.chanSettlementStrokes)).toEqual(expect.arrayContaining([sample.dashed ? [5, 3] : []]))
  expect(await page.evaluate(() => window.chanSettlementStrokes.every(dash => JSON.stringify(dash) === JSON.stringify(window.chanSettlementStrokes[0])))).toBe(true)
  await page.screenshot({ path: info.outputPath(`chan-${sample.status ?? 'unknown'}-desktop.png`), fullPage: true })
  await toggle.uncheck()
  await expect(page.getByTestId('chart-chan-note')).toHaveCount(0)
  await page.evaluate(() => { window.chanSettlementStrokes = [] })
  await page.getByTestId('chart-reset').click()
  await page.screenshot({ path: info.outputPath('chan-hidden.png') })
  expect(await page.evaluate(() => window.chanSettlementStrokes)).toEqual([])
  await page.setViewportSize({ width: 390, height: 844 })
  await toggle.check()
  await expect(page.getByTestId('chart-chan-note')).toContainText(sample.label)
  await expect.poll(() => page.evaluate(() => window.chanSettlementStrokes.length)).toBeGreaterThan(0)
  await page.screenshot({ path: info.outputPath(`chan-${sample.status ?? 'unknown'}-mobile.png`), fullPage: true })
  expect(errors).toEqual([])
})
