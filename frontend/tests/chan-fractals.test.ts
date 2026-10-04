import { beforeEach, describe, expect, it, vi } from 'vitest'
import fixture from './fixtures/chan_chart_projection.json'
import type { ChartData } from '../src/lib/types'
const mocked = vi.hoisted(() => ({ definitions: [] as any[], chart: { setPriceVolumePrecision: vi.fn(), applyNewData: vi.fn(), createIndicator: vi.fn(), createOverlay: vi.fn(), subscribeAction: vi.fn(), unsubscribeAction: vi.fn(), setBarSpace: vi.fn(), scrollToRealTime: vi.fn(), resize: vi.fn(), removeIndicator: vi.fn(), removeOverlay: vi.fn() } }))
vi.mock('klinecharts', () => ({ init: () => mocked.chart, dispose: vi.fn(), registerIndicator: vi.fn(), registerOverlay: (d: any) => mocked.definitions.push(d), ActionType: { OnCrosshairChange: 'crosshair' } }))
import { ChartAdapter, chanOverlay, projectBars } from '../src/lib/chartAdapter'
beforeEach(() => { vi.clearAllMocks(); vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} }) })
const marker = (date: unknown = '2026-09-03 15:00:00', price: unknown = 3, mark: unknown = 'top') => ({ date, price, mark, source: 'persisted' })
const data = (...fx: unknown[]) => { const d = structuredClone(fixture.chart) as ChartData; Object.assign(d.chan_observation!, { fx }); return d }
function draw(d: ChartData, selection = ['CHAN']) { const a = new ChartAdapter(document.createElement('div'), d, null, () => {}, selection); const all = mocked.chart.createOverlay.mock.calls.map(x => x[0]); a.destroy(); return all }
const markers = (d: ChartData) => draw(d).filter(x => x.name === 'chanFractal')
describe('saved fractal markers are observation projections, never historical confirmation', () => {
 it('draws explicit top/bottom at exact saved price and real candle timestamp; existing geometry is unchanged', () => {
  const old = draw(data()); mocked.chart.createOverlay.mockClear()
  const d = data(marker(), marker('2026-09-01', 1, 'bottom')), before = structuredClone(d)
  const result = draw(d); expect(result.filter(x => x.name !== 'chanFractal')).toEqual(old)
  const fx = result.filter(x => x.name === 'chanFractal'); expect(fx).toHaveLength(2)
  expect(fx.map(x => x.points[0])).toEqual([{ timestamp: projectBars([d.bars[0]])[0].timestamp, value: 1 }, { timestamp: projectBars([d.bars[1]])[0].timestamp, value: 3 }])
  expect(fx.map(x => x.extendData.mark)).toEqual(['bottom', 'top']); expect(fx.every(x => x.lock && x.groupId === 'server_research_studies')).toBe(true)
  expect(d).toEqual(before); expect(chanOverlay(d).note).toContain('不是买卖建议或交易信号'); expect(chanOverlay(d).note).toContain('不代表历史确认时点')
 })
 it.each(['2026-09-03T00:30:00+08:00', '2026-09-03T23:30:00-05:00', '2026-09-03T15:00:00Z'])('keeps the supplied source day across zones %s', date => { const d=data(marker(date)); expect(markers(d)[0].points[0].timestamp).toBe(projectBars([d.bars[1]])[0].timestamp) })
 it.each([marker('2026-09-02'), marker('2026-02-30'), marker('2026-09-03T25:00:00'), marker(null), marker(undefined, null), marker(undefined, true), marker(undefined, '3'), marker(undefined, Infinity), marker(undefined, 0), marker(undefined, -1), marker(undefined, 3, 'buy'), marker(undefined, 3, null), null])('omits malformed, missing and unknown marker %j', m => { expect(markers(data(m))).toEqual([]) })
 it('deduplicates equal markers, drops conflicting same-day same-mark prices, preserves the other mark', () => {
  expect(markers(data(marker(), marker(), marker(undefined, 2), marker(undefined, 1, 'bottom'))).map(x => x.extendData.mark)).toEqual(['bottom'])
  mocked.chart.createOverlay.mockClear(); expect(markers(data(marker(), marker()))).toHaveLength(1)
 })
 it('does not guess when more than one real candle has the same calendar day', () => { const d=data(marker()); d.bars.push({...d.bars[1],date:'2026-09-03T15:00:00+08:00'}); expect(markers(d)).toEqual([]) })
 it.each(['temporary','unknown',null])('keeps uncertainty for input state %s', status => { const d=data(marker()); Object.assign(d.chan_observation!,{settlement_status:status}); expect(markers(d)[0].extendData.dashed).toBe(true) })
 it('draws settled input with a solid ring without inventing confirmation time', () => {const fx=markers(data(marker()))[0];expect(fx.extendData.dashed).toBe(false);expect(JSON.stringify(fx)).not.toContain('confirmed_at')})
 it.each(['1h','5m'])('does not calendar-collapse unsupported intraday %s', interval => {const d=data(marker());d.interval=interval;expect(markers(d)).toEqual([])})
 it.each([false,undefined])('does not borrow fx from non-drawable persisted evidence %s', drawable => {const d=data(marker());d.chan_observation!.drawable=drawable;expect(markers(d)).toEqual([])})
 it('never interprets simplified fx as persisted markers and removes overlay group on selection changes', () => {const d=data(marker());d.chan_observation=null;d.studies={chan_structure:{available:true,fx:[marker()]}};expect(markers(d)).toEqual([]);mocked.chart.createOverlay.mockClear();expect(draw(data(marker()),[])).toEqual([]);expect(mocked.chart.removeOverlay).toHaveBeenCalledWith({groupId:'server_research_studies'})})
 it('registers a neutral point ring and top/bottom labels with no trading arrows', () => {draw(data(marker()));const def=mocked.definitions.find(x=>x.name==='chanFractal');expect(def).toBeTruthy();for(const mark of ['top','bottom']){const figures=def.createPointFigures({coordinates:[{x:60,y:60}],bounding:{width:120,height:120},overlay:{extendData:{mark,dashed:true}}});expect(figures[0]).toMatchObject({type:'circle',attrs:{x:60,y:60,r:4},styles:{borderStyle:'dashed'}});expect(figures[1].attrs.text).toBe(mark==='top'?'顶分型':'底分型')}})
})