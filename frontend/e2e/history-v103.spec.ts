import {test,expect} from '@playwright/test'

test('index cards open actual cached OHLC candles, not point history',async({page,request},info)=>{
 const r=await request.get('/api/workspace/indexes/cn-csi300/chart');expect(r.ok()).toBeTruthy()
 const d=await r.json();expect(d.available).toBe(true);expect(d.actionable).toBe(false);expect(d.qualification).toBe('mock');expect(d.bars.length).toBeGreaterThan(60)
 expect(d.bars.some((b:any)=>b.open!==b.close&&b.high>b.low)).toBe(true)
 await page.goto('/');await page.getByRole('button',{name:'查看沪深300历史数据'}).click()
 await expect(page.locator('.market-context-detail [data-testid=etf-chart] canvas').first()).toBeVisible()
 await expect(page.locator('.market-context-detail .chart-legend').first()).toContainText('开')
 await page.screenshot({path:info.outputPath('v103-index-history.png'),fullPage:true})
})

test('unsupported index cards do not offer the A-share download action', async ({page}) => {
 await page.route('**/api/market-context', async route => {
  const response = await route.fetch()
  const payload = await response.json()
  payload.latest_view = [...(payload.latest_view ?? []), {
   context_id:'us-sp500', label:'S&P 500', context_kind:'index', observed_value:5000,
   today_pct_change:0, source_timestamp:'2026-09-08', source:'mock', freshness:'stale',
   is_tradable_proxy:false
  }]
  await route.fulfill({response, json:payload})
 })
 await page.goto('/')
 const unsupported = page.locator('.market-context-card').filter({hasText:'S&P 500'}).first()
 await unsupported.click()
 await expect(page.locator('.market-context-detail')).toContainText('当前版本仅支持三个 A 股指数历史下载')
 await expect(page.getByRole('button',{name:'下载指数历史'})).toHaveCount(0)
})

test('favorites work in catalog and original decision template without navigation',async({page,request},info)=>{
 const code='512480.SH';const before=(await(await request.get('/api/workspace/watchlist')).json()).items.find((r:any)=>r.ts_code===code)
 if(before)await request.delete('/api/watchlist/entries/'+before.id)
 await page.goto('/analysis?q='+code)
 await page.getByRole('button',{name:'收藏 '+code,exact:true}).click()
 await expect(page).toHaveURL(/analysis/)
 await expect(page.getByRole('button',{name:'取消收藏 '+code,exact:true})).toBeVisible()
 await page.goto('/watchlist');await expect(page.locator('tbody')).toContainText(code)
 await page.goto('/');const frame=page.frameLocator('iframe[title="原版 ETF 决策快照"]')
 await frame.locator('#searchInput').fill(code)
 await expect(frame.locator('[data-favorite="'+code+'"]').first()).toContainText('已收藏')
 await frame.locator('[data-favorite="'+code+'"]').first().click()
 await expect(frame.locator('[data-favorite="'+code+'"]').first()).toContainText('收藏')
 await expect.poll(async()=> (await(await request.get('/api/workspace/watchlist')).json()).items.some((r:any)=>r.ts_code===code)).toBe(false)
 await expect(page).toHaveURL(/\/$/)
 await page.screenshot({path:info.outputPath('v103-favorite-template.png'),fullPage:true})
 // restore original fixture state for other journeys
 if(before)await request.post('/api/watchlist/entries',{data:{code}})
})

test('human review saves privately without a model; AI connection steps are visible',async({page},info)=>{
 const models:string[]=[];page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/research-jobs'))models.push(r.url())})
 await page.goto('/review');await page.getByLabel('当时判断与依据',{exact:true}).fill('验证人工复盘，不修改策略')
 await page.getByLabel('后来结果与偏差',{exact:true}).fill('等待真实价格兑现')
 await page.getByRole('button',{name:'保存人工复盘',exact:true}).click()
 await expect(page.getByTestId('manual-review')).toContainText('人工复盘已保存')
 await page.reload();await expect(page.getByLabel('当时判断与依据',{exact:true})).toHaveValue('验证人工复盘，不修改策略')
 await page.goto('/ai');await expect(page.getByTestId('ai-setup')).toContainText('CODEX_HOME')
 await page.getByRole('button',{name:'Vibe / 外部模型',exact:true}).click()
 await expect(page.getByTestId('ai-setup')).toContainText('尚未开放')
 expect(models).toEqual([])
 await page.screenshot({path:info.outputPath('v103-ai-guide.png'),fullPage:true})
})
