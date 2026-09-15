import {test,expect} from '@playwright/test'

test('login/register reflow and phone login/logout with the same database auth',async({page},info)=>{
  const errors:string[]=[]
  page.on('pageerror',e=>errors.push(e.message))
  for(const width of [320,390,430,768,1024,1440,1920,3840]){
    await page.setViewportSize({width,height:932})
    for(const path of ['/login','/register']){
      await page.goto(path)
      await expect(page.locator('.login-card h1')).toBeVisible()
      await expect.poll(()=>page.evaluate(()=>Math.max(document.body.scrollWidth,document.documentElement.scrollWidth)-innerWidth)).toBeLessThanOrEqual(1)
      if(width===390)await page.screenshot({path:info.outputPath(`${path.slice(1)}-390.png`)})
    }
  }
  await page.setViewportSize({width:390,height:844});await page.goto('/login')
  await page.getByLabel('账户',{exact:true}).fill('browser-admin')
  await page.getByLabel('密码',{exact:true}).fill('test-only-browser-pass')
  await page.getByRole('button',{name:'登录并进入总览'}).click()
  await expect(page.getByRole('heading',{name:'市场总览',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'打开导航',exact:true}).click()
  await expect(page.locator('.sidebar')).toHaveAttribute('aria-modal','true')
  await page.locator('.sidebar').getByTitle('退出登录',{exact:true}).click()
  await expect(page.getByRole('heading',{name:'账户登录',exact:true})).toBeVisible()
  await expect(page.locator('.workspace')).toHaveCount(0)
  expect(errors).toEqual([])
})
