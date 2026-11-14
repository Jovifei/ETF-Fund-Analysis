import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import Overview from '../src/views/Overview.vue'
import UsMarketsResearchCard from '../src/components/UsMarketsResearchCard.vue'
import { api } from '../src/lib/api'

vi.mock('../src/lib/api', () => ({ api: vi.fn(), errorText: (error: Error) => error.message }))

const flags = { research_only: true, actionable: false, calibration_status: 'not_calibrated' }
const spark = Array.from({ length: 30 }, (_, i) => [`2026-10-${String((i % 28) + 1).padStart(2, '0')}`, 100 + i])
const basket = { ...flags, series_id: 'us-cpo-optical-broad-ew', label: '美股 CPO/光模块（宽口径等权）', group_id: 'cpo_optical',
  kind: 'basket', available: true, as_of: '2026-11-13', level: 1998.1, provisional_last_close: true,
  returns: { '1w': 0.1036, '1m': -0.2003, '3m': -0.3748, ytd: 0.4211, '1y': 0.5808 }, drawdown: { current: -0.4277 },
  atr_pct: 0.0947, atr_risk_bucket: 'extreme', dow_phase: 'sideways', wyckoff_phase: 'not_computed',
  rs: { vs_spx: { excess: { '3m': -0.3511 } }, vs_ndx: { excess: { '3m': -0.3064 } } }, spark,
  rationale: '研究自定义篮子', coverage_note: '成分按上市日起逐步扩容：CRDO 自 2022-01-27',
  members: [{ ticker: 'COHR', name: 'Coherent', available: true, first_date: '2018-01-02', returns: { '1w': 0.13, '1m': -0.13, '3m': -0.38, ytd: 0.18 } },
    { ticker: 'XXXX', name: 'Missing', available: false }] }
const index = { ...flags, series_id: 'us-sp500', label: '标普 500', group_id: 'us_index', kind: 'index', available: true,
  as_of: '2026-11-13', level: 7561.67, provisional_last_close: false, returns: { '1w': 0.025, '1m': -0.0236, '3m': -0.0237, ytd: 0.1046, '1y': 0.1037 },
  drawdown: { current: -0.0329 }, atr_pct: 0.0143, atr_risk_bucket: 'mid', dow_phase: 'downtrend', wyckoff_phase: 'markup',
  rs: { vs_ndx: { excess: { '3m': 0.044 } } }, spark }
const down = { ...flags, series_id: 'us-nasdaq-composite', label: '纳斯达克综合', group_id: 'us_index', kind: 'index', available: false, reason: 'provider_returned_no_data' }
const view = { read_contract: 'us-markets-research-read-v1', availability: 'partial', available: true, reason: null, source_stale: false, source_age_days: 1,
  research: { ...flags, schema_version: 'us_markets_research_v1', changes_grade: false, availability: 'partial', as_of: '2026-11-13',
    source: { label: 'yfinance (Yahoo Finance, 非官方免费源)', note: '生产官方美股指数卡片仍使用原有新浪通道' },
    provisional_closes: [{ ticker: 'LITE', date: '2026-11-13' }], failed_tickers: ['SNDK'],
    groups: [{ group_id: 'us_index', label: '美股指数', order: 3 }, { group_id: 'cpo_optical', label: '美股 CPO / 光模块', order: 1 }],
    series: [basket, index, down] } }

const cleanup: Array<() => void> = []
afterEach(() => { cleanup.splice(0).forEach(fn => fn()); vi.unstubAllGlobals() })

describe('UsMarketsResearchCard', () => {
  it('shows baskets, indices, research-only flags, provisional and failed-ticker warnings', () => {
    const wrapper = mount(UsMarketsResearchCard, { props: { view } })
    cleanup.push(() => wrapper.unmount())
    const text = wrapper.text()
    expect(text).toContain('research_only')
    expect(text).toContain('不进入评分/分级/邮件')
    expect(wrapper.get('[data-testid="us-row-us-cpo-optical-broad-ew"]').text()).toContain('+10.36%')
    expect(wrapper.get('[data-testid="us-row-us-cpo-optical-broad-ew"]').text()).toContain('极高')
    expect(wrapper.get('[data-testid="us-row-us-cpo-optical-broad-ew"]').text()).toContain('未计算')
    expect(wrapper.get('[data-testid="us-row-us-sp500"]').text()).toContain('-3.29%')
    expect(wrapper.get('[data-testid="us-row-us-nasdaq-composite"]').text()).toContain('provider_returned_no_data')
    expect(wrapper.get('[data-testid="us-markets-provisional"]').text()).toContain('LITE 2026-11-13')
    expect(wrapper.get('[data-testid="us-markets-failed"]').text()).toContain('SNDK')
    expect(wrapper.get('[data-testid="us-markets-source"]').text()).toContain('非官方免费源')
    // group order follows `order`, not array order
    expect(wrapper.findAll('h3').map(h => h.text())).toEqual(['美股 CPO / 光模块', '美股指数'])
    expect(wrapper.findAll('svg.us-spark').length).toBe(2)
    expect(wrapper.get('[data-testid="us-details-us-cpo-optical-broad-ew"]').text()).toContain('本次未取得行情')
  })

  it('is honest when unpublished, stale or failed; never fills data', () => {
    const none = mount(UsMarketsResearchCard, { props: { view: { availability: 'unpublished', available: false, reason: 'us_markets_research_not_published', research: null } } })
    expect(none.get('[data-testid="us-markets-note"]').text()).toContain('尚未发布')
    expect(none.find('table').exists()).toBe(false)
    const stale = mount(UsMarketsResearchCard, { props: { view: { ...view, source_stale: true, source_age_days: 12 } } })
    expect(stale.get('[data-testid="us-markets-stale"]').text()).toContain('12 天')
    const failed = mount(UsMarketsResearchCard, { props: { view: null, error: '请求超时' } })
    expect(failed.get('[data-testid="us-markets-note"]').text()).toContain('读取失败')
    for (const w of [none, stale, failed]) w.unmount()
  })
})

