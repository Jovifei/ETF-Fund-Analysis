/** Only projects server numbers: no financial formula is implemented in the browser. */
import { init, dispose, registerIndicator, registerOverlay, ActionType, type Chart, type KLineData, type OverlayCreate } from 'klinecharts'
import type { ChartBar, ChartData, ChanObservation, PriceBox, SupportLevel } from './types'
import { levelPrice } from './format'
import { serverStudies, studyAvailable, volumeAvailable } from './chartStudies'
let registered = false
const STUDY_GROUPS = ['PIVOT', 'MA', 'BOLL', 'ATR', 'FIB', 'DERIVED', 'MACD', 'KDJ', 'RSI', 'CHAN']
export function projectBars(bars: ChartBar[]): KLineData[] {
  return bars.map(bar => ({ ...bar, timestamp: Date.parse(bar.date.length === 10 ? `${bar.date}T15:00:00+08:00` : bar.date), volume: bar.volume ?? undefined, turnover: bar.amount ?? undefined }))
}
export function groupsForLevel(level: SupportLevel): string[] {
  const supplied = Array.isArray(level.groups) ? level.groups.map(String) : []
  const preferred = supplied.filter((group, index) => STUDY_GROUPS.includes(group) && supplied.indexOf(group) === index)
  if (preferred.length) return preferred
  const methods = (Array.isArray(level.methods) ? level.methods : []).map(String).join(' ')
  const category = String(level.category ?? '')
  const groups: string[] = []
  const push = (group: string) => { if (!groups.includes(group)) groups.push(group) }
  if (category === 'price_structure' || /pivot|分形|TD9|趋势线|trendline|区间|成交/i.test(methods)) push('PIVOT')
  if (/^MA\d|均线/i.test(methods) || (category === 'dynamic_reference' && !/BOLL|布林/i.test(methods))) push('MA')
  if (/BOLL|布林/i.test(methods)) push('BOLL')
  if (category === 'volatility_reference' || /ATR/i.test(methods)) push('ATR')
  if (/Fibonacci/i.test(methods)) push('FIB')
  if (/MACD/.test(methods)) push('MACD')
  if (/KDJ/.test(methods)) push('KDJ')
  if (/RSI/.test(methods)) push('RSI')
  if (/缠论/.test(methods)) push('CHAN')
  if (category === 'price_reference' || category === 'mixed_reference') push('DERIVED')
  return groups.length ? groups : ['PIVOT']
}
export function chanOverlay(data: Pick<ChartData, 'chan_observation' | 'studies' | 'support_resistance'>): { mode: 'persisted' | 'simplified' | 'blocked' | 'absent'; geometry: ChanObservation | Record<string, unknown> | null; note: string } {
  const observation = data.chan_observation
  if (observation?.drawable) {
    const fx = Number(observation.counts?.fx ?? 0)
    const bi = Array.isArray(observation.bi) ? observation.bi.length : 0
    const zs = Array.isArray(observation.zhongshu) ? observation.zhongshu.length : 0
    const skipped = observation.undrawable_bi ? ` ${observation.undrawable_bi} 笔因方向不明未绘制。` : ''
    return { mode: 'persisted', geometry: observation, note: `已保存缠论 · 分型 ${fx} · 笔 ${bi} · 中枢 ${zs}。来自持久化 CZSC 观测，不含线段、背驰和买卖点。${skipped}` }
  }
  if (observation && observation.fallback_allowed === false) {
    return { mode: 'blocked', geometry: null, note: observation.disclaimer || '已保存缠论读模型未通过校验，不改用简化结构代替。' }
  }
  const withheld = observation?.available && observation.fallback_allowed && observation.disclaimer ? observation.disclaimer : ''
  const raw = (data.studies?.chan_structure ?? data.support_resistance?.chan_structure) as Record<string, unknown> | undefined
  if (!raw || typeof raw !== 'object') return { mode: 'absent', geometry: null, note: withheld || '当前图表没有缠论结构。' }
  if (raw.available === false) return { mode: 'simplified', geometry: null, note: [withheld, String(raw.disclaimer || raw.note || '缠论结构不可用。')].filter(Boolean).join(' ') }
  const count = (key: string) => Array.isArray(raw[key]) ? raw[key].length : 0
  const bi = count('bi'), duan = count('segments'), zs = count('zhongshu')
  const body = !bi && !duan && !zs ? '简化缠论未形成笔、段或中枢。' : `简化缠论 · 笔 ${bi} · 段 ${duan} · 中枢 ${zs}。不是完整 CZSC，不含背驰和买卖点。`
  return { mode: 'simplified', geometry: raw, note: [withheld, body].filter(Boolean).join(' ') }
}
const definitions = serverStudies.map(def=>({name:'SERVER_'+def.key,fields:[...def.fields],title:def.key+' · 服务端',height:def.height}))

