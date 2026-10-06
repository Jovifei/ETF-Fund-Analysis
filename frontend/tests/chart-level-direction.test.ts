import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { ChartData, SupportLevel } from '../src/lib/types'

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
const knownCases = [
  { name: 'canonical support', fields: { kind: 'support' }, label: '支撑', color: '#4dba90', css: 'bear' },
  { name: 'canonical resistance', fields: { kind: 'resistance' }, label: '压力', color: '#f3737c', css: 'bull' },
  { name: 'type-only support', fields: { type: 'support' }, label: '支撑', color: '#4dba90', css: 'bear' },
  { name: 'type-only resistance', fields: { type: 'resistance' }, label: '压力', color: '#f3737c', css: 'bull' },
  { name: 'support kind wins conflict', fields: { kind: 'support', type: 'resistance' }, label: '支撑', color: '#4dba90', css: 'bear' },
  { name: 'resistance kind wins conflict', fields: { kind: 'resistance', type: 'support' }, label: '压力', color: '#f3737c', css: 'bull' },
  { name: 'null kind is absent', fields: { kind: null, type: 'support' }, label: '支撑', color: '#4dba90', css: 'bear' },
]
const unknownCases = [
  { name: 'missing direction', fields: {} },
  { name: 'unrecognized kind blocks alias', fields: { kind: 'unknown', type: 'support' } },
  { name: 'empty kind blocks alias', fields: { kind: '', type: 'support' } },
  { name: 'non-string kind blocks alias', fields: { kind: 0, type: 'support' } },
  { name: 'unsupported is not support', fields: { kind: 'unsupported' } },
  { name: 'support_unknown is not support', fields: { type: 'support_unknown' } },
  { name: 'ambiguous type is not support', fields: { type: 'support_resistance' } },
  { name: 'invalid resistance type is unknown', fields: { type: 'resistance_unknown' } },
]

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.unstubAllGlobals() })

async function chart(fields: Record<string, unknown>, extra: Partial<ChartData> = {}) {
  const level = { price: 2.2, zone_low: 2.1, zone_high: 2.3, groups: ['PIVOT'], methods: ['确认分形低点'], ...fields } as SupportLevel
  const data: ChartData = {
    ts_code: 'TEST.SH', interval: '1d', available: true, sr_overlay_allowed: true,
    qualification: 'UNKNOWN', support_resistance: { qualified: false, levels: [level] },
    bars: [{ date: '2026-09-01', open: 2.5, high: 3, low: 2, close: 2.5, volume: null, amount: null, indicators: {} }],
    ...extra,
  }
  const before = JSON.stringify(data)
  const wrapper = mount(EtfChart, { props: { data }, attachTo: document.body })
  wrappers.push(wrapper)
  await flushPromises()
  expect(JSON.stringify(data)).toBe(before)
  expect(data.qualification).toBe('UNKNOWN')
  return wrapper
}
function zone() {
  return mocked.chart.createOverlay.mock.calls.map(call => call[0]).filter(item => item.name === 'researchZone').at(-1)
}
function expectGeometryAndColor(label: string, color: string) {
  const overlay = zone()
  expect(overlay).toBeDefined()
  expect(overlay.points.map((point: { value: number }) => point.value)).toEqual([2.1, 2.3, 2.2])
  expect(overlay.extendData.label).toBe(`${label} 2.200 · 确认分形低点`)
  expect(overlay.extendData.color).toBe(color)
  const line = mocked.chart.createOverlay.mock.calls.map(call => call[0]).filter(item => item.name === 'priceLine').at(-1)
  expect(line.points[0].value).toBe(2.2)
  expect(line.styles.line.color).toBe(color)
}