describe('Overview integration', () => {
  beforeEach(() => { vi.mocked(api).mockReset(); vi.stubGlobal('scrollTo', vi.fn()); Object.defineProperty(document, 'hidden', { configurable: true, value: false }) })

  async function open(local = true) {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: Overview }, { path: '/etf/:code', component: { template: '<div />' } }, { path: '/analysis', component: { template: '<div />' } }, { path: '/settings', component: { template: '<div />' } }] })
    const paths: string[] = []
    vi.mocked(api).mockImplementation(async (path: string) => {
      paths.push(path)
      if (path.includes('/overview?')) return local ? { generation: 7, research_source: 'local_bundle' } : {}
      if (path.includes('/us-markets-research')) return view
      if (path.includes('/market-context')) return { latest_view: [] }
      return {}
    })
    await router.push('/'); await router.isReady()
    const wrapper = mount(Overview, { global: { plugins: [createPinia(), router], stubs: { OriginalDecisionBoard: { template: '<div />', methods: { reload() {}, refresh() {} } }, DataHealth: true, OutlookPanel: true, TaskProgress: true, EtfChart: true } } })
    cleanup.push(() => wrapper.unmount())
    await flushPromises()
    return { wrapper, paths }
  }

  it('pins the research read to the overview generation and renders the card', async () => {
    const { wrapper, paths } = await open(true)
    expect(paths.some(p => p.includes('/us-markets-research') && p.includes('generation=7'))).toBe(true)
    expect(wrapper.find('[data-testid="us-markets-research-card"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="us-row-us-sp500"]').text()).toContain('7,561.67')
  })
})

describe('independent research page', () => {
  it('renders the same research block on /research with pinned generation', async () => {
    const Research = (await import('../src/views/Research.vue')).default
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/research', component: Research }, { path: '/settings', component: { template: '<div />' } }] })
    const paths: string[] = []
    vi.mocked(api).mockReset()
    vi.mocked(api).mockImplementation(async (path: string) => {
      paths.push(path)
      return path.includes('/overview?') ? { research_source: 'local_bundle', generation: 11 } : view
    })
    await router.push('/research'); await router.isReady()
    const wrapper = mount(Research, { global: { plugins: [createPinia(), router], stubs: { ResearchPanel: true, AISetupGuide: true, ManualReview: true } } })
    cleanup.push(() => wrapper.unmount())
    await flushPromises()
    expect(paths.some(p => p.includes('/us-markets-research') && p.includes('generation=11'))).toBe(true)
    expect(wrapper.find('[data-testid="us-markets-research-section"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('标普 500')
  })

  it('never requests an unpinned local research batch if overview generation is missing', async () => {
    const Section = (await import('../src/components/UsMarketsResearchSection.vue')).default
    const paths: string[] = []
    vi.mocked(api).mockReset()
    vi.mocked(api).mockImplementation(async (path: string) => { paths.push(path); return { research_source: 'local_bundle' } })
    const wrapper = mount(Section)
    cleanup.push(() => wrapper.unmount())
    await flushPromises()
    expect(paths.filter(p => p.includes('/us-markets-research'))).toEqual([])
  })

  it('explains excluded provisional data and current-membership bias', () => {
    const wrapper = mount(UsMarketsResearchCard, { props: { view: { ...view, research: { ...view.research, membership_warning: '非历史时点成分表', excluded_provisional_observations: [{ticker:'LITE',date:'2026-11-13'}] } } } })
    expect(wrapper.get('[data-testid="us-excluded-provisional"]').text()).toContain('不参与收益/ATR')
    expect(wrapper.get('[data-testid="us-membership-warning"]').text()).toContain('非历史时点')
    wrapper.unmount()
  })
})


describe('production router US research entry', () => {
  it('resolves and renders /research/us-markets without the legacy research redirect', async () => {
    const { makeRouter } = await import('../src/routerFactory')
    const { RouterView } = await import('vue-router')
    const router = makeRouter(createMemoryHistory())
    vi.stubGlobal('scrollTo', vi.fn())
    vi.mocked(api).mockReset()
    vi.mocked(api).mockImplementation(async (path:string) => path.includes('/overview?') ? {research_source:'local_bundle',generation:23} : view)
    await router.push('/research/us-markets'); await router.isReady()
    const wrapper=mount(RouterView,{global:{plugins:[createPinia(),router]}})
    cleanup.push(()=>wrapper.unmount())
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/research/us-markets')
    expect(wrapper.find('h1').text()).toBe('美股市场研究')
    expect(wrapper.find('[data-testid="us-markets-research-section"]').exists()).toBe(true)
    expect(vi.mocked(api).mock.calls.some(([p])=>p.includes('us-markets-research') && p.includes('generation=23'))).toBe(true)
  })
})
