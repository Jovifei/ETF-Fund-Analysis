import { test, expect } from '@playwright/test'

for (const viewport of [{ width: 1440, height: 1050 }, { width: 390, height: 844 }]) {
  test(`chart direction labels stay consistent inside the ${viewport.width}px dialog`, async ({ page }, info) => {
    await page.setViewportSize(viewport)
    await page.route('**/api/workspace/instruments/510300.SH/chart?**', async route => {
      const response = await route.fetch(), payload = await response.json()
      const levels = [
        { price: 2.2, zone_low: 2.1, zone_high: 2.3, type: 'support', groups: ['PIVOT'], methods: ['兼容方向测试'] },
        { price: 2.8, zone_low: 2.7, zone_high: 2.9, kind: 'resistance', type: 'support', groups: ['PIVOT'], methods: ['主字段优先测试'] },
        { price: 2.5, zone_low: 2.4, zone_high: 2.6, kind: 'unknown', type: 'support', groups: ['PIVOT'], methods: ['未知方向测试'] },
      ]
      await route.fulfill({ response, json: { ...payload,
        bars: payload.bars.map((bar: Record<string, unknown>) => ({ ...bar, open: 2.5, high: 3, low: 2, close: 2.5, indicators: {} })),
        research_bars: undefined, basis_transition: false, raw_overlay_allowed: true,
        sr_overlay_allowed: true, cost_overlay_allowed: false, qualification: 'UNKNOWN',
        support_resistance: { qualified: false, levels }, studies: {},
        chan_observation: null, price_structures: { boxes: [], qualified: false, actionable: false },
      } })
    })
    await page.goto('/etf/510300.SH')
    const chart = page.getByTestId('etf-chart')
    await expect(chart.locator('canvas').first()).toBeVisible()
    await chart.click({ position: { x: 80, y: 80 } })
    const dialog = page.locator('.expanded-chart')
    await expect(dialog).toHaveAttribute('role', 'dialog')
    const legend = dialog.locator('[aria-label="当前支撑压力快照价位"]')
    await expect(legend).toContainText('支撑 2.200')
    await expect(legend).toContainText('压力 2.800')
    const unknown = legend.locator('span').filter({ hasText: '方向未知 2.500' })
    await expect(unknown).toBeVisible()
    await expect(unknown).not.toHaveClass(/bull|bear/)
    const evidence = dialog.getByTestId('chart-level-evidence')
    await evidence.locator('summary').click()
    await expect(evidence).toContainText('支撑 2.200 · 兼容方向测试')
    await expect(evidence).toContainText('压力 2.800 · 主字段优先测试')
    await expect(evidence).toContainText('方向未知 2.500 · 未知方向测试')
    await evidence.screenshot({ path: info.outputPath(`sr-direction-evidence-${viewport.width}.png`) })
    await dialog.getByTestId('chart-sr-toggle').click()
    await expect(legend).toHaveCount(0)
    await dialog.getByTestId('chart-sr-toggle').click()
    await expect(legend).toContainText('支撑 2.200')
    await expect(legend).toContainText('方向未知 2.500')
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(page.locator('body')).not.toHaveClass(/modal-scroll-lock/)
    await expect(page.locator('[aria-label="当前支撑压力快照价位"]')).toContainText('支撑 2.200')
  })
}
