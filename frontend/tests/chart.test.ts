import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChartBar, ChartData } from '../src/lib/types'
const mocked = vi.hoisted(() => ({ definitions: [] as any[], overlayDefinitions: [] as any[], chart: { setPriceVolumePrecision: vi.fn(), applyNewData: vi.fn(), createIndicator: vi.fn(), createOverlay: vi.fn(), subscribeAction: vi.fn(), unsubscribeAction: vi.fn(), setBarSpace: vi.fn(), scrollToRealTime: vi.fn(), resize: vi.fn(), removeIndicator: vi.fn(), removeOverlay: vi.fn() }, disposed: vi.fn() }))
vi.mock('klinecharts', () => ({ init: () => mocked.chart, dispose: mocked.disposed, registerIndicator: (v: any) => mocked.definitions.push(v), registerOverlay: (v: any) => mocked.overlayDefinitions.push(v), ActionType: { OnCrosshairChange: 'crosshair' } }))
import { ChartAdapter, groupsForLevel, projectBars } from '../src/lib/chartAdapter'
const bar: ChartBar = { date: '2026-09-01', open: 2, high: 3, low: 1, close: 2.5, volume: 5, amount: 10, indicators: { macd_hist: .012345, kdj_k: 72.234, rsi14: 61.278, ma20: null, boll_upper: 3.45678, boll_mid: 2.12345, boll_lower: .79012 } }
beforeEach(() => { vi.clearAllMocks(); vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} }) })
describe('ChartAdapter has no independent indicator formulas', () => {
  it('projects server values without recomputing or rounding', () => { const projected = projectBars([bar])[0]; expect(projected.timestamp).toBe(Date.parse('2026-09-01T07:00:00Z')); expect(projected.indicators).toEqual(bar.indicators); expect(projected.turnover).toBe(10) })
  it('uses server columns even when OHLC would imply different values', () => { const host = document.createElement('div'); const data = { ts_code: '512480.SH', interval: '1d', available: true, bars: [bar], cost_overlay_allowed: false } as ChartData; const adapter = new ChartAdapter(host, data, 100, () => {}); expect(mocked.definitions.length).toBe(5); for (const d of mocked.definitions) expect(d.calc(projectBars([bar]))).toEqual([bar.indicators]); expect(mocked.chart.createOverlay).not.toHaveBeenCalled(); adapter.destroy(); expect(mocked.disposed).toHaveBeenCalledWith(host) })
  it('does not attach daily indicators or costs to minute data', () => { const adapter = new ChartAdapter(document.createElement('div'), { ts_code: '512480.SH', interval: '30m', available: true, bars: [bar], cost_overlay_allowed: false }, 3, () => {}); expect(mocked.chart.createIndicator.mock.calls).toHaveLength(1); expect(mocked.chart.createIndicator.mock.calls[0][0].name).toBe('VOL'); adapter.destroy() })

  it('maps research groups and draws dashed price/trend overlays', () => {
    expect(groupsForLevel({ methods: ['MA20', 'Fibonacci 0.618'] } as any)).toEqual(expect.arrayContaining(['MA', 'FIB']))
    const data = { ts_code: '512480.SH', interval: '1d', available: true, bars: [bar, { ...bar, date: '2026-09-02', close: 2.6 }], sr_overlay_allowed: true,
      support_resistance: { levels: [{ price: 2.2, kind: 'support', methods: ['MA20'], zone_low: 2.1, zone_high: 2.3 }] },
      studies: { trend_lines: [{ start_date: '2026-09-01', end_date: '2026-09-02', start_price: 2, end_price: 2.6 }] } } as any
    const adapter = new ChartAdapter(document.createElement('div'), data, null, () => {}, ['MA', 'PIVOT'])
    const overlays = mocked.chart.createOverlay.mock.calls.map(call => call[0])
    expect(overlays.some((item: any) => item.name === 'priceLine' && item.styles?.line?.style === 'dashed')).toBe(true)
    expect(overlays.some((item: any) => item.name === 'segment' && item.styles?.line?.style === 'dashed')).toBe(true)
    adapter.destroy()
  })
})

// Same numeric lines/zones; only avoid long labels covering narrow candles.
it('research zones keep prices but omit dense method labels below 600px',()=>{
  const overlay=mocked.overlayDefinitions.find(x=>x.name==='researchZone')
  const args={coordinates:[{x:0,y:20},{x:0,y:30},{x:0,y:25}],overlay:{extendData:{color:'#4dba90',label:'support methods'}}}
  const narrow=overlay.createPointFigures({...args,bounding:{width:320}})
  const wide=overlay.createPointFigures({...args,bounding:{width:900}})
  expect(narrow.filter((x:any)=>x.type==='text')).toEqual([])
  expect(narrow.find((x:any)=>x.type==='line').attrs.coordinates.map((x:any)=>x.y)).toEqual([25,25])
  const text=wide.find((x:any)=>x.type==='text')
  expect(text.attrs.text).toBe('support methods')
  expect(text.styles.backgroundColor).toBe('transparent')
})

// A-U2: change view layers without rebuilding the chart or jumping to latest.
it('indicator and volume toggles preserve chart position and server payload',()=>{
 const data={ts_code:'512480.SH',interval:'1d',available:true,bars:[bar],cost_overlay_allowed:false} as ChartData
 const adapter=new ChartAdapter(document.createElement('div'),data,null,()=>{})
 mocked.chart.scrollToRealTime.mockClear();mocked.chart.applyNewData.mockClear();mocked.disposed.mockClear()
 adapter.setIndicatorSelection(['BOLL'],false)
 expect(mocked.chart.removeIndicator).toHaveBeenCalledWith('server_volume','VOL')
 expect(mocked.chart.createIndicator).toHaveBeenCalledWith('SERVER_BOLL',true,{id:'candle_pane'})
 expect(mocked.chart.scrollToRealTime).not.toHaveBeenCalled()
 expect(mocked.chart.applyNewData).not.toHaveBeenCalled()
 expect(mocked.disposed).not.toHaveBeenCalled()
 adapter.setStudySelection([])
 expect(mocked.chart.removeOverlay).toHaveBeenCalledWith({groupId:'server_research_studies'})
 expect(mocked.disposed).not.toHaveBeenCalled()
 adapter.destroy()
})
