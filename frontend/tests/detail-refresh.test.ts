import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Detail from '../src/views/Detail.vue'
import { api } from '../src/lib/api'

vi.mock('../src/lib/api', () => ({ api: vi.fn(), errorText: () => 'error' }))
const cleanup: Array<() => void> = []
let detailReads = 0

const detail = {
  instrument: { ts_code: '510300.SH', name: '沪深300ETF', kind: 'ETF', theme_l1: '宽基', theme_l2: '沪深300' },
  decision: null, snapshot_id: 'snapshot-1', decision_time: '2026-09-23T10:00:00+08:00', read_as_of: '2026-09-23T10:00:01+08:00',
  quote: { price: 4, change_ratio: 0, status: 'recent_observation', source_time: '2026-09-23T10:00:00+08:00', fetched_at: '2026-09-23T10:00:01+08:00', source: 'fixture' },
  availability: {
    instrument: { status: 'active', reason_code: null }, price: { status: 'available', reason_code: null },
    history: { status: 'available', reason_code: null }, price_basis: { status: 'aligned', reason_code: null },
    indicators: { status: 'unavailable', reason_code: 'indicator_values_unavailable' },
    volume: { status: 'unavailable', reason_code: 'volume_missing_or_unverified' },
    forecasts: { status: 'unavailable', reason_code: 'forecast_not_generated' }, decision: { status: 'unavailable', reason_code: 'decision_not_generated' },
  },
  decision_explanation: { conclusion: null, primary_basis: null, comparison: { status: 'unavailable', reason_code: 'decision_not_generated' }, evidence_caveats: ['decision_not_generated', 'forecast_not_generated'], computed_at: null, actionable: false },
  indicator_values: {}, indicator_version: null, indicator_as_of: null, forecasts: {},
  support_resistance: null, holding: null, forecast_scenario: null,
}
const chart = { ts_code: '510300.SH', interval: '1d', available: true, bars: [], reason: 'fixture', adjust: 'none', display_price_basis: 'source_adjustment:none', research_price_basis: 'source_adjustment:none', input_hash: 'input-fixture', series_id: 'series-fixture', indicator_basis: 'fixture-basis', computed_at: '2026-09-23T10:00:02+08:00', source_as_of: '2026-09-23', as_of: '2026-09-23T10:00:01+08:00' }

async function openDetail(pageStateStub = true) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/etf/:code', component: Detail },
      { path: '/holdings', component: { template: '<div />' } },
    ],
  })
  await router.push('/etf/510300.SH')
  await router.isReady()
  const stubs = {
    PageState: pageStateStub ? { template: '<div><slot /></div>' } : false,
    Badge: true, FavoriteButton: true,
    EtfChart: { props: ['data'], template: '<div data-testid="chart-as-of">{{data.as_of}}</div>' },
    HistoryLoader: true, IndicatorReadings: true, OutlookPanel: true, ResearchPanel: true,
  }
  const wrapper = mount(Detail, {
    global: {
      plugins: [router],
      stubs,
    },
  })
  cleanup.push(() => wrapper.unmount())
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(api).mockClear()
  detailReads = 0
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  vi.mocked(api).mockImplementation(async (path: string) => {
    if (path.includes('/chart?')) return { ...chart, as_of: new URL(path, 'http://localhost').searchParams.get('as_of') }
    detailReads += 1
    return { ...detail, read_as_of: `2026-09-23T10:00:${String(detailReads).padStart(2, '0')}+08:00` }
  })
})

