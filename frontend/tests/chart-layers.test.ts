import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
vi.mock('klinecharts', () => ({ init: () => ({ setPriceVolumePrecision: vi.fn(), applyNewData: vi.fn(), createIndicator: vi.fn(), createOverlay: vi.fn(), subscribeAction: vi.fn(), unsubscribeAction: vi.fn(), setBarSpace: vi.fn(), scrollToRealTime: vi.fn(), resize: vi.fn(), removeIndicator: vi.fn(), removeOverlay: vi.fn() }), dispose: vi.fn(), registerIndicator: vi.fn(), registerOverlay: vi.fn(), ActionType: { OnCrosshairChange: 'crosshair' } }))
import EtfChart from '../src/components/EtfChart.vue'

const bar = { date: '2026-09-03', open: 2, high: 3, low: 1, close: 2.5, volume: 5, amount: 10, indicators: {} }
beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} }) })

function chart(extra: Record<string, unknown> = {}) {
  return mount(EtfChart, { props: { data: { ts_code: '512480.SH', interval: '1d', available: true, bars: [bar], sr_overlay_allowed: true, support_resistance: { levels: [{ price: 2.2, kind: 'support', methods: ['MACD确认拐点'], groups: ['MACD'] }] }, ...extra } } })
}

describe('research layer copy', () => {
  it('keeps indicator-tagged prices off the legend until that layer is checked', async () => {
    const wrapper = chart()
    await flushPromises()
    expect(wrapper.text()).toContain('缠论笔段中枢')
    expect(wrapper.find('[aria-label="当前支撑压力快照价位"]').exists()).toBe(false)
    await wrapper.get('.study-controls').findAll('label').find(label => label.text() === 'MACD')!.get('input').setValue(true)
    await flushPromises()
    expect(wrapper.get('[aria-label="当前支撑压力快照价位"]').text()).toContain('2.200')
  })

  it('explains a live prior range and a simplified chan overlay', async () => {
    const wrapper = chart({
      price_structures: { qualified: false, interval: '1d', actionable: false, reason: 'snapshot_missing_requires_task', boxes: [], live_prior_range: { kind: 'prior_high_low', qualified: false, actionable: false, persisted: false, window: 20, origin_at: '2026-08-01', valid_until: '2026-09-03', lower: 1.2, upper: 3.4 } },
      studies: { chan_structure: { available: true, actionable: false, bi: [{}], segments: [{}, {}], zhongshu: [{}], disclaimer: '简化' } },
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="chart-box-evidence"]').text()).toContain('前高')
    expect(wrapper.get('[data-testid="chart-box-evidence"]').text()).toContain('不是已审计箱体')
    await wrapper.get('.study-controls').findAll('label').find(label => label.text() === '缠论笔段中枢')!.get('input').setValue(true)
    await flushPromises()
    expect(wrapper.get('[data-testid="chart-chan-note"]').text()).toContain('简化缠论 · 笔 1 · 段 2 · 中枢 1')
    expect(wrapper.get('[data-testid="chart-chan-note"]').text()).toContain('不是完整 CZSC')
  })

  it('labels a persisted Chan observation instead of the simplified count', async () => {
    const wrapper = chart({
      chan_observation: { available: true, drawable: true, fallback_allowed: false, actionable: false, qualified: false, counts: { fx: 4, bi: 1, zs: 1 }, bi: [{}], segments: [], zhongshu: [{}] },
      studies: { chan_structure: { available: true, bi: [{}, {}], segments: [{}], zhongshu: [{}] } },
    })
    await flushPromises()
    await wrapper.get('.study-controls').findAll('label').find(label => label.text() === '缠论笔段中枢')!.get('input').setValue(true)
    await flushPromises()
    expect(wrapper.get('[data-testid="chart-chan-note"]').text()).toContain('已保存缠论 · 分型 4 · 笔 1 · 中枢 1')
    expect(wrapper.get('[data-testid="chart-chan-note"]').text()).toContain('持久化 CZSC')
  })
})
