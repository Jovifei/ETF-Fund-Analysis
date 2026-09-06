import { createRouter, type RouterHistory } from 'vue-router'
const overview = () => import('./views/Overview.vue')
const archive = () => import('./views/Research.vue')
export function makeRouter(history: RouterHistory) {
const router = createRouter({ history, scrollBehavior: () => ({ top: 0 }), routes: [
  { path: '/', component: overview, meta: { title: '市场总览' } },
  { path: '/boards', component: overview, meta: { title: '行业与概念板块' } },
  { path: '/decision/1430', component: overview, meta: { title: '14:30 尾盘研究' } },
  { path: '/analysis', component: () => import('./views/Catalog.vue'), meta: { title: 'ETF 分析' } },
  { path: '/etf/:code', component: () => import('./views/Detail.vue'), meta: { title: 'ETF 分析' } },
  { path: '/watchlist', component: () => import('./views/Watchlist.vue'), meta: { title: '我的自选' } },
  { path: '/holdings', component: () => import('./views/Holdings.vue'), meta: { title: '我的持仓' } },
  { path: '/ai', component: archive, meta: { title: 'AI 研究' } },
  { path: '/research', redirect: '/history' },
  { path: '/review', component: archive, meta: { title: '每日复盘' } },
  { path: '/history', component: archive, meta: { title: '研究档案' } },
  { path: '/research/news', component: () => import('./views/News.vue'), meta: { title: '新闻线索' } },
  { path: '/factors', component: () => import('./views/Factors.vue'), meta: { title: '因子研究' } },
  { path: '/settings', component: () => import('./views/Settings.vue'), meta: { title: '设置与连接' } },
  { path: '/system', redirect: '/settings' },
  { path: '/profile', component: () => import('./views/Settings.vue'), meta: { title: '个人中心' } },
  { path: '/legacy', redirect: '/history' },
  { path: '/workbench/1430', redirect: '/decision/1430' },
  { path: '/workbench/kline', redirect: '/analysis' },
  { path: '/:pathMatch(.*)*', component: () => import('./views/NotFound.vue'), meta: { title: '页面不存在' } },
] })
const historical: Record<string, string> = { holdings: '/holdings', news: '/research/news', system: '/settings', signals: '/', watchlist: '/watchlist' }
router.beforeEach(to => {
  const old = historical[to.hash.slice(1)]
  if (old && ['/legacy', '/research', '/history', '/'].includes(to.path)) return { path: old, replace: true }
})
router.afterEach(to => { document.title = `${String(to.meta.title ?? '研究')} · ETF Research` })
return router
}
export function etfPath(code: string) { return `/etf/${encodeURIComponent(code)}` }
