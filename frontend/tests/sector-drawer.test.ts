import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import SectorDrawer from '../src/components/SectorDrawer.vue'
import { api } from '../src/lib/api'

vi.mock('../src/lib/api', () => ({ api: vi.fn(), errorText: (error: Error) => error.message }))

const mockSector = {
  sector_name: '光伏设备',
  board_type: 'industry',
  sector_pct_change: 2.35,
  source_as_of: '2026-11-06',
  source: 'em_summary',
  is_mock: false,
  up_count: 35,
  down_count: 10,
  flat_count: 5,
  total_count: 50,
}

const mockMappings = {
  mappings: [
    {
      sector_name: '光伏设备',
      theme_l1: '新能源',
      theme_l2: '光伏',
      representative_etf: {
        ts_code: '515790.SH',
        symbol: '515790',
        name: '光伏ETF',
        fund_company: '华泰柏瑞基金',
      },
      tracking_index: {
        code: '931151.CSI',
        name: '中证光伏产业指数',
      },
      mapping_type: 'thematic_primary',
      basis: '华泰柏瑞中证光伏产业ETF，流动性与跟踪规模市场第一，具备代表性',
      effective_from: '2021-01-01',
      effective_to: '2099-12-31',
      qualification: 'QUALIFIED',
      status: 'active',
    },
  ],
  total: 1,
}

const mockDetail = {
  instrument: {
    ts_code: '515790.SH',
    name: '光伏ETF',
    kind: 'etf',
    theme_l1: '新能源',
    theme_l2: '光伏',
  },
  decision: {
    ts_code: '515790.SH',
    name: '光伏ETF',
    grade: '4',
    grade_base: '3',
    grade_final: '4',
    adjustment: {
      applied: true,
      base_grade: '3',
      final_grade: '4',
      weight: 0.4167,
    },
    qualification: 'QUALIFIED',
    support_resistance: {
      nearest_support: { price: 0.85 },
      nearest_resistance: { price: 1.05 },
    },
    structure_v1: {
      wyckoff_phase: '吸筹完成',
      dow_phase: '上升结构',
      atr_risk_bucket: '低波安全',
    },
  },
  read_as_of: '2026-11-06',
  quote: { price: 0.92, change_ratio: 0.021, status: 'NORMAL' },
}

const mockChart = {
  ts_code: '515790.SH',
  interval: '1d',
  available: true,
  bars: [
    { date: '2026-11-06', open: 0.90, high: 0.93, low: 0.89, close: 0.92, volume: 1000000, amount: 920000, indicators: {} }
  ],
}

describe('SectorDrawer.vue', () => {
  beforeEach(() => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.includes('/workspace/sectors/representatives')) {
        return mockMappings
      }
      if (path.includes('/workspace/instruments/515790.SH/chart')) {
        return mockChart
      }
      if (path.includes('/workspace/instruments/515790.SH')) {
        return mockDetail
      }
      if (path.includes('/workspace/indexes/931151.CSI/chart')) {
        return mockChart
      }
      return {}
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders drawer header, metrics and representative ETF details when open', async () => {
    const wrapper = mount(SectorDrawer, {
      props: {
        modelValue: true,
        sector: mockSector,
        generation: 42,
      },
      global: {
        stubs: {
          EtfChart: { template: '<div data-testid="etf-chart-stub">Chart Stub</div>' },
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await flushPromises()

    // Title and tags
    expect(wrapper.text()).toContain('光伏设备 板块研判')
    expect(wrapper.text()).toContain('行业板块')
    expect(wrapper.text()).toContain('+2.35%')

    // Representative ETF mapping info
    expect(wrapper.text()).toContain('515790.SH')
    expect(wrapper.text()).toContain('光伏ETF')
    expect(wrapper.text()).toContain('华泰柏瑞基金')
    expect(wrapper.text()).toContain('流动性与跟踪规模市场第一')

    // Structure & grade
    expect(wrapper.text()).toContain('4档 · 可入场')
    expect(wrapper.text()).toContain('基准: 3档 · 可试探')
    expect(wrapper.text()).toContain('结构因子调整：3 → 4')
    expect(wrapper.text()).toContain('0.85')
    expect(wrapper.text()).toContain('1.05')
    expect(wrapper.text()).toContain('吸筹完成')
    expect(wrapper.text()).toContain('上升结构')
    expect(wrapper.text()).toContain('低波安全')

    // Watermark
    expect(wrapper.text()).toContain('actionable=false')
  })

  it('switches to index & breadth tab and displays proportions', async () => {
    const wrapper = mount(SectorDrawer, {
      props: {
        modelValue: true,
        sector: mockSector,
        generation: 42,
      },
      global: {
        stubs: {
          EtfChart: { template: '<div data-testid="etf-chart-stub">Chart Stub</div>' },
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await flushPromises()

    // Switch tab to index & breadth
    const tabs = wrapper.findAll('.tab-btn')
    expect(tabs.length).toBe(2)
    await tabs[1].trigger('click')
    await flushPromises()

    // Breadth values
    expect(wrapper.text()).toContain('上涨 35 家 (70%)')
    expect(wrapper.text()).toContain('下跌 10 家 (20%)')
    expect(wrapper.text()).toContain('平盘 5 家')
    expect(wrapper.text()).toContain('跟踪指数：中证光伏产业指数 (931151.CSI)')
  })

  it('emits close event when close button or backdrop is clicked', async () => {
    const wrapper = mount(SectorDrawer, {
      props: {
        modelValue: true,
        sector: mockSector,
      },
      global: {
        stubs: {
          EtfChart: true,
          RouterLink: true,
        },
      },
    })

    await flushPromises()

    const closeBtn = wrapper.find('.close-btn')
    await closeBtn.trigger('click')

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
    expect(wrapper.emitted('close')).toBeTruthy()
  })
})
