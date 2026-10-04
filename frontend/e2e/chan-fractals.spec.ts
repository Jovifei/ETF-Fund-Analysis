import { test, expect } from '@playwright/test'
import fixture from '../tests/fixtures/chan_chart_projection.json' with { type: 'json' }

declare global { interface Window { chanFractalPaints: string[] } }
for (const viewport of [{width:1440,height:1050},{width:320,height:720}]) test(`saved top/bottom fractals render and disappear honestly at ${viewport.width}px`, async ({page}, info) => {
  await page.setViewportSize(viewport)
  await page.addInitScript(() => {
    window.chanFractalPaints=[]
    const original=CanvasRenderingContext2D.prototype.fillText
    CanvasRenderingContext2D.prototype.fillText=function(text: string, ...args: [number,number,number?]) {
      if (text==='顶分型'||text==='底分型') window.chanFractalPaints.push(text)
      return Reflect.apply(original,this,[text,...args])
    }
  })
  await page.route('**/api/workspace/instruments/510300.SH/chart?**', async route => {
    const response=await route.fetch(), payload=await response.json()
    const interval=new URL(route.request().url()).searchParams.get('interval')??'1d'
    await route.fulfill({response,json:{...payload,...fixture.chart,interval,ts_code:'510300.SH',
      chan_observation:{...fixture.chart.chan_observation,observation_id:`fx-${interval}`,settlement_status:'temporary',fx:interval==='1d'?[
        {date:'2026-09-03 15:00:00',price:3,mark:'top',source:'persisted'},
        {date:'2026-09-08 15:00:00',price:1.5,mark:'bottom',source:'persisted'},
      ]:[]},research_bars:undefined,raw_overlay_allowed:true,basis_transition:false,sr_overlay_allowed:false,cost_overlay_allowed:false,studies:{},price_structures:{boxes:[],qualified:false,actionable:false}}})
  })
  const redraw = async () => { await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))) }
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message))
  await page.goto('/etf/510300.SH')
  const toggle=page.getByRole('checkbox',{name:'缠论笔段中枢',exact:true})
  await toggle.check()
  await expect(page.getByTestId('chart-chan-note')).toContainText('不是买卖建议或交易信号')
  await expect(page.getByTestId('chart-chan-note')).toContainText('不代表历史确认时点')
  await expect(page.getByTestId('chart-chan-note')).toContainText('输入暂定')
  await expect.poll(()=>page.evaluate(()=>[...new Set(window.chanFractalPaints)].sort())).toEqual(['底分型','顶分型'])
  const reset=page.getByTestId('chart-reset')
  await reset.scrollIntoViewIfNeeded()
  await page.screenshot({path:info.outputPath(`chan-fractals-${viewport.width}-viewport.png`)})
  await page.evaluate(()=>window.scrollTo(0,0))
  await page.screenshot({path:info.outputPath(`chan-fractals-${viewport.width}-full.png`),fullPage:true})
  await toggle.uncheck();await page.evaluate(()=>{window.chanFractalPaints=[]})
  await reset.click();await redraw();expect(await page.evaluate(()=>window.chanFractalPaints)).toEqual([])
  await toggle.check();await expect.poll(()=>page.evaluate(()=>window.chanFractalPaints.length)).toBeGreaterThan(0)
  const weekly = page.waitForResponse(response => response.url().includes('/chart?') && new URL(response.url()).searchParams.get('interval') === '1w')
  await page.getByRole('button',{name:'周 K',exact:true}).click()
  await weekly;await redraw()
  await expect(page.getByRole('button',{name:'周 K',exact:true})).toHaveAttribute('aria-pressed','true')
  await toggle.check();await page.evaluate(()=>{window.chanFractalPaints=[]});await reset.click();await redraw()
  expect(await page.evaluate(()=>window.chanFractalPaints)).toEqual([])
  expect(errors).toEqual([])
})