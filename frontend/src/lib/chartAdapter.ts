/** Only projects server numbers: no financial formula is implemented in the browser. */
import { init, dispose, registerIndicator, registerOverlay, ActionType, type Chart, type KLineData, type OverlayCreate } from 'klinecharts'
import type { ChartBar, ChartData, SupportLevel } from './types'
import { levelPrice } from './format'
import { serverStudies, studyAvailable, volumeAvailable } from './chartStudies'
let registered = false
export function projectBars(bars: ChartBar[]): KLineData[] {
  return bars.map(bar => ({ ...bar, timestamp: Date.parse(bar.date.length === 10 ? `${bar.date}T15:00:00+08:00` : bar.date), volume: bar.volume ?? undefined, turnover: bar.amount ?? undefined }))
}
export function groupsForLevel(level: SupportLevel): string[] {
  const methods = (Array.isArray(level.methods) ? level.methods : []).map(String).join(' ')
  const groups: string[] = []
  if (/^MA\d|均线/i.test(methods)) groups.push('MA')
  if (/BOLL|布林/i.test(methods)) groups.push('BOLL')
  if (/^ATR|ATR[+-]/i.test(methods)) groups.push('ATR')
  if (/Fibonacci/i.test(methods)) groups.push('FIB')
  if (/缠论/.test(methods)) groups.push('CHAN')
  if (/pivot|分形|TD9|趋势线|trendline/i.test(methods)) groups.push('PIVOT')
  return groups.length ? groups : ['PIVOT']
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
      if(selected.includes('PIVOT')) {
        const lines=data.studies?.trend_lines
        if(Array.isArray(lines))for(const raw of lines){
          const line=raw as Record<string,unknown>,start=data.bars.find(b=>b.date===line.start_date),end=data.bars.find(b=>b.date===line.end_date)
          if(start&&end&&Number.isFinite(line.start_price)&&Number.isFinite(line.end_price))this.chart.createOverlay({name:'segment',groupId:'server_research_studies',lock:true,points:[{timestamp:projectBars([start])[0].timestamp,value:Number(line.start_price)},{timestamp:projectBars([end])[0].timestamp,value:Number(line.end_price)}],styles:{line:{color:'#8c9eff',size:1,style:'dashed',dashedValue:[5,3]}}} as OverlayCreate)
        }
      }
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
