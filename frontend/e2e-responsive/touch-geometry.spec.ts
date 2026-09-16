import { test, expect, type Page, type TestInfo } from '@playwright/test'

// Device emulation is not native browser zoom or physical iOS/Android acceptance.
// KLineCharts 9.8.12 uses ResizeObserver's device pixel box when available.
// Its initial DPR fallback may remain supersampled until the observer redraws.
// Compare complete width/height pairs for either documented renderer path,
// never accept arbitrary dimensions or mix axes from different paths.
test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 })
type Measurement = { probe: boolean; width: number; height: number; expectedWidth: number; expectedHeight: number; estimatedWidth: number; estimatedHeight: number;
  cssWidth: number; cssHeight: number; hostWidth: number; hostHeight: number; dpr: number; basis: string }

async function measureCanvases(page: Page): Promise<Measurement[]> {
  return page.getByTestId('etf-chart').evaluate(host => new Promise<Measurement[]>((resolve, reject) => {
    const canvases = Array.from(host.querySelectorAll('canvas')).filter(c => c.clientWidth > 0 && c.clientHeight > 0)
    if (!canvases.length) { resolve([]); return }
    const sizes = new Map<HTMLCanvasElement, ResizeObserverEntry>()
    const timer = window.setTimeout(() => { observer.disconnect(); reject(new Error('canvas_observation_timeout')) }, 2000)
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) sizes.set(entry.target as HTMLCanvasElement, entry)
      if (sizes.size !== canvases.length) return
      // Let the renderer consume the same resize notification before comparing.
      requestAnimationFrame(() => requestAnimationFrame(() => {
        clearTimeout(timer); observer.disconnect()
        const parent = host.getBoundingClientRect()
        resolve(canvases.map(c => {
          const entry = sizes.get(c)!, physical = entry.devicePixelContentBoxSize?.[0]
          const css = c.getBoundingClientRect()
          return { probe: c.hasAttribute('data-pixel-negative-control'), width: c.width, height: c.height,
            expectedWidth: physical?.inlineSize ?? Math.round(entry.contentRect.width * devicePixelRatio),
            expectedHeight: physical?.blockSize ?? Math.round(entry.contentRect.height * devicePixelRatio),
            estimatedWidth: Math.round(entry.contentRect.width * devicePixelRatio),
            estimatedHeight: Math.round(entry.contentRect.height * devicePixelRatio),
            cssWidth: css.width, cssHeight: css.height, hostWidth: parent.width, hostHeight: parent.height,
            dpr: devicePixelRatio, basis: physical ? 'device-pixel-content-box' : 'DPR-estimate' }
        }))
      }))
    })
    for (const canvas of canvases) {
      try { observer.observe(canvas, { box: 'device-pixel-content-box' }) }
      catch { observer.observe(canvas) }
    }
  }))
}
function violations(rows: Measurement[]) {
  if (!rows.length) return ['no_visible_canvas']
  return rows.flatMap((c, i) => {
    const invalid = !Number.isFinite(c.expectedWidth) || !Number.isFinite(c.expectedHeight) || c.expectedWidth <= 0 || c.expectedHeight <= 0
    const observedPair = Math.abs(c.width - c.expectedWidth) <= 1 && Math.abs(c.height - c.expectedHeight) <= 1
    const fallbackPair = Math.abs(c.width - c.estimatedWidth) <= 1 && Math.abs(c.height - c.estimatedHeight) <= 1
    const pixelMismatch = !observedPair && !fallbackPair
    const overflow = c.cssWidth > c.hostWidth + 1 || c.cssHeight > c.hostHeight + 1
    return invalid || pixelMismatch || overflow ? [`${c.probe ? 'negative-control' : i}:invalid=${invalid},pixels=${pixelMismatch},overflow=${overflow}`] : []
  })
}
async function canvasFitsHost(page: Page, info: TestInfo, stage: string) {
  await expect(page.getByTestId('etf-chart').locator('canvas').first()).toBeVisible()
  let measured: Measurement[] = []
  try {
    await expect.poll(async () => { measured = await measureCanvases(page); return violations(measured) }).toEqual([])
  } finally {
    await info.attach(`canvas-geometry-${stage}`, { body: JSON.stringify(measured), contentType: 'application/json' })
  }
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
  await canvasFitsHost(page, info, 'portrait')
  // A genuinely undersized backing store MUST fail the same pixel check.
  await page.getByTestId('etf-chart').evaluate(host => {
    const probe = document.createElement('canvas'); probe.setAttribute('data-pixel-negative-control', '')
    probe.style.cssText = 'position:absolute;left:0;top:0;width:47px;height:31px;pointer-events:none'
    probe.width = 1; probe.height = 1; host.append(probe)
  })
  expect(violations(await measureCanvases(page)).some(v => v.startsWith('negative-control'))).toBe(true)
  // A mixed physical/DPR axis pair must fail too, even when one axis matches.
  await page.locator('[data-pixel-negative-control]').evaluate(el => {
    const probe = el as HTMLCanvasElement
    probe.width = Math.round(47 * devicePixelRatio); probe.height = 31
  })
  expect(violations(await measureCanvases(page)).some(v => v.startsWith('negative-control'))).toBe(true)
  await page.locator('[data-pixel-negative-control]').evaluate(el => el.remove())
  await page.getByRole('button', { name: '打开导航', exact: true }).tap()
  await expect(page.locator('.main-shell')).toHaveAttribute('inert', '')
  const close = page.getByRole('dialog', { name: '主要导航' }).getByRole('button', { name: '关闭导航', exact: true })
  await expect(close).toHaveCount(1)
  await close.tap()
  await expect(page.locator('.main-shell')).not.toHaveAttribute('inert')
  await page.getByTestId('chart-fullscreen').tap()
  await expect(page.locator('.expanded-chart')).toBeVisible()
  await canvasFitsHost(page, info, 'fullscreen')
  await page.getByTestId('chart-fullscreen').tap()
  await expect(page.locator('.expanded-chart')).toHaveCount(0)
  for (const viewport of [{ width: 844, height: 390 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport)
    await canvasFitsHost(page, info, `${viewport.width}x${viewport.height}`)
  }
  await page.getByTestId('chart-reset').tap()
  await page.getByTestId('etf-chart').screenshot({ path: info.outputPath('touch-dpr2-chart.png') })
  expect(errors).toEqual([])
  expect(writes).toEqual([])
})
