import {test, expect} from '@playwright/test'

test('V105 data diagnostics is a read-only panel in the original overview shell', async ({page}) => {
  const writes:string[]=[]
  page.on('request', request => {if(request.method()==='POST') writes.push(request.url())})
  await page.goto('/')
  const health=page.getByTestId('data-health')
  await expect(health).toBeVisible()
  await health.locator('summary').click()
  await expect(health.getByRole('cell', {name:/^ETF 现价/})).toBeVisible()
  await expect(health.getByRole('cell', {name:/^ETF 已存日线/})).toBeVisible()
  await health.getByRole('button', {name:'重新读取状态（不抓取）'}).click()
  await expect(page.locator('.sidebar')).toHaveCount(1)
  expect(writes).toEqual([])
  await page.screenshot({path:'test-results/v105-data-health.png', fullPage:false})
})

test('AI setup exposes interactive mode cards and never calls a model while switching steps', async ({page}) => {
  const writes:string[]=[]
  page.on('request', request => {if(request.method()==='POST') writes.push(request.url())})
  await page.goto('/ai')
  const guide=page.getByTestId('ai-setup-guide')
  await expect(guide.getByRole('button',{name:/模型 API/})).toHaveAttribute('aria-pressed','true')
  await guide.getByRole('button',{name:/本地 Codex/}).click()
  await expect(guide.getByTestId('ai-mode-codex')).toBeVisible()
  await guide.getByRole('button',{name:/不用 AI/}).click()
  await expect(guide.getByTestId('ai-mode-manual')).toBeVisible()
  expect(writes).toEqual([])
})
