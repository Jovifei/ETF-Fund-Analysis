import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import EtfChart from '../src/components/EtfChart.vue'

const adapterState = vi.hoisted(() => ({ data: [] as Array<Record<string, any>> }))
vi.mock('../src/lib/chartAdapter', () => ({
  ChartAdapter: class {
    chart = { resize: vi.fn() }
    constructor(_host: HTMLElement, data: Record<string, any>) { adapterState.data.push(data) }
    destroy() {}
    setIndicatorSelection() {}
    setStudySelection() {}
    range() {}
    reset() {}
  },
  groupsForLevel: () => [],
}))
vi.mock('../src/lib/chartStudies', () => ({
  serverStudies: [], studyAvailable: () => true, volumeAvailable: () => false,
}))

const bar = (close: number, indicators: Record<string, number | null>) => ({
  date: '2026-09-23', open: close, high: close, low: close, close,
  volume: null, amount: null, indicators,
})

afterEach(() => { adapterState.data = [] })

describe('raw and research chart price bases', () => {
  it('starts on raw candles and switches to the matching research-price series', async () => {
    const wrapper = mount(EtfChart, { props: { data: {
      ts_code: '512480.SH', interval: '1d', available: true, adjust: 'none',
      bars: [bar(2, {})], research_bars: [bar(1, { ma5: 1 })],
      basis_transition: true, raw_overlay_allowed: false, sr_overlay_allowed: false,
      research_sr_overlay_allowed: true, research_support_resistance: { levels: [{ price: 1 }] },
      support_resistance: null, cost_overlay_allowed: true, research_cost_overlay_allowed: false,
    } } })
    await flushPromises()

    expect(adapterState.data.at(-1)?.bars[0].close).toBe(2)
    expect(wrapper.get('[data-testid="chart-basis-raw"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.text()).toContain('原始行情按来源数值显示')
    await wrapper.get('[data-testid="chart-basis-research"]').trigger('click')
    await flushPromises()

    expect(adapterState.data.at(-1)?.bars[0].close).toBe(1)
    expect(adapterState.data.at(-1)?.sr_overlay_allowed).toBe(true)
    expect(adapterState.data.at(-1)?.cost_overlay_allowed).toBe(false)
    expect(wrapper.text()).toContain('拆分调整研究价格')
  })
})
