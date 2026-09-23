import {test,expect} from '@playwright/test'

test('indicator manager changes panes without replacing candles or issuing writes',async({page},info)=>{
 const errors:string[]=[],writes:string[]=[]
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')writes.push(new URL(r.url()).pathname)})
 await page.goto('/etf/512480.SH')
 const chart=page.getByTestId('etf-chart'),picker=page.getByTestId('indicator-picker')
 await expect(chart.locator('canvas').first()).toBeVisible()
 await chart.locator('canvas').first().evaluate(el=>el.setAttribute('data-instance-sentinel','original'))
 await picker.locator('summary').click()
 await picker.getByLabel('显示 BOLL',{exact:true}).check()
 await picker.getByLabel('显示 MACD',{exact:true}).uncheck()
 await expect(chart.locator('[data-instance-sentinel="original"]')).toHaveCount(1)
 await expect(picker.getByRole('button',{name:'移除 BOLL',exact:true})).toBeVisible()
 await expect(picker.getByRole('button',{name:'移除 MACD',exact:true})).toHaveCount(0)
 await page.getByRole('button',{name:'关闭技术指标'}).click()
 await expect(picker).not.toHaveAttribute('open')
 await page.getByRole('button',{name:'成交量',exact:true}).click()
 await expect(page.getByRole('button',{name:'成交量',exact:true})).toHaveAttribute('aria-pressed','false')
 await expect(chart.locator('[data-instance-sentinel="original"]')).toHaveCount(1)
 for(const width of [320,430,1440]){
  await page.setViewportSize({width,height:1000});await picker.locator('summary').click()
  await expect.poll(()=>page.evaluate(()=>Math.max(document.body.scrollWidth,document.documentElement.scrollWidth)-innerWidth)).toBeLessThanOrEqual(1)
  await page.screenshot({path:info.outputPath(`indicator-menu-${width}.png`)})
  await page.keyboard.press('Escape');await expect(picker).not.toHaveAttribute('open')
 }
 expect(errors).toEqual([]);expect(writes).toEqual([])
})
