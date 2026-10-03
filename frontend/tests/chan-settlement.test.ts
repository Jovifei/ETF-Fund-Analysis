import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import fixture from './fixtures/chan_chart_projection.json'
import revision from './fixtures/chan_revision_evidence.json'
import type { ChartData } from '../src/lib/types'

const mocked = vi.hoisted(() => ({ definitions: [] as any[], live: [] as any[], chart: { setPriceVolumePrecision: vi.fn(), applyNewData: vi.fn(), createIndicator: vi.fn(), createOverlay: vi.fn(), subscribeAction: vi.fn(), unsubscribeAction: vi.fn(), setBarSpace: vi.fn(), scrollToRealTime: vi.fn(), resize: vi.fn(), removeIndicator: vi.fn(), removeOverlay: vi.fn() } }))
vi.mock('klinecharts', () => ({ init: () => mocked.chart, dispose: () => { mocked.live = [] }, registerIndicator: vi.fn(), registerOverlay: (definition: any) => mocked.definitions.push(definition), ActionType: { OnCrosshairChange: 'crosshair' } }))
import { ChartAdapter, chanOverlay } from '../src/lib/chartAdapter'
import EtfChart from '../src/components/EtfChart.vue'

beforeEach(() => {
  vi.clearAllMocks()
  mocked.live = []
  mocked.chart.createOverlay.mockImplementation(overlay => { mocked.live.push(overlay) })
  mocked.chart.removeOverlay.mockImplementation(({ groupId }) => { mocked.live = mocked.live.filter(overlay => overlay.groupId !== groupId) })
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
})
function data(status: unknown, interval = '1w'): ChartData {
  const chart = structuredClone(fixture.chart) as ChartData
  chart.interval = interval
  Object.assign(chart.chan_observation!, { settlement_status: status })
  return chart
}
const label = (status: string) => `已保存中枢 · ${status}`
const zones = () => mocked.live.filter(overlay => overlay.name === 'researchBox')
const strokes = () => mocked.live.filter(overlay => overlay.name === 'segment')

