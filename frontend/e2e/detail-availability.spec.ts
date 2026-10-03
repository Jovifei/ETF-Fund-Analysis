import { test, expect } from '@playwright/test'

test('detail availability is readable on a narrow screen without provider writes', async ({ page }) => {
  const writes: string[]=[]
  page.on('request', request => { if(request.method() !== 'GET' && request.url().includes('/api/')) writes.push(request.url()) })
  await page.setViewportSize({width:390,height:844})
  await page.goto('/etf/512480.SH')
  const panel=page.getByTestId('availability-matrix')
  await expect(panel).toBeVisible()
  await expect(panel.locator('.availability-row')).toHaveCount(9)
  await expect(panel.getByText('支撑压力',{exact:true})).toBeVisible()
  expect(writes).toEqual([])
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
