import { test, expect, type Page } from '@playwright/test'

const screens = [[320, 720], [390, 844], [430, 932], [768, 1024],
  [1024, 768], [1440, 1050], [1920, 1080], [3840, 1920]] as const
const pages = ['/', '/etf/512480.SH', '/holdings', '/settings']
async function noPageOverflow(page: Page) {
  await expect.poll(() => page.evaluate(() => Math.max(document.body.scrollWidth,
    document.documentElement.scrollWidth) - window.innerWidth)).toBeLessThanOrEqual(1)
}
for (const [width, height] of screens) {
  test(`reflow ${width}x${height}: overview, chart, holdings and settings`, async ({ page }, info) => {
    await page.setViewportSize({ width, height })
    const errors: string[] = [], writes: string[] = []
    page.on('pageerror', e => errors.push(e.message))
    page.on('request', r => { if (r.method() === 'POST' && r.url().includes('/api/')) writes.push(r.url()) })
    for (const route of pages) {
      await page.goto(route)
      await expect(page.locator('#main-content h1')).toBeVisible()
      if (route === '/') {
        if (width <= 680) {
          await expect(page.getByTestId('mobile-decision-board')).toBeVisible()
          await expect(page.getByTestId('mobile-decision-row').first()).toBeVisible()
          await expect(page.getByTestId('mobile-decision-row').first()).toContainText('历史收盘')
        } else {
          const frame = page.frameLocator('iframe[title="原版 ETF 决策快照"]')
          await expect(frame.locator('.decision-data-row').first()).toBeVisible()
          await expect.poll(() => frame.locator('html').evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1)
        }
        if (width >= 1920) {
          await expect.poll(async () => (await page.locator('.main-content').boundingBox())!.width)
            .toBeGreaterThan(width - 340)
        }
      }
      if (route.startsWith('/etf/')) await expect(page.getByTestId('etf-chart').locator('canvas').first()).toBeVisible()
      await noPageOverflow(page)
      if (route === '/' || route.startsWith('/etf/')) {
        await page.screenshot({ path: info.outputPath(`${route === '/' ? 'overview' : 'chart'}-${width}.png`), fullPage: false })
      }
    }
    expect(writes).toEqual([])
    expect(errors).toEqual([])
  })
}

test('mobile drawer isolates focus and restores it; breakpoint releases scroll lock', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto('/')
  const open = page.getByRole('button', { name: '打开导航', exact: true })
  await expect(open).toBeVisible()
  await expect(page.locator('.sidebar')).toHaveAttribute('inert', '')
  await open.click()
  await expect(page.locator('.mobile-menu')).toHaveAttribute('aria-expanded', 'true')
  await expect(page.locator('.sidebar')).toHaveAttribute('aria-modal', 'true')
  await expect(page.locator('.main-shell')).toHaveAttribute('inert', '')
  for (let i = 0; i < 25; i++) {
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => document.querySelector('.sidebar')!.contains(document.activeElement))).toBe(true)
  }
  await page.keyboard.press('Escape')
  await expect(open).toBeFocused()
  await expect(page.locator('body')).not.toHaveClass(/mobile-navigation-open/)
  await open.click(); await page.setViewportSize({ width: 1440, height: 1050 })
  await expect(page.locator('.workspace')).not.toHaveClass(/mobile-open/)
  await expect(page.locator('.main-shell')).not.toHaveAttribute('inert')
  await expect(page.locator('body')).not.toHaveClass(/mobile-navigation-open/)
})

test('mobile and original table share filters, horizons, actions and safe explanations', async ({ page }) => {
  await page.route('**/api/decision-board?*', async route => {
    const response = await route.fetch(); const data = await response.json()
    data.rows = data.rows.map((r: any) => r.ts_code === '512480.SH' ? { ...r,
      grade: '数据异常', data_status: 'historical_price_only',
      grade_reason: '<img src=x onerror="window.badReason=true">缺量额；仅可查看历史价格' } : r)
    await route.fulfill({ response, json: data })
  })
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto('/')
  const mobile = page.getByTestId('mobile-decision-board')
  await expect(mobile).toBeVisible()
  await mobile.getByLabel('筛选决策标的').fill('512480')
  await expect(page.getByTestId('mobile-decision-row')).toHaveCount(1)
  await expect(mobile).toContainText('数据异常')
  await expect(mobile).toContainText('缺量额；仅可查看历史价格')
  expect(await page.evaluate(() => (window as any).badReason)).toBeUndefined()
  await mobile.getByLabel('研究期限').selectOption('5')
  await page.setViewportSize({ width: 1440, height: 1050 })
  const frame = page.frameLocator('iframe[title="原版 ETF 决策快照"]')
  await expect(frame.locator('#searchInput')).toHaveValue('512480')
  await expect(frame.locator('#horizonSelect')).toHaveValue('5')
  await page.setViewportSize({ width: 390, height: 844 })
  await mobile.getByRole('link', { name: /512480.SH/ }).click()
  await expect(page).toHaveURL(/\/etf\/512480.SH$/)
})

test('chart canvases follow viewport, sidebar, fullscreen and pointer interactions', async ({ page }, info) => {
  await page.goto('/etf/512480.SH')
  const chart = page.getByTestId('etf-chart')
  await expect(chart.locator('canvas').first()).toBeVisible()
  const before = await chart.boundingBox()
  await page.getByRole('button', { name: '切换侧栏形态' }).click()
  await expect.poll(async () => (await chart.boundingBox())!.width).toBeGreaterThan(before!.width + 100)
  await page.setViewportSize({ width: 430, height: 932 })
  await expect.poll(async () => (await chart.boundingBox())!.width).toBeLessThan(431)
  await chart.hover(); await page.mouse.wheel(0, -200)
  const box = (await chart.boundingBox())!
  await page.mouse.move(box.x + 100, box.y + 80); await page.mouse.down()
  await page.mouse.move(box.x + 160, box.y + 80, { steps: 5 }); await page.mouse.up()
  await page.getByTestId('chart-fullscreen').click()
  await expect(page.locator('.expanded-chart')).toBeVisible()
  await expect(chart.locator('canvas').first()).toBeVisible()
  await page.screenshot({ path: info.outputPath('chart-fullscreen-mobile.png') })
  await page.keyboard.press('Escape')
  await expect(page.locator('.expanded-chart')).toHaveCount(0)
  await page.getByTestId('chart-reset').click()
  await noPageOverflow(page)
})

// CSS zoom is a separate stress check, not claimed as browser UI Ctrl+/Ctrl-.
for (const zoom of [0.8, 1.25, 2]) {
  test(`CSS zoom stress ${zoom}`, async ({ page }, info) => {
    await page.goto('/etf/512480.SH')
    await expect(page.getByTestId('etf-chart').locator('canvas').first()).toBeVisible()
    await page.evaluate(value => { document.documentElement.style.zoom = String(value) }, zoom)
    await noPageOverflow(page)
    await expect(page.getByTestId('chart-fullscreen')).toBeVisible()
    await page.screenshot({ path: info.outputPath(`css-zoom-${zoom}.png`) })
  })
}