describe('support/resistance direction is identical on the canvas, legend and evidence', () => {
  it.each(knownCases)('$name', async ({ fields, label, color, css }) => {
    const wrapper = await chart(fields)
    expectGeometryAndColor(label, color)
    const legend = wrapper.get('[aria-label="当前支撑压力快照价位"] span')
    expect(legend.text()).toBe(`${label} 2.200`)
    expect(legend.classes()).toContain(css)
    expect(wrapper.get('[data-testid="chart-level-evidence"] li').text()).toBe(`${label} 2.200 · 确认分形低点`)
  })

  it.each(unknownCases)('$name keeps numbers neutral and does not infer a side', async ({ fields }) => {
    const wrapper = await chart(fields)
    expectGeometryAndColor('方向未知', '#94a3b8')
    const legend = wrapper.get('[aria-label="当前支撑压力快照价位"] span')
    expect(legend.text()).toBe('方向未知 2.200')
    expect(legend.classes()).not.toContain('bull')
    expect(legend.classes()).not.toContain('bear')
    expect(wrapper.get('[data-testid="chart-level-evidence"] li').text()).toBe('方向未知 2.200 · 确认分形低点')
  })

  it('preserves the snapshot/basis drawing gate even for a recognized alias', async () => {
    const wrapper = await chart({ type: 'support' }, { sr_overlay_allowed: false })
    expect(zone()).toBeUndefined()
    expect(wrapper.find('[aria-label="当前支撑压力快照价位"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="chart-level-evidence"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="chart-sr-toggle"]').attributes('disabled')).toBeDefined()
  })

  it('uses the same direction only after switching to the allowed research basis', async () => {
    const wrapper = await chart({ type: 'support' }, {
      basis_transition: true, raw_overlay_allowed: false, sr_overlay_allowed: false,
      research_sr_overlay_allowed: true,
      research_bars: [{ date: '2026-09-01', open: 2.5, high: 3, low: 2, close: 2.5, volume: null, amount: null, indicators: {} }],
      research_support_resistance: { qualified: false, levels: [{
        price: 2.2, zone_low: 2.1, zone_high: 2.3, type: 'support', groups: ['PIVOT'], methods: ['确认分形低点'],
      }] },
    })
    expect(zone()).toBeUndefined()
    expect(wrapper.find('[aria-label="当前支撑压力快照价位"]').exists()).toBe(false)
    await wrapper.get('[data-testid="chart-basis-research"]').trigger('click')
    await flushPromises()
    expectGeometryAndColor('支撑', '#4dba90')
    expect(wrapper.get('[aria-label="当前支撑压力快照价位"] span').text()).toBe('支撑 2.200')
    expect(wrapper.get('[data-testid="chart-level-evidence"] li').text()).toBe('支撑 2.200 · 确认分形低点')
    mocked.chart.createOverlay.mockClear()
    await wrapper.get('[data-testid="chart-basis-raw"]').trigger('click')
    await flushPromises()
    expect(zone()).toBeUndefined()
    expect(wrapper.find('[data-testid="chart-level-evidence"]').exists()).toBe(false)
  })

  it('retains matching type-only evidence through expand, hide/show and close', async () => {
    const wrapper = await chart({ type: 'support' })
    await wrapper.get('[data-testid="chart-fullscreen"]').trigger('click')
    await flushPromises()
    expect(wrapper.attributes('role')).toBe('dialog')
    await wrapper.get('[data-testid="chart-sr-toggle"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="chart-level-evidence"]').exists()).toBe(false)
    await wrapper.get('[data-testid="chart-sr-toggle"]').trigger('click')
    await flushPromises()
    expectGeometryAndColor('支撑', '#4dba90')
    expect(wrapper.get('[data-testid="chart-level-evidence"] li').text()).toBe('支撑 2.200 · 确认分形低点')
    await wrapper.get('[data-testid="chart-fullscreen"]').trigger('click')
    await flushPromises()
    expect(wrapper.attributes('role')).toBeUndefined()
    expect(wrapper.get('[aria-label="当前支撑压力快照价位"] span').text()).toBe('支撑 2.200')
  })
})
