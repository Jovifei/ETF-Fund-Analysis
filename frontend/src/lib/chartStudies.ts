/** Labels and availability only; formulas and parameters remain server-owned. */
import type { ChartData } from './types'
export const serverStudies = [
 {key:'MA',label:'移动均线',parameters:'5 / 10 / 20 / 30 / 60',pane:'主图',fields:['ma5','ma10','ma20','ma30','ma60'],height:0},
 {key:'BOLL',label:'布林带',parameters:'服务端周期参数',pane:'主图',fields:['boll_upper','boll_mid','boll_lower'],height:0},
 {key:'MACD',label:'平滑异同均线',parameters:'DIF / DEA / HIST',pane:'副图',fields:['macd_dif','macd_dea','macd_hist'],height:90},
 {key:'KDJ',label:'随机指标',parameters:'K / D / J',pane:'副图',fields:['kdj_k','kdj_d','kdj_j'],height:80},
 {key:'RSI',label:'相对强弱',parameters:'14',pane:'副图',fields:['rsi14'],height:65},
] as const
export function studyAvailable(data:ChartData,key:string):boolean {
 const study=serverStudies.find(item=>item.key===key)
 return !!study&&['1d','1w','1mo'].includes(data.interval)&&data.bars.some(bar=>study.fields.some(field=>typeof bar.indicators?.[field]==='number'&&Number.isFinite(bar.indicators[field])))
}
export function volumeAvailable(data:ChartData):boolean {
 return data.bars.some(bar=>typeof bar.volume==='number'&&Number.isFinite(bar.volume))
}
