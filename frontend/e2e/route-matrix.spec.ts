import { expect, test } from '@playwright/test'

test('enabled workspace pages and legacy redirects resolve to their router contracts', async ({ page }) => {
  const pages: Array<[string, string]> = [
    ['/', '市场总览'],
    ['/analysis', 'ETF 分析'], ['/etf/512480.SH', 'ETF 分析'],
    ['/watchlist', '我的自选'], ['/holdings', '我的持仓'], ['/ai', 'AI 研究'],
    ['/review', '每日复盘'], ['/history', '研究档案'], ['/research/news', '新闻线索'],
    ['/factors', '因子研究'], ['/settings', '设置与连接'], ['/profile', '个人中心'],
  ]
  for (const [path, title] of pages) {
    await page.goto(path)
    await expect(page).toHaveTitle(`${title} · ETF Research`)
  }

  const redirects: Array<[string, string]> = [
    ['/login', '/'], ['/register', '/'],
    ['/boards', '/#market-boards'], ['/decision/1430', '/?mode=1430#etf-decisions'],
    ['/matrix', '/#etf-decisions'], ['/classic/etf-board', '/#etf-decisions'],
    ['/research', '/history'], ['/system', '/settings'], ['/legacy', '/history'],
    ['/workbench/1430', '/?mode=1430#etf-decisions'], ['/workbench/kline', '/analysis'],
    ['/#holdings', '/holdings'], ['/#news', '/research/news'], ['/#system', '/settings'],
    ['/#signals', '/'], ['/#watchlist', '/watchlist'],
  ]
  for (const [path, target] of redirects) {
    await page.goto(path)
    await expect.poll(() => new URL(page.url()).pathname + new URL(page.url()).search + new URL(page.url()).hash).toBe(target)
  }
})
