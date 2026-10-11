import projected from './shadow-chart-projection.json'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { ChartBar, ChartData } from '../src/lib/types'

// Exercise the real component projection and adapter; only the canvas library is mocked.
const mocked = vi.hoisted(() => ({ chart: {
  setPriceVolumePrecision: vi.fn(), applyNewData: vi.fn(), createIndicator: vi.fn(),
  createOverlay: vi.fn(), subscribeAction: vi.fn(), unsubscribeAction: vi.fn(),
  setBarSpace: vi.fn(), scrollToRealTime: vi.fn(), resize: vi.fn(),
  removeIndicator: vi.fn(), removeOverlay: vi.fn(),
} }))
vi.mock('klinecharts', () => ({
  init: () => mocked.chart, dispose: vi.fn(), registerIndicator: vi.fn(),
  registerOverlay: vi.fn(), ActionType: { OnCrosshairChange: 'crosshair' },
}))
import EtfChart from '../src/components/EtfChart.vue'

const wrappers: ReturnType<typeof mount>[] = []
const bar = (date: string, close: number, volume: number): ChartBar => ({
  date, open: close - 0.1, high: close + 0.2, low: close - 0.2, close,
  volume, amount: volume * close, indicators: { ma5: close },
})
function splitChart(extra: Partial<ChartData> = {}): ChartData {
  return {
    ts_code: '512480.SH', interval: '1d', available: true, adjust: 'none', qualification: 'UNKNOWN',
    bars: [bar('2026-09-01', 10, 100), bar('2026-09-02', 12, 120)],
    research_bars: [bar('2026-09-01', 5, 100), bar('2026-09-02', 6, 120)],
    basis_transition: true, raw_overlay_allowed: false, sr_overlay_allowed: false,
    // Trend geometry does not require horizontal support/resistance levels.
    research_sr_overlay_allowed: false, research_support_resistance: { levels: [] },
    support_resistance: null, cost_overlay_allowed: true, research_cost_overlay_allowed: false,
    studies: { levels: [], trend_lines: [{
      start_date: '2026-09-01', end_date: '2026-09-02', start_price: 5, end_price: 6,
    }] },
    ...extra,
  }
}
async function chart(data = splitChart()) {
  const wrapper = mount(EtfChart, { props: { data } })
  wrappers.push(wrapper)
  await flushPromises()
  expect(wrapper.text()).not.toContain('图表初始化失败')
  return wrapper
}
function bars(): ChartBar[] { return mocked.chart.applyNewData.mock.calls.at(-1)?.[0] ?? [] }
function overlays() { return mocked.chart.createOverlay.mock.calls.map(call => call[0]) }
function trends() { return overlays().filter(item => item.name === 'segment') }
function expectTrend() {
  expect(trends()).toHaveLength(1)
  expect(trends()[0].points).toEqual([
    { timestamp: Date.parse('2026-09-01T07:00:00Z'), value: 5 },
    { timestamp: Date.parse('2026-09-02T07:00:00Z'), value: 6 },
  ])
  expect(trends()[0].styles.line.style).toBe('dashed')
}
async function basis(wrapper: ReturnType<typeof mount>, target: 'raw' | 'research') {
  mocked.chart.createOverlay.mockClear()
  mocked.chart.createIndicator.mockClear()
  await wrapper.get(`[data-testid="chart-basis-${target}"]`).trigger('click')
  await flushPromises()
}
async function all(wrapper: ReturnType<typeof mount>) {
  const button = wrapper.findAll('button').find(item => item.text() === '打开全部')!
  await button.trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.unstubAllGlobals() })

describe('public shadow chart consumer', () => {
  it('supports research basis, indicators and SR with private cost disabled', async () => {
    const data = projected as unknown as ChartData
    const wrapper = await chart(data)
    expect(wrapper.find('[data-testid="chart-basis-research"]').exists()).toBe(true)
    await basis(wrapper, 'research')
    expect(bars().map(item => item.close)).toEqual([5, 6])
    expect(wrapper.get('[data-testid="chart-sr-toggle"]').attributes('disabled')).toBeUndefined()
    expect(bars()[0].indicators?.ma5).toBe(5)
    expect(wrapper.find('[data-testid="chart-cost-label"]').exists()).toBe(false)
  })
})