function register() {
  if (registered) return
  registered = true
  for (const def of definitions) registerIndicator({ name: def.name, shortName: def.title, precision: 4, calcParams: [], figures: def.fields.map(key => ({ key, title: `${key.replace('macd_', '').replace('kdj_', '').toUpperCase()}: `, type: key === 'macd_hist' ? 'bar' : 'line', ...(key === 'macd_hist' ? { styles: ({ current }: { current: { indicatorData?: Record<string, number | null> } }) => ({ color: (current.indicatorData?.macd_hist ?? 0) >= 0 ? '#f3737c' : '#4dba90' }) } : {}) })), calc: list => list.map(bar => (bar as KLineData & { indicators: Record<string, number | null> }).indicators ?? {}) })
  registerOverlay({ name: 'researchZone', totalStep: 3, needDefaultPointFigure: false, needDefaultXAxisFigure: false, needDefaultYAxisFigure: false, createPointFigures: ({ coordinates, bounding, overlay }) => {
    if (coordinates.length < 2) return []
    const extra = overlay.extendData as { color: string; label: string }
    const levelY = coordinates[2]?.y ?? (coordinates[0].y + coordinates[1].y) / 2
    return [{ type: 'line', attrs: { coordinates: [{ x: 0, y: levelY }, { x: bounding.width, y: levelY }] }, styles: { color: extra.color, size: 1, style: 'dashed', dashedValue: [5, 3] } }, ...(bounding.width >= 600 ? [{type:'text',attrs:{x:8,y:levelY-3,text:extra.label,align:'left',baseline:'bottom'},styles:{color:extra.color,size:11,backgroundColor:'transparent',borderSize:0}}] : []), { type: 'rect', attrs: { x: 0, y: Math.min(coordinates[0].y,coordinates[1].y), width: bounding.width, height: Math.max(2, Math.abs(coordinates[0].y - coordinates[1].y)) }, styles: { color: `${extra.color}18`, borderColor: `${extra.color}80`, borderSize: 1 } }]
  } })
  registerOverlay({ name: 'researchBox', totalStep: 2, needDefaultPointFigure: false, needDefaultXAxisFigure: false, needDefaultYAxisFigure: false, createPointFigures: ({ coordinates, bounding, overlay }) => {
    if (coordinates.length < 2) return []
    const extra = overlay.extendData as { color: string; fill: string; label: string; dashed: boolean }
    const left = Math.max(0, Math.min(coordinates[0].x, coordinates[1].x))
    const right = Math.min(bounding.width, Math.max(coordinates[0].x, coordinates[1].x))
    const top = Math.min(coordinates[0].y, coordinates[1].y)
    const bottom = Math.max(coordinates[0].y, coordinates[1].y)
    if (right <= left || bottom <= top) return []
    const style = extra.dashed ? 'dashed' : 'solid'
    return [
      { type: 'rect', attrs: { x: left, y: top, width: right - left, height: bottom - top }, styles: { color: extra.fill, borderColor: extra.color, borderSize: 1 } },
      { type: 'line', attrs: { coordinates: [{ x: left, y: top }, { x: right, y: top }] }, styles: { color: extra.color, size: 1, style, dashedValue: [5, 3] } },
      { type: 'line', attrs: { coordinates: [{ x: left, y: bottom }, { x: right, y: bottom }] }, styles: { color: extra.color, size: 1, style, dashedValue: [5, 3] } },
      ...(right - left >= 150 ? [{ type: 'text', attrs: { x: left + 5, y: top + 15, text: extra.label, align: 'left', baseline: 'bottom' }, styles: { color: extra.color, size: 11, backgroundColor: 'transparent', borderSize: 0 } }] : []),
    ]
  } })
}
export class ChartAdapter {
  readonly chart: Chart
  private resizeObserver: ResizeObserver
  private data: ChartData
  private activeIndicators = new Set<string>()
  private listener: (event: { dataIndex?: number }) => void
  constructor(private el: HTMLElement, data: ChartData, cost: number | null, onCursor: (bar: ChartBar | undefined) => void, selected: string[] = ["MA","MACD","KDJ","RSI","PIVOT"]) {
    register()
    this.data=data
    const chart = init(el, { timezone: 'Asia/Shanghai', locale: 'zh-CN', styles: { grid: { horizontal: { color: '#242b32' }, vertical: { color: '#1b2228' } }, candle: { bar: { upColor: '#f3737c', downColor: '#4dba90', upBorderColor: '#f3737c', downBorderColor: '#4dba90', upWickColor: '#f3737c', downWickColor: '#4dba90' } }, xAxis: { tickText: { color: '#82919f' } }, yAxis: { tickText: { color: '#82919f' } }, separator: { color: '#2a3038' }, crosshair: { horizontal: { line: { color: '#71818e' } }, vertical: { line: { color: '#71818e' } } } } })
    if (!chart) throw new Error('chart_initialization_failed')
    this.chart = chart
    chart.setPriceVolumePrecision(3, 0)
    chart.applyNewData(projectBars(data.bars), false)
    this.setIndicatorSelection(selected, true)
    this.setStudySelection(selected)
    const lastTime = projectBars(data.bars.slice(-1))[0]?.timestamp
    if (lastTime) {
      if (data.cost_overlay_allowed && cost != null && cost > 0) chart.createOverlay({ name: 'priceLine', lock: true, points: [{ timestamp: lastTime, value: cost }], styles: { line: { color: '#d8b776', size: 1, style: 'dashed' }, text: { color: '#d8b776', backgroundColor: '#29271f', borderSize: 0 } } } as OverlayCreate)
    }
    this.listener = event => onCursor(data.bars[event.dataIndex ?? data.bars.length - 1])
    chart.subscribeAction(ActionType.OnCrosshairChange, this.listener)
    this.resizeObserver = new ResizeObserver(() => chart.resize())
    this.resizeObserver.observe(el)
    this.range(100)
  }
  setIndicatorSelection(selected: string[], showVolume: boolean) {
    const wanted=new Set(definitions.filter(def=>selected.includes(def.name.replace('SERVER_',''))&&studyAvailable(this.data,def.name.replace('SERVER_',''))).map(def=>def.name))
    if(showVolume&&volumeAvailable(this.data))wanted.add('VOL')
    for(const name of this.activeIndicators)if(!wanted.has(name)) {
      const def=definitions.find(d=>d.name===name)
      this.chart.removeIndicator(name==='VOL'?'server_volume':def?.height?name:'candle_pane',name)
      this.activeIndicators.delete(name)
    }
    for(const name of wanted)if(!this.activeIndicators.has(name)) {
      const def=definitions.find(d=>d.name===name)
      if(name==='VOL')this.chart.createIndicator({name:'VOL',calcParams:[]},false,{id:'server_volume',height:65})
      else if(def)this.chart.createIndicator(name,true,def.height?{id:name,height:def.height}:{id:'candle_pane'})
      this.activeIndicators.add(name)
    }
    this.chart.resize()
  }
  setStudySelection(selected: string[]) {
    const data=this.data
    this.chart.removeOverlay({groupId:'server_research_studies'})
    const lastTime=projectBars(data.bars.slice(-1))[0]?.timestamp
    if(!lastTime)return
    const levels = data.sr_overlay_allowed ? data.support_resistance?.levels ?? [] : []
      const nearest = [...levels].filter(level => levelPrice(level) != null && groupsForLevel(level).some(group => selected.includes(group))).sort((a, b) => Math.abs(levelPrice(a)! - data.bars.at(-1)!.close) - Math.abs(levelPrice(b)! - data.bars.at(-1)!.close)).slice(0, 12)
      for (const level of nearest) this.zone(level, lastTime)
      if(selected.includes('DERIVED')) {
        const lines=data.studies?.trend_lines
        if(Array.isArray(lines))for(const raw of lines){
          const line=raw as Record<string,unknown>,start=data.bars.find(b=>b.date===line.start_date),end=data.bars.find(b=>b.date===line.end_date)
          if(start&&end&&Number.isFinite(line.start_price)&&Number.isFinite(line.end_price))this.chart.createOverlay({name:'segment',groupId:'server_research_studies',lock:true,points:[{timestamp:projectBars([start])[0].timestamp,value:Number(line.start_price)},{timestamp:projectBars([end])[0].timestamp,value:Number(line.end_price)}],styles:{line:{color:'#8c9eff',size:1,style:'dashed',dashedValue:[5,3]}}} as OverlayCreate)
        }
      }
      if (selected.includes('BOX') && data.interval === '1d') {
        const structures = data.price_structures
        const sourceDate = structures?.source_as_of_date
        const boxes = structures?.boxes ?? []
        const active = boxes.filter(box => !['failed_breakout', 'invalidated', 'expired'].includes(box.state))
        const latest = active.at(-1) ?? boxes.at(-1)
        if (latest) this.box(latest, sourceDate)
        const candidate = structures?.candidate
        let drewCandidate = false
        if (candidate && typeof candidate.lower === 'number' && typeof candidate.upper === 'number' && typeof candidate.origin_at === 'string') {
          drewCandidate = true
          this.box({ ...candidate, kind: 'daily_box', structure_id: String(candidate.structure_id ?? 'candidate'), lower: candidate.lower, upper: candidate.upper, mid: typeof candidate.mid === 'number' ? candidate.mid : (candidate.lower + candidate.upper) / 2, origin_at: candidate.origin_at, confirmed_at: null, state: 'candidate', source_ids: [], touch_count: 0, upper_touch_count: 0, lower_touch_count: 0, volume_confirmation_available: false } as PriceBox, sourceDate)
        }
        const live = structures?.live_prior_range
        if (!latest && !drewCandidate && live && typeof live.lower === 'number' && typeof live.upper === 'number' && typeof live.origin_at === 'string' && live.lower < live.upper) {
          this.box({ kind: 'daily_box', structure_id: 'live-prior-high-low', lower: live.lower, upper: live.upper, mid: (live.lower + live.upper) / 2, origin_at: live.origin_at, confirmed_at: null, state: 'candidate', source_ids: [], touch_count: 0, upper_touch_count: 0, lower_touch_count: 0, volume_confirmation_available: false }, live.valid_until ?? sourceDate, '前高前低')
        }
      }
      if (selected.includes('CHAN')) this.chan(chanOverlay(data).geometry)
  }
  private chan(raw: unknown) {
    if (!raw || typeof raw !== 'object') return
    const structure = raw as { bi?: Array<Record<string, unknown>>; segments?: Array<Record<string, unknown>>; zhongshu?: Array<Record<string, unknown>> }
    for (const stroke of structure.bi ?? []) this.stroke(stroke, '#b388ff', 1)
    for (const stroke of structure.segments ?? []) this.stroke(stroke, '#ef9b61', 2)
    for (const zone of structure.zhongshu ?? []) this.chanZone(zone)
  }
  private stroke(item: Record<string, unknown>, color: string, size: number) {
    const start = this.timestamp(item.start_date), end = this.timestamp(item.end_date)
    const startPrice = Number(item.start_price), endPrice = Number(item.end_price)
    if (!start || !end || start === end || !Number.isFinite(startPrice) || !Number.isFinite(endPrice)) return
    this.chart.createOverlay({ name: 'segment', groupId: 'server_research_studies', lock: true, points: [{ timestamp: start, value: startPrice }, { timestamp: end, value: endPrice }], styles: { line: { color, size, style: 'solid' } } } as OverlayCreate)
  }
  private chanZone(zone: Record<string, unknown>) {
    const lower = Number(zone.zd), upper = Number(zone.zg)
    const origin = typeof zone.start_date === 'string' ? zone.start_date : ''
    const until = typeof zone.end_date === 'string' ? zone.end_date : ''
    if (!origin || !until || !Number.isFinite(lower) || !Number.isFinite(upper) || lower >= upper) return
    const label = zone.source === 'segment' ? '段中枢' : zone.source === 'persisted' ? '已保存中枢' : '笔中枢'
    this.box({ kind: 'daily_box', structure_id: `chan-${String(zone.source ?? 'bi')}`, lower, upper, mid: (lower + upper) / 2, origin_at: origin, confirmed_at: origin, valid_until: until, state: 'confirmed', source_ids: [], touch_count: 0, upper_touch_count: 0, lower_touch_count: 0, volume_confirmation_available: false }, until, label, { color: '#b388ff', fill: '#b388ff18' })
  }
  private timestamp(day: unknown) {
    if (typeof day !== 'string' || !day) return undefined
    return projectBars(this.data.bars.filter(bar => bar.date.slice(0, 10) === day.slice(0, 10)).slice(0, 1))[0]?.timestamp
  }
  private box(box: PriceBox, sourceDate?: string | null, label?: string, palette?: { color: string; fill: string }) {
    const bars = this.data.bars
    if (!bars.length || !Number.isFinite(box.lower) || !Number.isFinite(box.upper) || box.lower >= box.upper) return
    const visibleStart = bars[0].date.slice(0, 10)
    const visibleEnd = (box.valid_until ?? sourceDate ?? bars.at(-1)!.date).slice(0, 10)
    if (visibleEnd < visibleStart) return
    const startDate = box.origin_at < visibleStart ? visibleStart : box.origin_at
    const endDate = visibleEnd > bars.at(-1)!.date.slice(0, 10) ? bars.at(-1)!.date.slice(0, 10) : visibleEnd
    const timestamp = (day: string) => projectBars(bars.filter(bar => bar.date.slice(0, 10) === day).slice(0, 1))[0]?.timestamp
    const start = timestamp(startDate), end = timestamp(endDate)
    if (!start || !end || start > end) return
    const terminal = ['failed_breakout', 'invalidated', 'expired'].includes(box.state)
    const color = palette?.color ?? (terminal ? '#71818e' : box.state === 'breakout_confirmed' ? '#ef9b61' : '#d8b776')
    const fill = palette?.fill ?? (terminal ? '#71818e10' : '#d8b77612')
    const add = (from: number, to: number, dashed: boolean, text: string) => {
      if (to <= from) return
      this.chart.createOverlay({ name: 'researchBox', groupId: 'server_research_studies', lock: true,
        points: [{ timestamp: from, value: box.upper }, { timestamp: to, value: box.lower }],
        extendData: { color, fill, dashed, label: text } })
    }
    const confirmedDay = box.confirmed_at?.slice(0, 10)
    const confirmed = confirmedDay ? (confirmedDay < visibleStart ? start : timestamp(confirmedDay)) : undefined
    if (confirmed && confirmed > start) add(start, confirmed, true, label ?? '候选箱体')
    if (confirmed && end >= confirmed) add(confirmed, end, box.state === 'breakout_attempt', label ?? '日线箱体')
    else if (!box.confirmed_at) add(start, end, true, label ?? '候选箱体')
  }
  private zone(level: SupportLevel, timestamp: number) {
    const price = levelPrice(level)
    if (price == null) return
    const support = String(level.kind ?? level.type).includes('support')
    const color = support ? '#4dba90' : '#f3737c'
    const label = `${support ? '支撑' : '压力'} ${price.toFixed(3)} · ${Array.isArray(level.methods)?level.methods.slice(0,2).join(' / '):'价格研究'}`
    this.chart.createOverlay({ name: 'researchZone', groupId:'server_research_studies', lock: true, points: [{ timestamp, value: level.zone_low ?? price }, { timestamp, value: level.zone_high ?? price }, { timestamp, value: price }], extendData: { color, label } })
    this.chart.createOverlay({ name: 'priceLine', groupId:'server_research_studies', lock: true, points: [{ timestamp, value: price }], styles: { line: { color, size: 1, style: 'dashed', dashedValue: [5, 3] }, text: { color, backgroundColor: `${color}22`, borderSize: 0 } } } as OverlayCreate)
  }
  range(bars: number) { this.chart.setBarSpace(Math.max(2, Math.min(30, (this.el.clientWidth - 65) / bars))); this.chart.scrollToRealTime(); }
  reset() { this.range(100) }
  destroy() { this.resizeObserver.disconnect(); this.chart.unsubscribeAction(ActionType.OnCrosshairChange, this.listener); dispose(this.el) }
}
