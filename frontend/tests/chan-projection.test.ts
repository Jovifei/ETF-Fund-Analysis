import { beforeEach, describe, expect, it, vi } from 'vitest'
import fixture from './fixtures/chan_chart_projection.json'
import type { ChartData } from '../src/lib/types'

const mocked = vi.hoisted(() => ({ chart: { setPriceVolumePrecision: vi.fn(), applyNewData: vi.fn(), createIndicator: vi.fn(), createOverlay: vi.fn(), subscribeAction: vi.fn(), unsubscribeAction: vi.fn(), setBarSpace: vi.fn(), scrollToRealTime: vi.fn(), resize: vi.fn(), removeIndicator: vi.fn(), removeOverlay: vi.fn() } }))
vi.mock('klinecharts', () => ({ init: () => mocked.chart, dispose: vi.fn(), registerIndicator: vi.fn(), registerOverlay: vi.fn(), ActionType: { OnCrosshairChange: 'crosshair' } }))
import { ChartAdapter, chanOverlay, projectBars } from '../src/lib/chartAdapter'

beforeEach(() => { vi.clearAllMocks(); vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} }) })
const data = () => structuredClone(fixture.chart) as ChartData
function draw(chart: ChartData) {
  const adapter = new ChartAdapter(document.createElement('div'), chart, null, () => {}, ['CHAN'])
  const overlays = mocked.chart.createOverlay.mock.calls.map(call => call[0])
  adapter.destroy()
  return overlays
}
function zone(chart: ChartData, start: unknown, end: unknown) {
  Object.assign(chart.chan_observation!.zhongshu![0], { start_date: start, end_date: end })
  return draw(chart).filter(item => item.name === 'researchBox')
}

