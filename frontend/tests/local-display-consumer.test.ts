import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { ChartBar, ChartData } from '../src/lib/types'
import projected from './shadow-chart-projection.json'

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
import DecisionSummary from '../src/components/DecisionSummary.vue'

const wrappers: ReturnType<typeof mount>[] = []

describe('local-display-v2 consumer validation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  })

  afterEach(() => {
    wrappers.splice(0).forEach(w => w.unmount())
    vi.unstubAllGlobals()
  })

  it('renders local display chart projection correctly without error', async () => {
    const chartData = projected as unknown as ChartData
    const wrapper = mount(EtfChart, { props: { data: chartData } })
    wrappers.push(wrapper)
    await flushPromises()
    expect(wrapper.text()).not.toContain('图表初始化失败')
    expect(mocked.chart.applyNewData).toHaveBeenCalled()
  })

  it('renders decision summary digest from local bundle payload', async () => {
    const board = {
      rows: [
        { ts_code: '510300.SH', name: '300ETF', grade: '可加仓', price: 4.12, theme_l1: '宽基' },
        { ts_code: '512480.SH', name: '半导体', grade: '减仓', price: 0.88, theme_l1: '科技' },
      ],
      read_contract: 'version_matched',
      sector_timing: {
        version: 'sector-timing-observation-v2',
        evidence_contract: 'sector-evidence-v2-source-percent-cutoff',
        calibration_status: 'not_calibrated',
        digest: {
          headline: '14:30 宽基偏强观察，科技偏弱观察',
          add_themes: ['宽基'],
          reduce_themes: ['科技'],
        },
      },
    }

    const wrapper = mount(DecisionSummary, {
      props: {
        board,
        filter: '',
        horizon: 1,
      },
      global: {
        stubs: {
          RouterLink: true,
        },
      },
    })
    wrappers.push(wrapper)
    await flushPromises()
    expect(wrapper.text()).toContain('宽基')
  })
})