describe('persisted Chan observation input settlement', () => {
  it('clears expanded revision evidence on observation replacement and layer hiding', async () => {
    const chart = data('settled')
    chart.chan_observation!.revision_evidence = structuredClone(revision)
    const wrapper = mount(EtfChart, { props: { data: chart } })
    await flushPromises()
    const toggle = wrapper.get('.study-controls').findAll('label').find(item => item.text() === '缠论笔段中枢')!.get('input')
    await toggle.setValue(true)
    const first = wrapper.get('[data-testid="chan-evidence-card"]').element as HTMLDetailsElement
    first.open = true
    await wrapper.get('[data-testid="chan-evidence-more"]').trigger('click')
    expect(wrapper.findAll('[data-testid="chan-transition"]')).toHaveLength(6)
    const replacement = structuredClone(chart)
    replacement.chan_observation!.observation_id = 'obs-next'
    replacement.chan_observation!.revision_evidence!.input_hash = 'next-input'
    await wrapper.setProps({ data: replacement })
    await flushPromises()
    const next = wrapper.get('[data-testid="chan-evidence-card"]').element as HTMLDetailsElement
    expect(next).not.toBe(first)
    expect(next.open).toBe(false)
    expect(wrapper.findAll('[data-testid="chan-transition"]')).toHaveLength(5)
    expect(wrapper.get('[data-testid="chan-evidence-card"]').text()).toContain('next-input')
    expect(zones()).toHaveLength(1)
    await toggle.setValue(false)
    expect(wrapper.find('[data-testid="chan-evidence-card"]').exists()).toBe(false)
    expect(mocked.live).toHaveLength(0)
    wrapper.unmount()
  })

  it('drops stale revision IDs on legacy/removal and resets for symbol or interval replacement', async () => {
    const chart = data('settled')
    chart.chan_observation!.revision_evidence = structuredClone(revision)
    const wrapper = mount(EtfChart, { props: { data: chart } })
    await flushPromises()
    const toggle = wrapper.get('.study-controls').findAll('label').find(item => item.text() === '缠论笔段中枢')!.get('input')
    await toggle.setValue(true)
    const legacy = structuredClone(chart)
    delete legacy.chan_observation!.revision_evidence
    await wrapper.setProps({ data: legacy })
    expect(wrapper.get('[data-testid="chan-evidence-card"]').text()).toContain('当前响应未提供修订变化记录')
    expect(wrapper.text()).not.toContain('revision-absent')
    await wrapper.setProps({ data: { ...legacy, chan_observation: null } })
    expect(wrapper.find('[data-testid="chan-evidence-card"]').exists()).toBe(false)
    for (const replacement of [{ ...chart, ts_code: '510300.SH' }, { ...chart, ts_code: '510300.SH', interval: '1mo' }]) {
      await wrapper.setProps({ data: replacement })
      const card = wrapper.get('[data-testid="chan-evidence-card"]').element as HTMLDetailsElement
      expect(card.open).toBe(false)
      expect(wrapper.findAll('[data-testid="chan-evidence-card"]')).toHaveLength(1)
      card.open = true
    }
    await wrapper.setProps({ data: { ...chart, raw_overlay_allowed: false } })
    expect(wrapper.find('[data-testid="chan-evidence-card"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it.each([
    ['1d', 'settled', '输入已结算', false],
    ['1w', 'settled', '输入已结算', false],
    ['1mo', 'settled', '输入已结算', false],
    ['1w', 'temporary', '输入暂定', true],
    ['1mo', 'temporary', '输入暂定', true],
    ['1w', undefined, '输入结算状态未知', true],
    ['1mo', null, '输入结算状态未知', true],
    ['1w', 'unknown', '输入结算状态未知', true],
    ['1w', 'SETTLED', '输入结算状态未知', true],
    ['1w', 'confirmed', '输入结算状态未知', true],
  ])('shows %s / %j without claiming structure confirmation', (interval, status, text, dashed) => {
    const chart = data(status, interval as string), before = structuredClone(chart)
    const adapter = new ChartAdapter(document.createElement('div'), chart, null, () => {}, ['CHAN'])
    const note = chanOverlay(chart).note
    expect(note).toContain(text)
    expect(note).toContain('引擎确认未知')
    expect(note).not.toContain('已确认')
    expect(zones()).toHaveLength(1)
    expect(zones()[0].extendData).toMatchObject({ dashed, label: label(text as string) })
    expect(strokes()).toHaveLength(1)
    expect(strokes()[0].styles.line.style).toBe(dashed ? 'dashed' : 'solid')
    expect(chart).toEqual(before)
    expect(chart.chan_observation).toMatchObject({ actionable: false, qualified: false, fallback_allowed: false, view_semantics: 'latest_persisted_observed_revision_not_historical_pit' })
    expect(zones()[0].points.map((point: any) => point.value)).toEqual([2.8, 1.6])
    adapter.destroy()
  })

  it('styles the full Chan border without duplicate solid edge figures', () => {
    const adapter = new ChartAdapter(document.createElement('div'), data('temporary'), null, () => {}, ['CHAN'])
    const definition = mocked.definitions.find(item => item.name === 'researchBox')
    const figures = definition.createPointFigures({ coordinates: [{ x: 10, y: 10 }, { x: 220, y: 70 }], bounding: { width: 300 }, overlay: zones()[0] })
    expect(figures.find((item: any) => item.type === 'rect').styles).toMatchObject({ style: 'stroke_fill', borderStyle: 'dashed', borderDashedValue: [5, 3] })
    expect(figures.filter((item: any) => item.type === 'line')).toHaveLength(0)
    adapter.destroy()
  })

  it('replaces status-only overlays and removes the entire group on repeated toggles', () => {
    const chart = data('temporary')
    const adapter = new ChartAdapter(document.createElement('div'), chart, null, () => {}, ['CHAN'])
    const originalPoints = structuredClone(zones()[0].points)
    for (const status of ['settled', undefined, 'temporary', 'settled']) {
      Object.assign(chart.chan_observation!, { settlement_status: status })
      adapter.setStudySelection(['CHAN'])
      expect(zones()).toHaveLength(1)
      expect(strokes()).toHaveLength(1)
      expect(zones()[0].points).toEqual(originalPoints)
      expect(zones()[0].extendData.dashed).toBe(status !== 'settled')
      expect(strokes()[0].styles.line.style).toBe(status === 'settled' ? 'solid' : 'dashed')
      adapter.setStudySelection([])
      expect(mocked.live).toHaveLength(0)
      adapter.setStudySelection(['CHAN'])
      expect(mocked.live).toHaveLength(2)
    }
    adapter.destroy()
  })

  it('does not transfer persisted settlement to a simplified fallback or corrupt blocked read', () => {
    const chart = data('temporary')
    chart.studies = { chan_structure: { available: true, settlement_status: 'settled', bi: [], segments: [], zhongshu: [{ start_date: '2026-09-01', end_date: '2026-09-08', zd: 1.5, zg: 2.5, source: 'bi' }] } }
    Object.assign(chart.chan_observation!, { drawable: false, fallback_allowed: true })
    const adapter = new ChartAdapter(document.createElement('div'), chart, null, () => {}, ['CHAN'])
    expect(chanOverlay(chart).mode).toBe('simplified')
    expect(chanOverlay(chart).note).not.toContain('输入已结算')
    expect(chanOverlay(chart).note).not.toContain('输入暂定')
    expect(zones()[0].extendData).toMatchObject({ dashed: false, label: '笔中枢' })
    Object.assign(chart.chan_observation!, { fallback_allowed: false })
    adapter.setStudySelection(['CHAN'])
    expect(chanOverlay(chart).mode).toBe('blocked')
    expect(mocked.live).toHaveLength(0)
    adapter.destroy()
  })

  it('refreshes the visible note and drawing for a status-only response replacement', async () => {
    const chart = data('temporary')
    const wrapper = mount(EtfChart, { props: { data: chart } })
    await flushPromises()
    const toggle = wrapper.get('.study-controls').findAll('label').find(item => item.text() === '缠论笔段中枢')!.get('input')
    await toggle.setValue(true)
    await flushPromises()
    expect(wrapper.get('[data-testid="chart-chan-note"]').text()).toContain('输入暂定')
    expect(zones()[0].extendData.dashed).toBe(true)
    await wrapper.setProps({ data: data('settled') })
    await flushPromises()
    expect(wrapper.get('[data-testid="chart-chan-note"]').text()).toContain('输入已结算')
    expect(wrapper.get('[data-testid="chart-chan-note"]').text()).toContain('引擎确认未知')
    expect(zones()).toHaveLength(1)
    expect(zones()[0].extendData.dashed).toBe(false)
    await toggle.setValue(false)
    expect(wrapper.find('[data-testid="chart-chan-note"]').exists()).toBe(false)
    expect(mocked.live).toHaveLength(0)
    wrapper.unmount()
  })
})