describe('persisted backend Chan timestamp projection', () => {
  it('draws the real backend projection without changing prices, qualification or source payload', () => {
    const chart = data(), before = structuredClone(chart)
    expect(chanOverlay(chart).mode).toBe('persisted')
    const overlays = draw(chart)
    const zones = overlays.filter(item => item.name === 'researchBox')
    expect(zones).toHaveLength(1)
    expect(zones[0].points).toEqual([
      { timestamp: projectBars([chart.bars[0]])[0].timestamp, value: 2.8 },
      { timestamp: projectBars([chart.bars[2]])[0].timestamp, value: 1.6 },
    ])
    expect(zones[0].extendData).toMatchObject({ label: '已保存中枢', dashed: false })
    expect(overlays.filter(item => item.name === 'segment')).toHaveLength(1)
    expect(chart).toEqual(before)
    expect(chart.chan_observation).toMatchObject({ qualified: false, actionable: false, fallback_allowed: false })
  })

  it.each(['', ' 15:00:00', 'T15:00:00', 'T15:00:00.123+08:00', 'T00:30:00+08:00', 'T23:30:00-05:00', 'T15:00:00Z'])('uses source calendar day for timestamp suffix %j', suffix => {
    const chart = data()
    const zones = zone(chart, `2026-09-01${suffix}`, `2026-09-08${suffix}`)
    expect(zones).toHaveLength(1)
    expect(zones[0].points.map((point: { timestamp: number }) => point.timestamp)).toEqual([
      projectBars([chart.bars[0]])[0].timestamp, projectBars([chart.bars[2]])[0].timestamp,
    ])
  })

  it('uses the matching candle timestamp when the candle itself has a full timestamp', () => {
    const chart = data()
    chart.bars = chart.bars.map(bar => ({ ...bar, date: `${bar.date}T15:00:00+08:00` }))
    expect(zone(chart, '2026-09-01 15:00:00', '2026-09-08 15:00:00')[0].points.map((point: { timestamp: number }) => point.timestamp)).toEqual([
      projectBars([chart.bars[0]])[0].timestamp, projectBars([chart.bars[2]])[0].timestamp,
    ])
  })

  it('clips full timestamps to available candles without creating missing dates', () => {
    const chart = data()
    expect(zone(chart, '2026-08-31 15:00:00', '2026-09-09T15:00:00+08:00')[0].points.map((point: { timestamp: number }) => point.timestamp)).toEqual([
      projectBars([chart.bars[0]])[0].timestamp, projectBars([chart.bars[2]])[0].timestamp,
    ])
  })

  it.each([
    ['2026-09-02 15:00:00', '2026-09-08 15:00:00'],
    ['2026-09-01 15:00:00', '2026-09-06 15:00:00'],
    ['2026-09-09 15:00:00', '2026-09-10 15:00:00'],
    ['2026-08-28 15:00:00', '2026-08-31 15:00:00'],
    ['2026-09-08 15:00:00', '2026-09-01 15:00:00'],
    ['2026-09-01 15:00:00', '2026-09-01 15:00:00'],
    ['invalid', '2026-09-08 15:00:00'],
    ['2026-09-01-invalid', '2026-09-08 15:00:00'],
    ['2026-09-01T25:00:00', '2026-09-08 15:00:00'],
    ['2026-02-30 15:00:00', '2026-09-08 15:00:00'],
    ['2026-09-01 15:00:00', '2026-09-31 15:00:00'],
    ['', '2026-09-08 15:00:00'],
    [null, '2026-09-08 15:00:00'],
    ['2026-09-01 15:00:00', undefined],
  ])('omits unavailable, invalid, reversed or zero-width endpoints %j / %j', (start, end) => {
    expect(zone(data(), start, end)).toEqual([])
  })

  it('does not normalize an invalid calendar day into an available candle', () => {
    const chart = data()
    chart.bars = chart.bars.map((bar, index) => ({ ...bar, date: ['2026-02-27', '2026-03-02', '2026-03-03'][index] }))
    expect(zone(chart, '2026-02-30 15:00:00', '2026-03-03 15:00:00')).toEqual([])
  })

  it('accepts a leap-day candle without rolling the day forward', () => {
    const chart = data()
    chart.bars = chart.bars.slice(0, 2).map((bar, index) => ({ ...bar, date: ['2024-02-29', '2024-03-01'][index] }))
    expect(zone(chart, '2024-02-29 15:00:00', '2024-03-01 15:00:00')[0].points.map((point: { timestamp: number }) => point.timestamp)).toEqual(projectBars(chart.bars).map(bar => bar.timestamp))
  })

  it('does not draw when the chart has no bars', () => {
    const chart = data()
    chart.bars = []
    expect(draw(chart)).toEqual([])
  })
})


describe('daily box confirmation coordinates', () => {
  it.each([
    ['2026-08-31 15:00:00', false],
    ['2026-09-09T15:00:00+08:00', true],
  ])('clips confirmation %s to the available candle range', (confirmed, dashed) => {
    const chart = data()
    chart.price_structures = { qualified: false, interval: '1d', actionable: false, boxes: [{ kind: 'daily_box', structure_id: 'calendar-box', lower: 1.6, upper: 2.8, mid: 2.2,
      origin_at: '2026-08-31 15:00:00', valid_until: '2026-09-09 15:00:00', confirmed_at: confirmed,
      state: 'confirmed', source_ids: [], touch_count: 0, upper_touch_count: 0, lower_touch_count: 0, volume_confirmation_available: false,
    }] }
    const adapter = new ChartAdapter(document.createElement('div'), chart, null, () => {}, ['BOX'])
    const boxes = mocked.chart.createOverlay.mock.calls.map(call => call[0]).filter(item => item.name === 'researchBox')
    expect(boxes).toHaveLength(1)
    expect(boxes[0].extendData.dashed).toBe(dashed)
    expect(boxes[0].points.map((point: { timestamp: number }) => point.timestamp)).toEqual([
      projectBars([chart.bars[0]])[0].timestamp, projectBars([chart.bars[2]])[0].timestamp,
    ])
    adapter.destroy()
  })
})
