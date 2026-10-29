import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import Overview from '../src/views/Overview.vue'
import { api } from '../src/lib/api'

vi.mock('../src/lib/api', () => ({ api: vi.fn(), errorText: (error: Error) => error.message }))
const cleanup: Array<() => void> = []
const item = { context_id: 'cn-csi300', context_kind: 'index', label: '沪深300', observed_value: 4000,
  source: 'fixture', source_timestamp: '2026-10-09T15:00:00+08:00', freshness: 'historical' }
const local = { read_contract: 'local-display-context-read-v1', research_source: 'local_bundle',
  generation: 7, generated_at: '2026-10-12T06:30:00Z', expires_at: '2026-10-12T08:30:00Z',
  read_at: '2026-10-12T09:00:00Z', source_as_of: '2026-10-09', is_stale: true, is_expired: true,
  index_history_available: false, provider_called: false, actionable: false }

async function openOverview(context: Record<string, unknown>, options: { local?: boolean; missingGeneration?: boolean } = { local: true }) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: Overview }, { path: '/etf/:code', component: { template: '<div />' } },
    { path: '/analysis', component: { template: '<div />' } }, { path: '/settings', component: { template: '<div />' } },
  ] })
  vi.mocked(api).mockImplementation(async (path: string, init?: unknown) => {
    if (path.includes('/overview?')) return options.local ? { generation: options.missingGeneration ? undefined : 7, research_source: 'local_bundle' } : {}
    if (path.includes('/market-context')) return context
    if (path.includes('/hs300-ratio')) return options.local ? { status: 'unavailable', reason: 'research_ratio_not_published', items: [] } : { status: 'available', items: [{ numerator_basis: 'market_value_at_close', ratio: 0.005, trade_date: '2026-10-29', lag_days: 0 }] }
    if (path.includes('/indexes/') && path.includes('/chart?')) return { available: true, bars: [], summary: { price: 4000 } }
    if (path.includes('/indexes?') || path.endsWith('/indexes')) return options.local ? { ...local, items: [] } : { items: [] }
    if (path.includes('/data-jobs') && init) return { job: { job_id: 'fixture-job' } }
    return {}
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(Overview, { global: { plugins: [createPinia(), router], stubs: {
    OriginalDecisionBoard: { props: ['ready'], template: '<div data-testid="decision-board-stub" :data-ready="ready" />', methods: { reload() {}, refresh() {} } }, DataHealth: true, OutlookPanel: true, TaskProgress: true,
    EtfChart: { template: '<div data-testid="index-chart">fixture chart</div>' },
  } } })
  cleanup.push(() => wrapper.unmount())
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.mocked(api).mockReset()
  vi.stubGlobal('scrollTo', vi.fn())
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
})
afterEach(() => { cleanup.splice(0).forEach(unmount => unmount()); vi.unstubAllGlobals() })

