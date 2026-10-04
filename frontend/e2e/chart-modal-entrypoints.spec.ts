import { test, expect, type Locator, type Page } from '@playwright/test'

async function paneHeight(chart: Locator) {
  const canvas = chart.locator('canvas').first()
  await expect(canvas).toBeVisible()
  return Math.round((await canvas.boundingBox())!.height)
}

async function openFromCompactChart(page: Page, chart: Locator, label: string, info: any) {
  const compact = await paneHeight(chart)
  await chart.click({ position: { x: 80, y: 80 } })
  const dialog = page.locator('.expanded-chart')
  await expect(dialog).toBeVisible()
  await expect(dialog).toHaveAttribute('role', 'dialog')
  await expect(page.locator('body')).toHaveClass(/modal-scroll-lock/)
  const expanded = await paneHeight(chart)
  await info.attach(label + '-pane-heights', {
    body: JSON.stringify({ compact_main_pane_px: compact, expanded_main_pane_px: expanded }),
    contentType: 'application/json',
  })
  expect(compact).toBeGreaterThan(180)
  expect(expanded).toBeGreaterThan(compact + 40)
  expect(expanded).toBeGreaterThan(360)

  const box = (await chart.boundingBox())!
  await page.mouse.move(box.x + 120, box.y + 120)
  await page.mouse.down()
  await page.mouse.move(box.x + 220, box.y + 140, { steps: 5 })
  await page.mouse.up()
  await chart.click({ position: { x: 160, y: 120 } })
  await expect(dialog).toBeVisible()
  await expect(page.locator('.expanded-chart')).toHaveCount(1)

  const focusStates: Array<{tag:string; hiddenByCollapsedDetails:boolean; inside:boolean}> = []
  for(let index=0;index<36;index++){
    focusStates.push(await page.evaluate(()=>{
      const active=document.activeElement as HTMLElement|null
      const dialog=document.querySelector('.expanded-chart')
      const collapsed=active?.closest('details:not([open])')
      const summary=collapsed?.firstElementChild?.tagName==='SUMMARY'?collapsed.firstElementChild:collapsed?.querySelector('summary')
      return {tag:active?.tagName??'',hiddenByCollapsedDetails:Boolean(collapsed&&summary!==active),inside:Boolean(active&&dialog?.contains(active))}
    }))
    await page.keyboard.press('Tab')
  }
  expect(focusStates.every(state=>state.inside&&!state.hiddenByCollapsedDetails)).toBe(true)
  expect(focusStates.some(state=>state.tag==='SUMMARY')).toBe(true)
  return { compact, expanded }
}

test('Detail compact K-line click opens one dialog and measures the real candle pane', async ({ page }, info) => {
  await page.goto('/etf/512480.SH')
  const chart = page.getByTestId('etf-chart')
  await openFromCompactChart(page, chart, 'detail', info)
  await page.keyboard.press('Escape')
  await expect(page.locator('.expanded-chart')).toHaveCount(0)
  await expect(page.locator('body')).not.toHaveClass(/modal-scroll-lock/)
})

for (const viewport of [{ width: 390, height: 844 }, { width: 320, height: 720 }]) {
  test(`Detail compact chart opens at ${viewport.width}px and keeps a usable main pane`, async ({ page }, info) => {
    await page.setViewportSize(viewport)
    await page.goto('/etf/512480.SH')
    const chart = page.getByTestId('etf-chart')
    const { expanded } = await openFromCompactChart(page, chart, `detail-${viewport.width}`, info)
    expect(expanded).toBeGreaterThanOrEqual(320)
  })
}

test('Overview index K-line compact surface opens the same dialog', async ({ page }, info) => {
  await page.goto('/')
  await page.getByRole('button', { name: '查看沪深300历史数据' }).click()
  const chart = page.locator('.market-context-detail [data-testid=etf-chart]')
  await openFromCompactChart(page, chart, 'overview-index', info)
})

test('global search to ETF Detail retains chart-surface modal entry', async ({ page }, info) => {
  await page.goto('/')
  await page.getByLabel('搜索 ETF 或 LOF').fill('512480')
  await page.getByRole('button', { name: '看图', exact: true }).first().click()
  await expect(page).toHaveURL(/\/etf\/512480\.SH$/)
  const chart = page.getByTestId('etf-chart')
  await openFromCompactChart(page, chart, 'search-detail', info)
})

test('Legacy detail canvas click enlarges once and measures its actual canvas', async ({ page }, info) => {
  await page.goto('/')
  const frame = page.frameLocator('iframe[title="原版 ETF 决策快照"]')
  await frame.locator('#searchInput').fill('512480')
  const row = frame.locator('.decision-data-row').first()
  await expect(row).toBeVisible()
  await row.click()
  const overlay = frame.locator('#detailOverlay')
  await expect(overlay).not.toHaveClass(/hidden/)
  const canvas = frame.locator('#chartCanvas')
  await expect(canvas).toBeVisible()
  const compact = Math.round((await canvas.boundingBox())!.height)
  await canvas.click({ position: { x: 80, y: 80 } })
  const modal = frame.locator('#detailOverlay .detail-modal')
  await expect(modal).toHaveClass(/chart-expanded/)
  const expanded = Math.round((await canvas.boundingBox())!.height)
  await info.attach('legacy-pane-heights', {
    body: JSON.stringify({ compact_canvas_px: compact, expanded_canvas_px: expanded }),
    contentType: 'application/json',
  })
  expect(expanded).toBeGreaterThan(compact + 40)
  await canvas.click({ position: { x: 120, y: 100 } })
  await expect(modal).toHaveClass(/chart-expanded/)
  await frame.locator('#chartExpandButton').click()
  await expect(modal).not.toHaveClass(/chart-expanded/)
  await expect.poll(async()=>Math.round((await canvas.boundingBox())!.height)).toBeLessThan(expanded-40)
})
