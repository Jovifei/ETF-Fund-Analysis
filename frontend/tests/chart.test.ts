import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChartBar, ChartData } from '../src/lib/types'
const mocked = vi.hoisted(() => ({ definitions: [] as any[], overlayDefinitions: [] as any[], chart: { setPriceVolumePrecision: vi.fn(), applyNewData: vi.fn(), createIndicator: vi.fn(), createOverlay: vi.fn(), subscribeAction: vi.fn(), unsubscribeAction: vi.fn(), setBarSpace: vi.fn(), scrollToRealTime: vi.fn(), resize: vi.fn(), removeIndicator: vi.fn(), removeOverlay: vi.fn() }, disposed: vi.fn() }))
vi.mock('klinecharts', () => ({ init: () => mocked.chart, dispose: mocked.disposed, registerIndicator: (v: any) => mocked.definitions.push(v), registerOverlay: (v: any) => mocked.overlayDefinitions.push(v), ActionType: { OnCrosshairChange: 'crosshair' } }))
import { ChartAdapter, chanOverlay, groupsForLevel, projectBars } from '../src/lib/chartAdapter'
const bar: ChartBar = { date: '2026-09-01', open: 2, high: 3, low: 1, close: 2.5, volume: 5, amount: 10, indicators: { macd_hist: .012345, kdj_k: 72.234, rsi14: 61.278, ma20: null, boll_upper: 3.45678, boll_mid: 2.12345, boll_lower: .79012 } }
beforeEach(() => { vi.clearAllMocks(); vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} }) })
describe('ChartAdapter has no independent indicator formulas', () => {
  it('projects server values without recomputing or rounding', () => { const projected = projectBars([bar])[0]; expect(projected.timestamp).toBe(Date.parse('2026-09-01T07:00:00Z')); expect(projected.indicators).toEqual(bar.indicators); expect(projected.turnover).toBe(10) })
  it('uses server columns even when OHLC would imply different values', () => { const host = document.createElement('div'); const data = { ts_code: '512480.SH', interval: '1d', available: true, bars: [bar], cost_overlay_allowed: false } as ChartData; const adapter = new ChartAdapter(host, data, 100, () => {}); expect(mocked.definitions.length).toBe(5); for (const d of mocked.definitions) expect(d.calc(projectBars([bar]))).toEqual([bar.indicators]); expect(mocked.chart.createOverlay).not.toHaveBeenCalled(); adapter.destroy(); expect(mocked.disposed).toHaveBeenCalledWith(host) })
  it('does not attach daily indicators or costs to minute data', () => { const adapter = new ChartAdapter(document.createElement('div'), { ts_code: '512480.SH', interval: '30m', available: true, bars: [bar], cost_overlay_allowed: false }, 3, () => {}); expect(mocked.chart.createIndicator.mock.calls).toHaveLength(1); expect(mocked.chart.createIndicator.mock.calls[0][0].name).toBe('VOL'); adapter.destroy() })

  it('prefers server groups and still infers MA, BOLL, FIB and indicator tags', () => {
    expect(groupsForLevel({ methods: ['MA20', 'Fibonacci 0.618'] } as any)).toEqual(expect.arrayContaining(['MA', 'FIB']))
    expect(groupsForLevel({ category: 'price_structure', methods: ['MACD确认拐点'], groups: ['MACD'] } as any)).toEqual(['MACD'])
    expect(groupsForLevel({ category: 'mixed_reference', methods: ['20日区间上沿'], groups: ['MA', 'BOLL'] } as any)).toEqual(['MA', 'BOLL'])
    expect(groupsForLevel({ category: 'mixed_reference', methods: ['MA20', '布林下轨'] } as any)).toEqual(expect.arrayContaining(['MA', 'BOLL']))
    expect(groupsForLevel({ methods: ['KDJ确认拐点'] } as any)).toEqual(expect.arrayContaining(['KDJ']))
    expect(groupsForLevel({ methods: ['RSI确认拐点'] } as any)).toEqual(expect.arrayContaining(['RSI']))
    expect(groupsForLevel({ category: 'price_reference', methods: ['Fibonacci 0.618'], groups: ['FIB'] } as any)).toEqual(['FIB'])
  })

  it('draws only the checked MA, BOLL, FIB, pivot and indicator levels', () => {
    const levels = [
      { price: 2.2, kind: 'support', category: 'price_structure', methods: ['MACD确认拐点'], groups: ['MACD'] },
      { price: 2.4, kind: 'resistance', category: 'mixed_reference', methods: ['MA20', '布林下轨'], groups: ['MA', 'BOLL'] },
      { price: 2.8, kind: 'resistance', methods: ['Fibonacci 0.618'], groups: ['FIB'] },
      { price: 1.9, kind: 'support', category: 'price_structure', methods: ['确认分形低点'], groups: ['PIVOT'] },
    ]
    const data = { ts_code: '512480.SH', interval: '1d', available: true, bars: [bar, { ...bar, date: '2026-09-02', close: 2.6 }], sr_overlay_allowed: true, support_resistance: { levels } } as any
    const prices = (selected: string[]) => {
      mocked.chart.createOverlay.mockClear()
      const adapter = new ChartAdapter(document.createElement('div'), data, null, () => {}, selected)
      const drawn = mocked.chart.createOverlay.mock.calls.map(call => call[0]).filter((item: any) => item.name === 'priceLine').map((item: any) => item.points[0].value)
      adapter.destroy()
      return drawn
    }
    expect(prices(['MACD'])).toEqual([2.2])
    expect(prices(['MA'])).toEqual([2.4])
    expect(prices(['BOLL'])).toEqual([2.4])
    expect(prices(['FIB'])).toEqual([2.8])
    expect(prices(['PIVOT'])).toEqual([1.9])
    expect(prices(['DERIVED'])).toEqual([])
  })

  it('maps research groups and draws dashed price/trend overlays', () => {
    expect(groupsForLevel({ methods: ['MA20', 'Fibonacci 0.618'] } as any)).toEqual(expect.arrayContaining(['MA', 'FIB']))
    const data = { ts_code: '512480.SH', interval: '1d', available: true, bars: [bar, { ...bar, date: '2026-09-02', close: 2.6 }], sr_overlay_allowed: true,
      support_resistance: { levels: [{ price: 2.2, kind: 'support', methods: ['MA20'], zone_low: 2.1, zone_high: 2.3 }] },
      studies: { trend_lines: [{ start_date: '2026-09-01', end_date: '2026-09-02', start_price: 2, end_price: 2.6 }] } } as any
    const adapter = new ChartAdapter(document.createElement('div'), data, null, () => {}, ['MA', 'DERIVED'])
    const overlays = mocked.chart.createOverlay.mock.calls.map(call => call[0])
    expect(overlays.some((item: any) => item.name === 'priceLine' && item.styles?.line?.style === 'dashed')).toBe(true)
    expect(overlays.some((item: any) => item.name === 'segment' && item.styles?.line?.style === 'dashed')).toBe(true)
    adapter.destroy()
  })

  it('draws only date-bounded daily box overlays and separates pre-confirmation from confirmed time', () => {
    const bars = ['2026-09-01', '2026-09-02', '2026-09-03'].map(date => ({ ...bar, date }))
    const data = { ts_code: '512480.SH', interval: '1d', available: true, bars,
      price_structures: { qualified: true, interval: '1d', actionable: false, source_as_of_date: '2026-09-03', boxes: [{
        kind: 'daily_box', structure_id: 'box-a', lower: 2, upper: 3, mid: 2.5, origin_at: '2026-09-01',
        confirmed_at: '2026-09-02', valid_until: null, state: 'confirmed', source_ids: ['touch-a', 'touch-b'],
        touch_count: 2, upper_touch_count: 1, lower_touch_count: 1, volume_confirmation_available: false,
      }] } } as any
    const adapter = new ChartAdapter(document.createElement('div'), data, null, () => {}, ['BOX'])
    const boxes = mocked.chart.createOverlay.mock.calls.map(call => call[0]).filter((item: any) => item.name === 'researchBox')

    expect(boxes).toHaveLength(2)
    expect(boxes[0].points.map((point: any) => point.timestamp)).toEqual([
      projectBars([bars[0]])[0].timestamp, projectBars([bars[1]])[0].timestamp,
    ])
    expect(boxes[0].extendData.dashed).toBe(true)
    expect(boxes[1].points[0].timestamp).toBe(projectBars([bars[1]])[0].timestamp)
    expect(boxes[1].points[1].timestamp).toBe(projectBars([bars[2]])[0].timestamp)
    expect(boxes[1].extendData.dashed).toBe(false)
    adapter.destroy()
  })

  it('draws a live prior high/low box when the saved daily structure is missing', () => {
    const bars = ['2026-09-01', '2026-09-02', '2026-09-03'].map(date => ({ ...bar, date }))
    const data = { ts_code: '512480.SH', interval: '1d', available: true, bars, price_structures: {
      qualified: false, interval: '1d', actionable: false, reason: 'snapshot_missing_requires_task', boxes: [],
      live_prior_range: { kind: 'prior_high_low', qualified: false, actionable: false, persisted: false, window: 3, origin_at: '2026-09-01', valid_until: '2026-09-03', lower: 1, upper: 3, label: '前高前低' },
    } } as any
    const adapter = new ChartAdapter(document.createElement('div'), data, null, () => {}, ['BOX'])
    const boxes = mocked.chart.createOverlay.mock.calls.map(call => call[0]).filter((item: any) => item.name === 'researchBox')
    expect(boxes).toHaveLength(1)
    expect(boxes[0].extendData.label).toBe('前高前低')
    expect(boxes[0].extendData.dashed).toBe(true)
    expect(boxes[0].points.map((point: any) => point.value)).toEqual([3, 1])
    adapter.destroy()
  })

  it('draws simplified chan strokes, segments and pivot boxes when CHAN is checked', () => {
    const bars = ['2026-09-01', '2026-09-02', '2026-09-03'].map(date => ({ ...bar, date }))
    const data = { ts_code: '512480.SH', interval: '1d', available: true, bars, studies: { chan_structure: {
      available: true, actionable: false, qualified: false,
      bi: [{ start_date: '2026-09-01', end_date: '2026-09-02', start_price: 1, end_price: 3, direction: 'up' }],
      segments: [{ start_date: '2026-09-01', end_date: '2026-09-03', start_price: 1, end_price: 2.5, direction: 'up' }],
      zhongshu: [{ start_date: '2026-09-01', end_date: '2026-09-03', zd: 1.5, zg: 2.5, source: 'bi' }],
    } } } as any
    const adapter = new ChartAdapter(document.createElement('div'), data, null, () => {}, ['CHAN'])
    const overlays = mocked.chart.createOverlay.mock.calls.map(call => call[0])
    const strokes = overlays.filter((item: any) => item.name === 'segment')
    const zones = overlays.filter((item: any) => item.name === 'researchBox')
    expect(strokes).toHaveLength(2)
    expect(strokes[0].points.map((point: any) => point.value)).toEqual([1, 3])
    expect(strokes[1].points.map((point: any) => point.value)).toEqual([1, 2.5])
    expect(zones).toHaveLength(1)
    expect(zones[0].extendData.label).toBe('笔中枢')
    expect(zones[0].points.map((point: any) => point.value)).toEqual([2.5, 1.5])
    adapter.destroy()
  })

  it('draws persisted Chan bi and zhongshu instead of the simplified fallback', () => {
    const bars = ['2026-09-01', '2026-09-03', '2026-09-08'].map(date => ({ ...bar, date }))
    const data = { ts_code: '512480.SH', interval: '1d', available: true, bars, studies: { chan_structure: {
      available: true, bi: [{ start_date: '2026-09-01', end_date: '2026-09-03', start_price: 9, end_price: 8 }],
      segments: [{ start_date: '2026-09-01', end_date: '2026-09-08', start_price: 9, end_price: 7 }], zhongshu: [],
    } }, chan_observation: {
      available: true, drawable: true, fallback_allowed: false, actionable: false, qualified: false,
      counts: { fx: 2, bi: 1, zs: 1 }, undrawable_bi: 1,
      bi: [{ start_date: '2026-09-01', end_date: '2026-09-03', start_price: 1, end_price: 3, source: 'persisted' }],
      segments: [],
      zhongshu: [{ start_date: '2026-09-01', end_date: '2026-09-08', zd: 1.6, zg: 2.8, source: 'persisted' }],
    } } as any
    expect(chanOverlay(data).note).toContain('已保存缠论')
    expect(chanOverlay(data).note).toContain('1 笔因方向不明未绘制')
    expect(chanOverlay(data).mode).toBe('persisted')
    const adapter = new ChartAdapter(document.createElement('div'), data, null, () => {}, ['CHAN'])
    const overlays = mocked.chart.createOverlay.mock.calls.map(call => call[0])
    const strokes = overlays.filter((item: any) => item.name === 'segment')
    const zones = overlays.filter((item: any) => item.name === 'researchBox')
    expect(strokes).toHaveLength(1)
    expect(strokes[0].points.map((point: any) => point.value)).toEqual([1, 3])
    expect(zones).toHaveLength(1)
    expect(zones[0].extendData.label).toBe('已保存中枢 · 输入结算状态未知')
    adapter.destroy()
    const blocked = chanOverlay({ chan_observation: { available: false, drawable: false, fallback_allowed: false, disclaimer: '已保存缠论读模型未通过校验，不改用简化结构代替。' }, studies: { chan_structure: { bi: [{ start_date: '2026-09-01', end_date: '2026-09-03', start_price: 1, end_price: 3 }] } } })
    expect(blocked.mode).toBe('blocked')
    expect(blocked.geometry).toBeNull()
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