afterEach(() => {
  cleanup.splice(0).forEach(unmount => unmount())
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('detail data refresh lifecycle', () => {
  it('shows source, fetch, calculation and snapshot times as separate fields', async () => {
    const wrapper = await openDetail()
    const freshness = wrapper.get('[data-testid="detail-freshness"]')
    expect(freshness.text()).toContain('10:00:00')
    expect(freshness.text()).toContain('10:00:01')
    expect(freshness.text()).toContain('10:00:02')
    expect(freshness.text()).toContain('snapshot-1')
    expect(freshness.text()).toContain('fixture-basis')
    expect(freshness.text()).toContain('source_adjustment:none')
  })

  it('pins chart reads to the detail response time', async () => {
    const wrapper = await openDetail()
    const chartRequest = vi.mocked(api).mock.calls.map(([path]) => String(path)).find(path => path.includes('/chart?'))
    expect(chartRequest).toBeTruthy()
    expect(new URL(chartRequest!, 'http://localhost').searchParams.get('as_of')).toBe('2026-09-23T10:00:01+08:00')
    expect(wrapper.get('[data-testid="chart-as-of"]').text()).toBe('2026-09-23T10:00:01+08:00')
  })

  it('explains a missing decision without hiding an available price', async () => {
    const wrapper = await openDetail()
    expect(wrapper.get('.page-heading').text()).toContain('研究决策未生成')
    expect(wrapper.get('[data-testid="decision-explanation"]').text()).toContain('当前没有生成研究决策快照')
    expect(wrapper.text()).toContain('4.000')
    expect(wrapper.text()).toContain('当前没有可用预测')
  })

  it('labels a disabled catalog item while preserving its available quote', async () => {
    const implementation = vi.mocked(api).getMockImplementation()!
    vi.mocked(api).mockImplementation(async path => {
      if (path.includes('/chart?')) return implementation(path)
      const value = await implementation(path) as typeof detail
      return { ...value, instrument: { ...detail.instrument, enabled: false }, availability: {
        ...detail.availability, instrument: { status: 'disabled', reason_code: 'instrument_disabled' },
      } }
    })
    const wrapper = await openDetail()
    expect(wrapper.text()).toContain('该标的未启用研究池')
    expect(wrapper.text()).toContain('4.000')
  })

  it('explains an empty history without replacing price with a fake candle', async () => {
    const implementation = vi.mocked(api).getMockImplementation()!
    vi.mocked(api).mockImplementation(async path => {
      if (path.includes('/chart?')) return { ...chart, available: false, bars: [], reason: 'history_not_prepared', as_of: new URL(path, 'http://localhost').searchParams.get('as_of') }
      const value = await implementation(path) as typeof detail
      return { ...value, availability: { ...detail.availability, history: { status: 'unavailable', reason_code: 'history_not_prepared' } } }
    })
    const wrapper = await openDetail()
    expect(wrapper.text()).toContain('尚未准备历史行情')
    expect(wrapper.text()).toContain('4.000')
    expect(wrapper.text()).not.toContain('0.000')
  })

  it('re-reads quote and chart after one visible refresh interval', async () => {
    const wrapper = await openDetail()
    expect(api).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(60_000)
    await flushPromises()
    expect(api).toHaveBeenCalledTimes(4)
  })

  it('stops while hidden and refreshes immediately when visible again', async () => {
    const wrapper = await openDetail()
    expect(api).toHaveBeenCalledTimes(2)
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(120_000)
    expect(api).toHaveBeenCalledTimes(2)
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(api).toHaveBeenCalledTimes(4)
  })

  it('keeps the last detail visible when a background refresh fails', async () => {
    const implementation = vi.mocked(api).getMockImplementation()!
    let failDetail = false
    vi.mocked(api).mockImplementation(async path => {
      if (failDetail && !path.includes('/chart?')) throw new Error('detail unavailable')
      return implementation(path)
    })
    const wrapper = await openDetail(false)
    failDetail = true
    await vi.advanceTimersByTimeAsync(60_000)
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toContain('详情刷新失败')
    expect(wrapper.text()).toContain('4.000')
  })

  it('shows chart request errors inside the chart while keeping quote details visible', async () => {
    const implementation = vi.mocked(api).getMockImplementation()!
    vi.mocked(api).mockImplementation(async path => {
      if (path.includes('/chart?')) throw new Error('chart unavailable')
      return implementation(path)
    })
    const wrapper = await openDetail(false)

    expect(wrapper.get('[role="alert"]').text()).toContain('暂时无法载入')
    expect(wrapper.text()).toContain('4.000')
  })

  it('clears the refresh schedule after the detail page unmounts', async () => {
    const wrapper = await openDetail()
    expect(api).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(120_000)
    expect(api).toHaveBeenCalledTimes(2)
  })
})
