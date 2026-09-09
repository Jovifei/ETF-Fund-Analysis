/** Only projects server numbers: no financial formula is implemented in the browser. */
import { init, dispose, registerIndicator, registerOverlay, ActionType, type Chart, type KLineData, type OverlayCreate } from 'klinecharts'
import type { ChartBar, ChartData, SupportLevel } from './types'
import { levelPrice } from './format'
let registered = false
export function projectBars(bars: ChartBar[]): KLineData[] {
  return bars.map(bar => ({ ...bar, timestamp: Date.parse(bar.date.length === 10 ? `${bar.date}T15:00:00+08:00` : bar.date), volume: bar.volume ?? undefined, turnover: bar.amount ?? undefined }))
}
const definitions = [
  { name: 'SERVER_MA', fields: ['ma5', 'ma10', 'ma20', 'ma30', 'ma60'], title: 'MA · 服务端', height: 0 },
  { name: 'SERVER_BOLL', fields: ['boll_upper','boll_mid','boll_lower'], title:'BOLL · 服务端',height:0 },
  { name: 'SERVER_MACD', fields: ['macd_dif', 'macd_dea', 'macd_hist'], title: 'MACD · 服务端', height: 90 },
  { name: 'SERVER_KDJ', fields: ['kdj_k', 'kdj_d', 'kdj_j'], title: 'KDJ · 服务端', height: 80 },
  { name: 'SERVER_RSI', fields: ['rsi14'], title: 'RSI · 服务端', height: 65 },
]
function register() {
  if (registered) return
  registered = true
  for (const def of definitions) registerIndicator({ name: def.name, shortName: def.title, precision: 4, calcParams: [], figures: def.fields.map(key => ({ key, title: `${key.replace('macd_', '').replace('kdj_', '').toUpperCase()}: `, type: key === 'macd_hist' ? 'bar' : 'line', ...(key === 'macd_hist' ? { styles: ({ current }: { current: { indicatorData?: Record<string, number | null> } }) => ({ color: (current.indicatorData?.macd_hist ?? 0) >= 0 ? '#f3737c' : '#4dba90' }) } : {}) })), calc: list => list.map(bar => (bar as KLineData & { indicators: Record<string, number | null> }).indicators ?? {}) })
  registerOverlay({ name: 'researchZone', totalStep: 3, needDefaultPointFigure: false, needDefaultXAxisFigure: false, needDefaultYAxisFigure: false, createPointFigures: ({ coordinates, bounding, overlay }) => {
    if (coordinates.length < 2) return []
    const extra = overlay.extendData as { color: string; label: string }
    return [{type:'text',attrs:{x:8,y:Math.min(coordinates[0].y,coordinates[1].y)-3,text:extra.label,align:'left',baseline:'bottom'},styles:{color:extra.color,size:11}}, { type: 'rect', attrs: { x: 0, y: Math.min(coordinates[0].y, coordinates[1].y), width: bounding.width, height: Math.max(2, Math.abs(coordinates[0].y - coordinates[1].y)) }, styles: { color: `${extra.color}18`, borderColor: `${extra.color}80`, borderSize: 1 } }]
  } })
}
export class ChartAdapter {
  readonly chart: Chart
  private resizeObserver: ResizeObserver
  private listener: (event: { dataIndex?: number }) => void
  constructor(private el: HTMLElement, data: ChartData, cost: number | null, onCursor: (bar: ChartBar | undefined) => void, selected: string[] = ["MA","MACD","KDJ","RSI","PIVOT"]) {
    register()
    const chart = init(el, { timezone: 'Asia/Shanghai', locale: 'zh-CN', styles: { grid: { horizontal: { color: '#242b32' }, vertical: { color: '#1b2228' } }, candle: { bar: { upColor: '#f3737c', downColor: '#4dba90', upBorderColor: '#f3737c', downBorderColor: '#4dba90', upWickColor: '#f3737c', downWickColor: '#4dba90' } }, xAxis: { tickText: { color: '#82919f' } }, yAxis: { tickText: { color: '#82919f' } }, separator: { color: '#2a3038' }, crosshair: { horizontal: { line: { color: '#71818e' } }, vertical: { line: { color: '#71818e' } } } } })
    if (!chart) throw new Error('chart_initialization_failed')
    this.chart = chart
    chart.setPriceVolumePrecision(3, 0)
    chart.applyNewData(projectBars(data.bars), false)
    if (data.bars.some(bar => bar.volume != null)) chart.createIndicator({ name: 'VOL', calcParams: [] }, false, { height: 65 })
    if (['1d','1w','1mo'].includes(data.interval)) for (const def of definitions.filter(x=>selected.includes(x.name.replace('SERVER_','')))) chart.createIndicator(def.name, true, def.height ? { id: def.name, height: def.height } : { id: 'candle_pane' })
    const lastTime = projectBars(data.bars.slice(-1))[0]?.timestamp
    if (lastTime) {
      const levels = data.sr_overlay_allowed ? data.support_resistance?.levels ?? [] : []
      const nearest = [...levels].filter(level => levelPrice(level) != null && (Array.isArray(level.groups)?level.groups.some(x=>selected.includes(String(x))):selected.includes('PIVOT'))).sort((a, b) => Math.abs(levelPrice(a)! - data.bars.at(-1)!.close) - Math.abs(levelPrice(b)! - data.bars.at(-1)!.close)).slice(0, 12)
      for (const level of nearest) this.zone(level, lastTime)
      if(selected.includes('PIVOT')) {
        const lines=data.studies?.trend_lines
        if(Array.isArray(lines))for(const raw of lines){
          const line=raw as Record<string,unknown>,start=data.bars.find(b=>b.date===line.start_date),end=data.bars.find(b=>b.date===line.end_date)
          if(start&&end&&Number.isFinite(line.start_price)&&Number.isFinite(line.end_price))chart.createOverlay({name:'segment',lock:true,points:[{timestamp:projectBars([start])[0].timestamp,value:Number(line.start_price)},{timestamp:projectBars([end])[0].timestamp,value:Number(line.end_price)}]})
        }
      }
      if (data.cost_overlay_allowed && cost != null && cost > 0) chart.createOverlay({ name: 'priceLine', lock: true, points: [{ timestamp: lastTime, value: cost }], styles: { line: { color: '#d8b776', size: 1, style: 'dashed' }, text: { color: '#d8b776', backgroundColor: '#29271f', borderSize: 0 } } } as OverlayCreate)
    }
    this.listener = event => onCursor(data.bars[event.dataIndex ?? data.bars.length - 1])
    chart.subscribeAction(ActionType.OnCrosshairChange, this.listener)
    this.resizeObserver = new ResizeObserver(() => chart.resize())
    this.resizeObserver.observe(el)
    this.range(100)
  }
  private zone(level: SupportLevel, timestamp: number) {
    const price = levelPrice(level)
    if (price == null) return
    const support = String(level.kind ?? level.type).includes('support')
    this.chart.createOverlay({ name: 'researchZone', lock: true, points: [{ timestamp, value: level.zone_low ?? price }, { timestamp, value: level.zone_high ?? price }], extendData: { color: support ? '#4dba90' : '#f3737c', label: `${support ? '支撑' : '压力'} ${price.toFixed(3)} · ${Array.isArray(level.methods)?level.methods.slice(0,2).join(' / '):'价格研究'}` } })
  }
  range(bars: number) { this.chart.setBarSpace(Math.max(2, Math.min(30, (this.el.clientWidth - 65) / bars))); this.chart.scrollToRealTime(); }
  reset() { this.range(100) }
  destroy() { this.resizeObserver.disconnect(); this.chart.unsubscribeAction(ActionType.OnCrosshairChange, this.listener); dispose(this.el) }
}
