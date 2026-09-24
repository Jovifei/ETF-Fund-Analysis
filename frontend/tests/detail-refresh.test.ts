import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Detail from '../src/views/Detail.vue'
import { api } from '../src/lib/api'

vi.mock('../src/lib/api', () => ({ api: vi.fn(), errorText: () => 'error' }))
const cleanup: Array<() => void> = []

const detail = {
  instrument: { ts_code: '510300.SH', name: '沪深300ETF', kind: 'ETF', theme_l1: '宽基', theme_l2: '沪深300' },
  decision: null, snapshot_id: 'snapshot-1', decision_time: '2026-09-23T10:00:00+08:00',
  quote: { price: 4, change_ratio: 0, status: 'recent_observation', source_time: '2026-09-23T10:00:00+08:00', fetched_at: '2026-09-23T10:00:01+08:00', source: 'fixture' },
  indicator_values: {}, indicator_version: null, indicator_as_of: null, forecasts: {},
  support_resistance: null, holding: null, forecast_scenario: null,
}
const chart = { ts_code: '510300.SH', interval: '1d', available: false, bars: [], reason: 'fixture', adjust: 'none', indicator_basis: 'fixture-basis', computed_at: '2026-09-23T10:00:02+08:00', source_as_of: '2026-09-23' }

async function openDetail() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/etf/:code', component: Detail },
      { path: '/holdings', component: { template: '<div />' } },
    ],
  })
  await router.push('/etf/510300.SH')
  await router.isReady()
  const wrapper = mount(Detail, {
    global: {
      plugins: [router],
      stubs: {
        PageState: { template: '<div><slot /></div>' },
        Badge: true, FavoriteButton: true, EtfChart: true, HistoryLoader: true,
        IndicatorReadings: true, OutlookPanel: true, ResearchPanel: true,
      },
    },
  })
  cleanup.push(() => wrapper.unmount())
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(api).mockClear()
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  vi.mocked(api).mockImplementation(async (path: string) =>
    path.includes('/chart?') ? chart : detail,
  )
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
    expect(freshness.text()).toContain('none')
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

  it('clears the refresh schedule after the detail page unmounts', async () => {
    const wrapper = await openDetail()
    expect(api).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(120_000)
    expect(api).toHaveBeenCalledTimes(2)
  })
})
