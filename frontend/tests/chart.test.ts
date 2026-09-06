import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChartBar, ChartData } from '../src/lib/types'
const mocked = vi.hoisted(() => ({ definitions: [] as any[], chart: { setPriceVolumePrecision: vi.fn(), applyNewData: vi.fn(), createIndicator: vi.fn(), createOverlay: vi.fn(), subscribeAction: vi.fn(), unsubscribeAction: vi.fn(), setBarSpace: vi.fn(), scrollToRealTime: vi.fn(), resize: vi.fn() }, disposed: vi.fn() }))
vi.mock('klinecharts', () => ({ init: () => mocked.chart, dispose: mocked.disposed, registerIndicator: (v: any) => mocked.definitions.push(v), registerOverlay: vi.fn(), ActionType: { OnCrosshairChange: 'crosshair' } }))
import { ChartAdapter, projectBars } from '../src/lib/chartAdapter'
const bar: ChartBar = { date: '2026-09-01', open: 2, high: 3, low: 1, close: 2.5, volume: 5, amount: 10, indicators: { macd_hist: .012345, kdj_k: 72.234, rsi14: 61.278, ma20: null } }
beforeEach(() => { vi.clearAllMocks(); vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} }) })
describe('ChartAdapter has no independent indicator formulas', () => {
  it('projects server values without recomputing or rounding', () => { const projected = projectBars([bar])[0]; expect(projected.timestamp).toBe(Date.parse('2026-09-01T07:00:00Z')); expect(projected.indicators).toEqual(bar.indicators); expect(projected.turnover).toBe(10) })
  it('uses server columns even when OHLC would imply different values', () => { const host = document.createElement('div'); const data = { ts_code: '512480.SH', interval: '1d', available: true, bars: [bar], cost_overlay_allowed: false } as ChartData; const adapter = new ChartAdapter(host, data, 100, () => {}); expect(mocked.definitions.length).toBe(4); for (const d of mocked.definitions) expect(d.calc(projectBars([bar]))).toEqual([bar.indicators]); expect(mocked.chart.createOverlay).not.toHaveBeenCalled(); adapter.destroy(); expect(mocked.disposed).toHaveBeenCalledWith(host) })
  it('does not attach daily indicators or costs to minute data', () => { const adapter = new ChartAdapter(document.createElement('div'), { ts_code: '512480.SH', interval: '30m', available: true, bars: [bar], cost_overlay_allowed: false }, 3, () => {}); expect(mocked.chart.createIndicator.mock.calls).toHaveLength(1); expect(mocked.chart.createIndicator.mock.calls[0][0].name).toBe('VOL'); adapter.destroy() })
})
