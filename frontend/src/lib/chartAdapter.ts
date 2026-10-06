/** Only projects server numbers: no financial formula is implemented in the browser. */
import { init, dispose, registerIndicator, registerOverlay, ActionType, type Chart, type KLineData, type OverlayCreate } from 'klinecharts'
import type { ChartBar, ChartData, ChanObservation, PriceBox, SupportLevel } from './types'
import { levelDirection, levelDirectionLabel, levelPrice } from './format'
import { serverStudies, studyAvailable, volumeAvailable } from './chartStudies'
let registered = false
const STUDY_GROUPS = ['PIVOT', 'MA', 'BOLL', 'ATR', 'FIB', 'DERIVED', 'MACD', 'KDJ', 'RSI', 'CHAN']
export function projectBars(bars: ChartBar[]): KLineData[] {
  return bars.map(bar => ({ ...bar, timestamp: Date.parse(bar.date.length === 10 ? `${bar.date}T15:00:00+08:00` : bar.date), volume: bar.volume ?? undefined, turnover: bar.amount ?? undefined }))
}
// Match the calendar date supplied by the server, never reinterpret an offset or
// invent a candle for a missing trading day. Coordinates come from the bar itself.
function candleDay(value: unknown): string | undefined {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}(?:[ T](?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):?[0-5]\d)?)?$/.test(value)) return undefined
  const day = value.slice(0, 10)
  const [year, month, date] = day.split('-').map(Number)
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  return month >= 1 && month <= 12 && date >= 1 && date <= days[month - 1] ? day : undefined
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
type ChanSettlement = { label: string; dashed: boolean }
// This describes the accepted observation input, never engine/structure confirmation.
function chanSettlement(status: unknown): ChanSettlement {
  if (status === 'settled') return { label: '输入已结算', dashed: false }
  if (status === 'temporary') return { label: '输入暂定', dashed: true }
  return { label: '输入结算状态未知', dashed: true }
}
export function chanOverlay(data: Pick<ChartData, 'chan_observation' | 'studies' | 'support_resistance'>): { mode: 'persisted' | 'simplified' | 'blocked' | 'absent'; geometry: ChanObservation | Record<string, unknown> | null; note: string } {
  const observation = data.chan_observation
  if (observation?.drawable) {
    const fx = Number(observation.counts?.fx ?? 0)
    const bi = Array.isArray(observation.bi) ? observation.bi.length : 0
    const zs = Array.isArray(observation.zhongshu) ? observation.zhongshu.length : 0
    const skipped = observation.undrawable_bi ? ` ${observation.undrawable_bi} 笔因方向不明未绘制。` : ''
    const settlement = chanSettlement(observation.settlement_status)
    return { mode: 'persisted', geometry: observation, note: `已保存缠论 · 分型 ${fx} · 笔 ${bi} · 中枢 ${zs}。${settlement.label}（${settlement.dashed ? '虚线' : '实线'}）。结算状态仅描述本次观测输入，引擎确认未知。来自持久化 CZSC 观测，不含线段、背驰和买卖点。顶/底分型不是买卖建议或交易信号；标记位于已保存观测的来源蜡烛，不代表历史确认时点。缺蜡烛或同日同类价格冲突不绘制。${skipped}` }
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
  registerOverlay({ name: 'chanFractal', totalStep: 2, needDefaultPointFigure: false, needDefaultXAxisFigure: false, needDefaultYAxisFigure: false, createPointFigures: ({ coordinates, bounding, overlay }) => {
    if (!coordinates.length) return []
    const point = coordinates[0], extra = overlay.extendData as { mark: 'top' | 'bottom'; dashed: boolean }
    if (!['top', 'bottom'].includes(extra.mark)) return []
    return [
      { type: 'circle', attrs: { x: point.x, y: point.y, r: 4 }, styles: { style: 'stroke', color: '#9bc8dc', borderColor: '#9bc8dc', borderSize: 1.5, borderStyle: extra.dashed ? 'dashed' : 'solid', borderDashedValue: [3, 2] } },
      { type: 'text', attrs: { x: Math.max(24, Math.min(point.x, bounding.width - 24)), y: Math.max(12, Math.min(point.y + (extra.mark === 'top' ? -14 : 18), bounding.height - 12)), text: extra.mark === 'top' ? '顶分型' : '底分型', align: 'center', baseline: 'middle' }, styles: { color: '#9bc8dc', size: 11, backgroundColor: '#11181e', borderSize: 0 } },
    ]
  } })
  registerOverlay({ name: 'researchZone', totalStep: 3, needDefaultPointFigure: false, needDefaultXAxisFigure: false, needDefaultYAxisFigure: false, createPointFigures: ({ coordinates, bounding, overlay }) => {
    if (coordinates.length < 2) return []
    const extra = overlay.extendData as { color: string; label: string }
    const levelY = coordinates[2]?.y ?? (coordinates[0].y + coordinates[1].y) / 2
    return [{ type: 'line', attrs: { coordinates: [{ x: 0, y: levelY }, { x: bounding.width, y: levelY }] }, styles: { color: extra.color, size: 1, style: 'dashed', dashedValue: [5, 3] } }, ...(bounding.width >= 600 ? [{type:'text',attrs:{x:8,y:levelY-3,text:extra.label,align:'left',baseline:'bottom'},styles:{color:extra.color,size:11,backgroundColor:'transparent',borderSize:0}}] : []), { type: 'rect', attrs: { x: 0, y: Math.min(coordinates[0].y,coordinates[1].y), width: bounding.width, height: Math.max(2, Math.abs(coordinates[0].y - coordinates[1].y)) }, styles: { color: `${extra.color}18`, borderColor: `${extra.color}80`, borderSize: 1 } }]
  } })
  registerOverlay({ name: 'researchBox', totalStep: 2, needDefaultPointFigure: false, needDefaultXAxisFigure: false, needDefaultYAxisFigure: false, createPointFigures: ({ coordinates, bounding, overlay }) => {
    if (coordinates.length < 2) return []
    const extra = overlay.extendData as { color: string; fill: string; label: string; dashed: boolean; outline?: boolean }
    const left = Math.max(0, Math.min(coordinates[0].x, coordinates[1].x))
    const right = Math.min(bounding.width, Math.max(coordinates[0].x, coordinates[1].x))
    const top = Math.min(coordinates[0].y, coordinates[1].y)
    const bottom = Math.max(coordinates[0].y, coordinates[1].y)
    if (right <= left || bottom <= top) return []
    const style = extra.dashed ? 'dashed' : 'solid'
    return [
      { type: 'rect', attrs: { x: left, y: top, width: right - left, height: bottom - top }, styles: { color: extra.fill, borderColor: extra.color, borderSize: 1, ...(extra.outline ? { style: 'stroke_fill', borderStyle: style, borderDashedValue: [5, 3] } : {}) } },
      ...(!extra.outline ? [{ type: 'line', attrs: { coordinates: [{ x: left, y: top }, { x: right, y: top }] }, styles: { color: extra.color, size: 1, style, dashedValue: [5, 3] } },
      { type: 'line', attrs: { coordinates: [{ x: left, y: bottom }, { x: right, y: bottom }] }, styles: { color: extra.color, size: 1, style, dashedValue: [5, 3] } }] : []),
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
      if (selected.includes('CHAN')) {
        const view = chanOverlay(data)
        this.chan(view.geometry, view.mode === 'persisted' ? chanSettlement(data.chan_observation?.settlement_status) : undefined)
        if (view.mode === 'persisted') this.fractals()
      }
  }
  private fractals() {
    if (!['1d', '1w', '1mo'].includes(this.data.interval)) return
    const raw = this.data.chan_observation?.fx
    if (!Array.isArray(raw)) return
    // Never choose one arbitrary price for conflicting same-day/mark evidence.
    // Equal duplicates collapse; top and bottom remain separate descriptions.
    const groups = new Map<string, { timestamp: number; price: number; mark: 'top' | 'bottom'; conflict: boolean }>()
    for (const item of raw) {
      if (!item || typeof item !== 'object' || !['top', 'bottom'].includes(item.mark) || item.source !== 'persisted' || typeof item.price !== 'number' || !Number.isFinite(item.price) || item.price <= 0) continue
      const day = candleDay(item.date)
      if (!day) continue
      const candles = this.data.bars.filter(bar => candleDay(bar.date) === day)
      if (candles.length !== 1) continue
      const timestamp = projectBars(candles)[0].timestamp
      if (!Number.isFinite(timestamp)) continue
      const key = `${day}:${item.mark}`, previous = groups.get(key)
      if (previous) previous.conflict ||= previous.price !== item.price
      else groups.set(key, { timestamp, price: item.price, mark: item.mark, conflict: false })
    }
    const settlement = chanSettlement(this.data.chan_observation?.settlement_status)
    for (const item of [...groups.values()].filter(item => !item.conflict).sort((a, b) => a.timestamp - b.timestamp || a.mark.localeCompare(b.mark))) {
      this.chart.createOverlay({ name: 'chanFractal', groupId: 'server_research_studies', lock: true,
        points: [{ timestamp: item.timestamp, value: item.price }], extendData: { mark: item.mark, dashed: settlement.dashed } })
    }
  }
  private chan(raw: unknown, settlement?: ChanSettlement) {
    if (!raw || typeof raw !== 'object') return
    const structure = raw as { bi?: Array<Record<string, unknown>>; segments?: Array<Record<string, unknown>>; zhongshu?: Array<Record<string, unknown>> }
    for (const stroke of structure.bi ?? []) this.stroke(stroke, '#b388ff', 1, settlement?.dashed)
    for (const stroke of structure.segments ?? []) this.stroke(stroke, '#ef9b61', 2, settlement?.dashed)
    for (const zone of structure.zhongshu ?? []) this.chanZone(zone, settlement)
  }
  private stroke(item: Record<string, unknown>, color: string, size: number, dashed = false) {
    const start = this.timestamp(item.start_date), end = this.timestamp(item.end_date)
    const startPrice = Number(item.start_price), endPrice = Number(item.end_price)
    if (!start || !end || start === end || !Number.isFinite(startPrice) || !Number.isFinite(endPrice)) return
    this.chart.createOverlay({ name: 'segment', groupId: 'server_research_studies', lock: true, points: [{ timestamp: start, value: startPrice }, { timestamp: end, value: endPrice }], styles: { line: { color, size, style: dashed ? 'dashed' : 'solid', dashedValue: [5, 3] } } } as OverlayCreate)
  }
  private chanZone(zone: Record<string, unknown>, settlement?: ChanSettlement) {
    const lower = Number(zone.zd), upper = Number(zone.zg)
    const origin = typeof zone.start_date === 'string' ? zone.start_date : ''
    const until = typeof zone.end_date === 'string' ? zone.end_date : ''
    if (!origin || !until || !Number.isFinite(lower) || !Number.isFinite(upper) || lower >= upper) return
    const range = this.boundedRange(origin, until)
    if (!range || range.end <= range.start) return
    const label = settlement ? `已保存中枢 · ${settlement.label}` : zone.source === 'segment' ? '段中枢' : '笔中枢'
    this.chart.createOverlay({ name: 'researchBox', groupId: 'server_research_studies', lock: true,
      points: [{ timestamp: range.start, value: upper }, { timestamp: range.end, value: lower }],
      extendData: { color: '#b388ff', fill: '#b388ff18', dashed: settlement?.dashed ?? false, label, outline: !!settlement } })
  }
  private timestamp(day: unknown) {
    const key = candleDay(day)
    if (!key) return undefined
    const bar = this.data.bars.find(bar => candleDay(bar.date) === key)
    const timestamp = bar ? projectBars([bar])[0].timestamp : undefined
    return Number.isFinite(timestamp) ? timestamp : undefined
  }
  private boundedRange(originAt: unknown, untilAt: unknown) {
    const bars = this.data.bars
    if (!bars.length) return undefined
    const visibleStart = candleDay(bars[0].date), visibleEnd = candleDay(bars.at(-1)!.date)
    const origin = candleDay(originAt), until = candleDay(untilAt)
    if (!visibleStart || !visibleEnd || !origin || !until || until < visibleStart) return undefined
    const startDate = origin < visibleStart ? visibleStart : origin
    const endDate = until > visibleEnd ? visibleEnd : until
    const start = this.timestamp(startDate), end = this.timestamp(endDate)
    if (!start || !end || start > end) return undefined
    return { startDate, endDate, start, end }
  }
  private box(box: PriceBox, sourceDate?: string | null, label?: string) {
    if (!Number.isFinite(box.lower) || !Number.isFinite(box.upper) || box.lower >= box.upper) return
    const range = this.boundedRange(box.origin_at, box.valid_until ?? sourceDate ?? this.data.bars.at(-1)?.date)
    if (!range) return
    const { startDate, endDate, start, end } = range
    const terminal = ['failed_breakout', 'invalidated', 'expired'].includes(box.state)
    const color = terminal ? '#71818e' : box.state === 'breakout_confirmed' ? '#ef9b61' : '#d8b776'
    const fill = terminal ? '#71818e10' : '#d8b77612'
    const add = (from: number, to: number, dashed: boolean, text: string) => {
      if (to <= from) return
      this.chart.createOverlay({ name: 'researchBox', groupId: 'server_research_studies', lock: true,
        points: [{ timestamp: from, value: box.upper }, { timestamp: to, value: box.lower }],
        extendData: { color, fill, dashed, label: text } })
    }
    const confirmedDay = candleDay(box.confirmed_at)
    const confirmed = confirmedDay ? (confirmedDay < startDate ? start : confirmedDay > endDate ? end : this.timestamp(confirmedDay)) : undefined
    if (confirmed && confirmed > start) add(start, confirmed, true, label ?? '候选箱体')
    if (confirmed && end >= confirmed) add(confirmed, end, box.state === 'breakout_attempt', label ?? '日线箱体')
    else if (!box.confirmed_at) add(start, end, true, label ?? '候选箱体')
  }
  private zone(level: SupportLevel, timestamp: number) {
    const price = levelPrice(level)
    if (price == null) return
    const direction = levelDirection(level)
    const color = direction === 'support' ? '#4dba90' : direction === 'resistance' ? '#f3737c' : '#94a3b8'
    const label = `${levelDirectionLabel(level)} ${price.toFixed(3)} · ${Array.isArray(level.methods)?level.methods.slice(0,2).join(' / '):'价格研究'}`
    this.chart.createOverlay({ name: 'researchZone', groupId:'server_research_studies', lock: true, points: [{ timestamp, value: level.zone_low ?? price }, { timestamp, value: level.zone_high ?? price }, { timestamp, value: price }], extendData: { color, label } })
    this.chart.createOverlay({ name: 'priceLine', groupId:'server_research_studies', lock: true, points: [{ timestamp, value: price }], styles: { line: { color, size: 1, style: 'dashed', dashedValue: [5, 3] }, text: { color, backgroundColor: `${color}22`, borderSize: 0 } } } as OverlayCreate)
  }
  range(bars: number) { this.chart.setBarSpace(Math.max(2, Math.min(30, (this.el.clientWidth - 65) / bars))); this.chart.scrollToRealTime(); }
  reset() { this.range(100) }
  destroy() { this.resizeObserver.disconnect(); this.chart.unsubscribeAction(ActionType.OnCrosshairChange, this.listener); dispose(this.el) }
}