describe('published market context on the overview', () => {
  it('distinguishes a historical identity from an expired bundle', async () => {
    const { wrapper } = await openOverview({ ...local, availability: 'available', latest_view: [item],
      historical_identity: true, is_expired: false })
    const status = wrapper.get('[data-testid="market-context-status"]')
    expect(status.text()).toContain('历史版本')
    expect(status.text()).not.toContain('已过期')
  })

  it('does not issue unpinned context reads when a local overview has no generation', async () => {
    const { wrapper } = await openOverview({ ...local, latest_view: [item] }, { local: true, missingGeneration: true })
    expect(wrapper.text()).toContain('尚无可消费批次')
    expect(wrapper.get('[data-testid="decision-board-stub"]').attributes('data-ready')).toBe('false')
    expect(vi.mocked(api).mock.calls.some(([path]) => /\/workspace\/(market-context|indexes|sectors)/.test(path))).toBe(false)
  })

  it('shows read failures beside retained context values', async () => {
    const { wrapper } = await openOverview({ ...local, availability: 'carried_forward', latest_view: [item] })
    const implementation = vi.mocked(api).getMockImplementation()!
    vi.mocked(api).mockImplementation(async (path, init) => {
      if (path.includes('/market-context')) throw new Error('fixture read failed')
      return implementation(path, init)
    })
    await wrapper.get('.page-heading button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="market-context-read-error"]').text()).toContain('fixture read failed')
    expect(wrapper.get('.market-context-card').text()).toContain('4,000.00')
  })

  it.each([
    ['unavailable', 'optional_refresh_failed', '本次更新失败'],
    ['unpublished', 'market_context_not_published', '本批次未发布'],
    ['partial', 'coverage_incomplete', '部分数据'],
    ['carried_forward', 'fast_slot_reuses_same_day_refresh', '沿用既有数据'],
  ])('shows %s separately from bundle expiry and all timestamps', async (availability, reason, label) => {
    const { wrapper } = await openOverview({ ...local, availability, reason, latest_view: [],
      refreshed_at: '2026-10-12T01:30:00Z', refreshed_in_slot: false })
    const status = wrapper.get('[data-testid="market-context-status"]')
    expect(status.text()).toContain(label)
    expect(status.text()).toContain('已过期')
    expect(status.text()).toContain('批次 7')
    expect(status.text()).toContain('来源日期 2026-10-09')
    expect(status.text()).toContain('生成 10/12 14:30')
    expect(status.text()).toContain('上下文更新 10/12 09:30')
    expect(status.text()).toContain('读取 10/12 17:00')
    expect(wrapper.text()).not.toContain('待同步')
  })

  it('keeps source dates and suppresses unsupported history and writer actions in local mode', async () => {
    const { wrapper } = await openOverview({ ...local, availability: 'carried_forward', latest_view: [item] })
    const card = wrapper.get('.market-context-card')
    expect(card.text()).toContain('2026-10-09')
    expect(card.text()).toContain('本地展示包未发布指数历史')
    expect(card.attributes('role')).not.toBe('button')
    await card.trigger('click')
    await card.trigger('keydown.enter')
    await flushPromises()
    expect(wrapper.find('.market-context-detail').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('下载指数历史')
    expect(wrapper.text()).not.toContain('同步市场目录与板块')
    expect(wrapper.text()).not.toContain('重算已存历史指标')
    expect(wrapper.text()).not.toContain('预览历史准备清单')
    expect(vi.mocked(api).mock.calls.some(([path]) => path.includes('/indexes/') && path.includes('/chart'))).toBe(false)
    expect(vi.mocked(api).mock.calls.some(([, init]) => (init as { method?: string })?.method === 'POST')).toBe(false)
    const contextRead = vi.mocked(api).mock.calls.find(([path]) => path.includes('/market-context'))![0]
    expect(new URL(contextRead, 'http://localhost').searchParams.get('generation')).toBe('7')
  })

  it('retains proxy ETF navigation with its generation in local mode', async () => {
    const { wrapper, router } = await openOverview({ ...local, latest_view: [
      { ...item, context_kind: 'tradable_proxy', is_tradable_proxy: true, display_code: '510300.SH' },
    ] })
    await wrapper.get('.market-context-card').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/etf/510300.SH?generation=7')
  })

  it('keeps database/mockdemo index history and its download action', async () => {
    const { wrapper } = await openOverview({ latest_view: [item] }, { local: false })
    expect(wrapper.get('.market-context-card').attributes('role')).toBe('button')
    await wrapper.get('.market-context-card').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="index-chart"]').text()).toContain('fixture chart')
    const download = wrapper.findAll('button').find(button => button.text() === '下载指数历史')!
    expect(download.exists()).toBe(true)
    await download.trigger('click')
    await flushPromises()
    expect(vi.mocked(api).mock.calls.some(([path, init]) => path.includes('/data-jobs') &&
      (init as { body?: { task?: string } })?.body?.task === 'index_history')).toBe(true)
  })

  it('renders the research-only HS300 ratio card without affecting decisions', async () => {
    const { wrapper } = await openOverview({ latest_view: [item] }, { local: false })
    const card = wrapper.get('[data-testid="hs300-ratio-card"]')
    expect(card.text()).toContain('沪深300 被动配置比例')
    expect(card.text()).toContain('0.500%')
    expect(card.text()).toContain('收盘口径')
    expect(card.text()).toContain('不进入评分或仓位')
  })
})
