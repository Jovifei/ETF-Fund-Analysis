import {test,expect} from '@playwright/test'

test('narrow chart keeps server price lines and exposes long evidence outside canvas',async({page},info)=>{
  await page.setViewportSize({width:430,height:932})
  await page.goto('/etf/512480.SH')
  const chart=page.getByTestId('etf-chart'), evidence=page.getByTestId('chart-level-evidence')
  await expect(chart.locator('canvas').first()).toBeVisible()
  await chart.screenshot({path:info.outputPath('narrow-chart-price-lines.png')})
  await evidence.locator('summary').click()
  await expect(evidence.locator('li').first()).toBeVisible()
  await expect(evidence).toContainText('结构价位只计独立价格触碰')
  await evidence.screenshot({path:info.outputPath('narrow-chart-level-evidence.png')})
  expect(await page.evaluate(()=>Math.max(document.body.scrollWidth,document.documentElement.scrollWidth)-innerWidth)).toBeLessThanOrEqual(1)
})
