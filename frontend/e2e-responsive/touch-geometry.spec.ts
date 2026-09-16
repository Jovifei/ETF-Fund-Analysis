import { test, expect, type Page } from '@playwright/test'

// Touch/DPR emulation is distinct from the CSS-zoom stress suite and from
// physical iOS/Android browser acceptance. Only isolated HTTP fixtures are used.
test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 })

async function canvasFitsHost(page: Page) {
  const chart = page.getByTestId('etf-chart')
  await expect(chart.locator('canvas').first()).toBeVisible()
  await expect.poll(() => chart.evaluate(host => {
    const canvases = Array.from(host.querySelectorAll('canvas')).filter(c => c.clientWidth > 0 && c.clientHeight > 0)
    return canvases.length > 0 && canvases.every(c => {
      const bounds = c.getBoundingClientRect(), parent = host.getBoundingClientRect()
      return bounds.width <= parent.width + 1 && bounds.height <= parent.height + 1
        && Math.abs(c.width - c.clientWidth * devicePixelRatio) <= 2
        && Math.abs(c.height - c.clientHeight * devicePixelRatio) <= 2
    })
  })).toBe(true)
  await expect.poll(() => page.evaluate(() => {
    const root = document.scrollingElement as HTMLElement
    return root.scrollWidth - root.clientWidth
  })).toBeLessThanOrEqual(1)
}

test('touch controls and orientation preserve chart sizing at DPR 2', async ({ page }, info) => {
  const errors: string[] = [], writes: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('request', r => { if (r.method() === 'POST' && new URL(r.url()).pathname.startsWith('/api/')) writes.push(new URL(r.url()).pathname) })
  await page.goto('/etf/512480.SH')
  expect(await page.evaluate(() => navigator.maxTouchPoints)).toBeGreaterThan(0)
  expect(await page.evaluate(() => devicePixelRatio)).toBe(2)
  const viewport = await page.locator('meta[name="viewport"]').getAttribute('content')
  expect(viewport).toContain('width=device-width')
  expect(viewport).not.toMatch(/user-scalable\s*=\s*no|maximum-scale\s*=\s*1(?:[,\s]|$)/i)
  await canvasFitsHost(page)
  await page.getByRole('button', { name: '打开导航', exact: true }).tap()
  await expect(page.locator('.main-shell')).toHaveAttribute('inert', '')
  // The backdrop is also a close control; choose the button inside the dialog.
  const close = page.getByRole('dialog', { name: '主要导航' }).getByRole('button', { name: '关闭导航', exact: true })
  await expect(close).toHaveCount(1)
  await close.tap()
  await expect(page.locator('.main-shell')).not.toHaveAttribute('inert')
  await page.getByTestId('chart-fullscreen').tap()
  await expect(page.locator('.expanded-chart')).toBeVisible()
  await canvasFitsHost(page)
  await page.getByTestId('chart-fullscreen').tap()
  await expect(page.locator('.expanded-chart')).toHaveCount(0)
  for (const viewport of [{ width: 844, height: 390 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport)
    await canvasFitsHost(page)
  }
  await page.getByTestId('chart-reset').tap()
  await page.getByTestId('etf-chart').screenshot({ path: info.outputPath('touch-dpr2-chart.png') })
  expect(errors).toEqual([])
  expect(writes).toEqual([])
})
