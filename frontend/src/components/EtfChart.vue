<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { popupLayout } from '../lib/popupLayout'
import { acquireDialogScrollLock, releaseDialogScrollLock } from '../lib/dialogScrollLock'
import { serverStudies, studyAvailable, volumeAvailable } from '../lib/chartStudies'
import { ChartAdapter, chanOverlay, groupsForLevel } from '../lib/chartAdapter'
import { num, levelDirection, levelDirectionLabel, levelPrice } from '../lib/format'
import type { ChartBar, ChartData } from '../lib/types'
import ChanEvidenceCard from './ChanEvidenceCard.vue'
const props=defineProps<{data:ChartData;cost?:number|null;label?:string;allowMinutes?:boolean}>()
const emit=defineEmits<{period:[value:string]}>()
const root=ref<HTMLElement|null>(null),host=ref<HTMLElement|null>(null),cursor=ref<ChartBar>(),failed=ref(''),range=ref(100),expanded=ref(false),expandButton=ref<HTMLButtonElement|null>(null)
const priceBasis=ref<'raw'|'research'>('raw')
const basisTransition=computed(()=>props.data.basis_transition===true&&!!props.data.research_bars?.length)
const displayData=computed<ChartData>(()=>{
 if(priceBasis.value==='research'&&props.data.research_bars)return {...props.data,bars:props.data.research_bars,support_resistance:props.data.research_support_resistance??null,price_structures:props.data.research_price_structures,sr_overlay_allowed:props.data.research_sr_overlay_allowed??false,cost_overlay_allowed:props.data.research_cost_overlay_allowed??false}
 // Studies use research prices; remove their geometry only from a mismatched raw projection.
 if(props.data.raw_overlay_allowed===false)return {...props.data,bars:props.data.bars.map(bar=>({...bar,indicators:{}})),studies:props.data.studies?{...props.data.studies,trend_lines:undefined,chan_structure:undefined}:undefined,chan_observation:props.data.chan_observation?{...props.data.chan_observation,drawable:false,fallback_allowed:false,disclaimer:'原始行情与研究价格口径不同，缠论结构已隐藏。'}:undefined,support_resistance:null,price_structures:{qualified:false,reason:'price_basis_mismatch',interval:props.data.interval,actionable:false,boxes:[]},sr_overlay_allowed:false}
 return props.data
})
const data=displayData
const periods=computed(()=>[...['1d','1w','1mo'],...(props.allowMinutes?['30m','60m']:[])])
const periodNames:Record<string,string>={'1d':'日 K','1w':'周 K','1mo':'月 K','30m':'30 分钟','60m':'小时 K'}
const groups=['BOX','PIVOT','MA','BOLL','ATR','FIB','DERIVED','MACD','KDJ','RSI','CHAN']
const supportResistanceGroups=new Set(['BOX','PIVOT','MA','BOLL','ATR','FIB','DERIVED','MACD','KDJ','RSI'])
const defaultSupportResistanceGroups=['BOX','PIVOT']
const names:Record<string,string>={BOX:'日线箱体',PIVOT:'结构支撑压力',MA:'均线参考',BOLL:'布林带参考',ATR:'波幅参考',FIB:'斐波那契',DERIVED:'其他派生价位',MACD:'MACD',KDJ:'KDJ',RSI:'RSI',CHAN:'缠论笔段中枢'}
const selected=ref([...defaultSupportResistanceGroups])
const supportResistanceVisible=computed(()=>selected.value.some(item=>supportResistanceGroups.has(item)))
const indicatorPanel=ref<HTMLDetailsElement|null>(null), indicators=ref(['MA']), showVolume=ref(false)
const menuPosition=ref<Record<string,string>>({})
function positionIndicators(){
 const panel=indicatorPanel.value
 if(!panel?.open)return
 const anchor=panel.getBoundingClientRect()
 if(!anchor.height||!panel.offsetHeight)return
 const view=window.visualViewport
 const layout=popupLayout(anchor,{left:view?.offsetLeft??0,top:view?.offsetTop??0,width:view?.width??window.innerWidth,height:view?.height??window.innerHeight},anchor.height/panel.offsetHeight)
 if(!layout){panel.open=false;return}
 menuPosition.value={left:layout.left+'px',right:'auto',top:layout.top+'px',width:layout.width+'px',maxWidth:'none',maxHeight:layout.maxHeight+'px'}
}
const activeIndicators=computed(()=>indicators.value.filter(key=>studyAvailable(displayData.value,key)))
const indicatorCount=computed(()=>activeIndicators.value.length+(showVolume.value&&volumeAvailable(displayData.value)?1:0))
function closeIndicators(){if(indicatorPanel.value){indicatorPanel.value.open=false;indicatorPanel.value.querySelector('summary')?.focus()}}
function outside(event:PointerEvent){if(indicatorPanel.value?.open&&!indicatorPanel.value.contains(event.target as Node))indicatorPanel.value.open=false}
function toggleSupportResistance(){
 selected.value=supportResistanceVisible.value
  ? selected.value.filter(item=>!supportResistanceGroups.has(item))
  : [...new Set([...selected.value,...defaultSupportResistanceGroups])]
}
function focusChartInsideDialog(){if(expanded.value)host.value?.focus({preventScroll:true})}
function chartPointerDown(event:PointerEvent){
 if(expanded.value){focusChartInsideDialog();return}
 compactPointerOrigin={x:event.clientX,y:event.clientY};compactPointerDragged=false
}
function chartPointerMove(event:PointerEvent){
 if(expanded.value||!compactPointerOrigin)return
 const dx=event.clientX-compactPointerOrigin.x,dy=event.clientY-compactPointerOrigin.y
 if(Math.hypot(dx,dy)>8)compactPointerDragged=true
}
function resetCompactPointer(){compactPointerOrigin=null;compactPointerDragged=false}
function openCompactChart(){
 if(expanded.value){focusChartInsideDialog();return}
 if(compactPointerDragged){resetCompactPointer();return}
 resetCompactPointer();void toggleExpanded()
}
const levels=computed(()=>{
 if(!displayData.value.sr_overlay_allowed)return []
 const current=displayData.value.bars.at(-1)?.close??0
 return [...(displayData.value.support_resistance?.levels??[])].filter(x=>levelPrice(x)!=null&&groupsForLevel(x).some(g=>selected.value.includes(g))).sort((a,b)=>Math.abs(levelPrice(a)!-current)-Math.abs(levelPrice(b)!-current)).slice(0,12)
})
const structureReason:Record<string,string>={snapshot_missing_requires_task:'尚无结构快照，需由受审计刷新任务生成。',history_qualification_blocked:'历史价格口径或连续性未通过检查。',snapshot_after_as_of:'快照晚于当前图表读取时点，已隐藏。',price_basis_mismatch:'价格口径不匹配，结构线已隐藏。',trading_day_gap:'存在未解释的交易日缺口。',calendar_unavailable:'交易日历不可用。',atr_unavailable:'有效历史不足以计算 ATR。',history_too_short:'已结算日线不足。',no_confirmed_pivots:'没有已确认的价格拐点。',insufficient_independent_touches:'独立触碰不足，未形成箱体。',box_width_out_of_range:'区间宽度不符合当前研究条件。',box_duration_too_short:'持续时间不足。',box_inside_ratio_too_low:'区间内收盘比例不足。',box_trend_drift_too_high:'区间趋势位移过大。',interval_unsupported:'本批仅支持日线结构。'}
const structureText=computed(()=>{
 const value=displayData.value.price_structures
 if(displayData.value.interval!=='1d')return '本批仅支持日线结构。'
 if(value?.boxes?.length)return `已计算至 ${value.source_as_of_date??'—'}；状态：${value.boxes[0].state}。`
 if(value?.candidate)return `结构候选尚未确认：${structureReason[String(value.candidate.reason)]??String(value.candidate.reason??'条件未满足')}`
 const live=value?.live_prior_range
 if(live&&typeof live.lower==='number'&&typeof live.upper==='number')return `未使用已确认箱体。最近 ${live.window} 根日线前高 ${num(live.upper,3)}、前低 ${num(live.lower,3)}。这是现算研究区间，不是已审计箱体。`
 const reason=structureReason[value?.reason??'snapshot_missing_requires_task']??`结构不可用：${value?.reason??'unknown'}`
 if(value&&Object.prototype.hasOwnProperty.call(value,'live_prior_range'))return `${reason} 可见日线不足或价格无效，前高前低也无法绘制。`
 return reason
})
const chanNote=computed(()=>chanOverlay(displayData.value).note)
const displayedBox=computed(()=>{
 const boxes=displayData.value.price_structures?.boxes??[]
 return boxes.filter(box=>!['failed_breakout','invalidated','expired'].includes(box.state)).at(-1)??boxes.at(-1)
})
const candidateBox=computed(()=>{
 const value=displayData.value.price_structures?.candidate
 if(!value||typeof value.lower!=='number'||typeof value.upper!=='number'||typeof value.origin_at!=='string')return null
 return {lower:value.lower,upper:value.upper,origin_at:value.origin_at,as_of_date:typeof value.as_of_date==='string'?value.as_of_date:null,
  upper_touch_count:typeof value.upper_touch_count==='number'?value.upper_touch_count:null,lower_touch_count:typeof value.lower_touch_count==='number'?value.lower_touch_count:null}
})
const boxState:Record<string,string>={candidate:'候选',confirmed:'已确认',breakout_attempt:'突破尝试',breakout_confirmed:'收盘突破已确认',failed_breakout:'假突破',invalidated:'失效',expired:'已到期'}
const intradaySide:Record<string,string>={upper:'上沿',lower:'下沿',both:'上下沿'}
let adapter:ChartAdapter|null=null,mountRevision=0,returnFocus:HTMLElement|null=null,scrollLockToken:symbol|null=null
let compactPointerOrigin:{x:number;y:number}|null=null,compactPointerDragged=false
async function mount(){const revision=++mountRevision;await nextTick();if(revision!==mountRevision)return;adapter?.destroy();adapter=null;failed.value='';cursor.value=displayData.value.bars.at(-1);if(!host.value||!displayData.value.available)return;try{adapter=new ChartAdapter(host.value,displayData.value,props.cost??null,b=>cursor.value=b,selected.value);adapter.setIndicatorSelection(activeIndicators.value,showVolume.value);adapter.range(range.value)}catch{failed.value='图表初始化失败，请重新读取。数值仍可在下方查看。'}}
function reset(){range.value=100;adapter?.reset()}
function dialogFocusable(){
 if(!root.value)return [] as HTMLElement[]
 const candidates=[...root.value.querySelectorAll<HTMLElement>('button:not([disabled]),summary,[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')]
 return candidates.filter(element=>{
  if(element.hidden||element.closest('[hidden],[aria-hidden="true"]'))return false
  const collapsed=element.closest('details:not([open])')
  if(collapsed){
   const summary=collapsed.firstElementChild?.tagName==='SUMMARY'?collapsed.firstElementChild:collapsed.querySelector('summary')
   if(summary!==element)return false
  }
  return true
 })
}
async function closeExpanded(){
 if(!expanded.value)return
 expanded.value=false
 releaseDialogScrollLock(scrollLockToken);scrollLockToken=null
 await nextTick()
 adapter?.chart.resize()
 returnFocus?.focus()
 returnFocus=null
}
async function toggleExpanded(){
 if(expanded.value){await closeExpanded();return}
 returnFocus=document.activeElement instanceof HTMLElement?document.activeElement:null
 expanded.value=true
 scrollLockToken??=acquireDialogScrollLock()
 await nextTick()
 adapter?.chart.resize()
 expandButton.value?.focus()
}
function key(event:KeyboardEvent){
 if(event.key==='Escape'&&!event.defaultPrevented){
  if(indicatorPanel.value?.open){event.preventDefault();event.stopPropagation();closeIndicators();return}
  if(expanded.value){event.preventDefault();void closeExpanded();return}
 }
 if(!expanded.value||event.key!=='Tab'||!root.value)return
 const focusable=dialogFocusable()
 if(!focusable.length)return
 const first=focusable[0],last=focusable[focusable.length-1],active=document.activeElement
 if(!(active instanceof Node)||!root.value.contains(active)){
  event.preventDefault();(event.shiftKey?last:first).focus();return
 }
 if(event.shiftKey&&active===first){event.preventDefault();last.focus()}
 else if(!event.shiftKey&&active===last){event.preventDefault();first.focus()}
}
onMounted(()=>{void mount();document.addEventListener('keydown',key);document.addEventListener('pointerdown',outside);window.addEventListener('resize',positionIndicators);window.addEventListener('scroll',positionIndicators,true);window.visualViewport?.addEventListener('resize',positionIndicators);window.visualViewport?.addEventListener('scroll',positionIndicators)})
watch(()=>[props.data,props.cost,priceBasis.value],mount)
watch(()=>selected.value.join(','),()=>adapter?.setStudySelection(selected.value))
watch(()=>[activeIndicators.value.join(','),showVolume.value],()=>adapter?.setIndicatorSelection(activeIndicators.value,showVolume.value))
onBeforeUnmount(()=>{++mountRevision;adapter?.destroy();adapter=null;releaseDialogScrollLock(scrollLockToken);scrollLockToken=null;document.removeEventListener('keydown',key);document.removeEventListener('pointerdown',outside);window.removeEventListener('resize',positionIndicators);window.removeEventListener('scroll',positionIndicators,true);window.visualViewport?.removeEventListener('resize',positionIndicators);window.visualViewport?.removeEventListener('scroll',positionIndicators)})
</script>
<template><section ref="root" class="chart-workspace" :class="{'expanded-chart':expanded}" :role="expanded?'dialog':undefined" :aria-modal="expanded?true:undefined" :aria-label="expanded?(label??data.ts_code)+' K线大图':undefined">
 <div class="chart-top"><div class="range-buttons" aria-label="K线周期"><button v-for="p in periods" :key="p" :class="{active:data.interval===p}" :aria-pressed="data.interval===p" @click="emit('period',p)">{{periodNames[p]}}</button></div><div v-if="basisTransition" class="range-buttons price-basis-toggle" role="group" aria-label="K线价格口径"><button class="button small" data-testid="chart-basis-raw" :aria-pressed="priceBasis==='raw'" @click="priceBasis='raw'">原始行情</button><button class="button small" data-testid="chart-basis-research" :aria-pressed="priceBasis==='research'" @click="priceBasis='research'">拆分调整研究</button></div><div class="actions chart-actions"><button class="button small" data-testid="chart-sr-toggle" :aria-pressed="supportResistanceVisible" :disabled="!data.sr_overlay_allowed" :title="data.sr_overlay_allowed?'切换已验证支撑压力图层':'当前价格口径或快照不允许绘制支撑压力'" @click="toggleSupportResistance">显示支撑／压力</button><button class="button small" :aria-pressed="showVolume&&volumeAvailable(data)" :disabled="!volumeAvailable(data)" :title="volumeAvailable(data)?'切换真实成交量副图':'当前没有成交量，未知量额不补零'" @click="showVolume=!showVolume">成交量</button>
 <details ref="indicatorPanel" class="indicator-picker" data-testid="indicator-picker" @toggle="positionIndicators"><summary>技术指标 <span>{{indicatorCount}}</span></summary><div class="indicator-menu" :style="menuPosition"><header><strong>技术指标</strong><button type="button" class="icon-button" aria-label="关闭技术指标" @click="closeIndicators">×</button></header><p>已应用 · {{periodNames[data.interval]??data.interval}}</p><div class="applied-indicators"><button v-for="key in activeIndicators" :key="key" class="indicator-chip" :aria-label="'移除 '+key" @click="indicators=indicators.filter(item=>item!==key)">{{key}} ×</button><span v-if="!activeIndicators.length" class="small-note">未选择价格技术指标</span></div><hr><label v-for="study in serverStudies" :key="study.key" class="indicator-option"><input v-model="indicators" type="checkbox" :value="study.key" :disabled="!studyAvailable(data,study.key)" :aria-label="'显示 '+study.key"><span><b>{{study.key}} · {{study.label}}</b><small>{{study.pane}} · {{study.parameters}}</small><small v-if="!studyAvailable(data,study.key)">该周期无有效服务端数值</small></span></label><p class="small-note">此处只控制图层，参数与数值由服务端提供。EMA、SAR、BBI 等尚未接入，不能仅靠增加按钮冒充实现。</p><button class="button small" @click="indicators=['MA'];showVolume=false">恢复默认指标</button></div></details>
 <details><summary>显示范围</summary><div class="range-buttons"><button v-for="n in [60,100,250]" :key="n" @click="range=n;adapter?.range(n)">{{n}} 根</button></div></details><button class="button small" @click="reset" data-testid="chart-reset">复位图表</button><button ref="expandButton" class="button small" data-testid="chart-fullscreen" :aria-expanded="expanded" @click="toggleExpanded">{{expanded?'关闭大图':'放大图表'}}</button></div></div>
 <div class="study-controls" aria-label="辅助线与指标"><strong class="study-caption">研究图层</strong><label v-for="g in groups" :key="g"><input v-model="selected" type="checkbox" :value="g"/>{{names[g]}}</label><button class="button small" @click="selected=[...groups]">打开全部</button><button class="button small" @click="selected=[]">隐藏全部</button></div>
 <div class="chart-legend"><strong>{{label??data.ts_code}}</strong><span v-if="data.cost_overlay_allowed&&cost" style="color:#d8b776" data-testid="chart-cost-label">我的成本 {{num(cost,3)}}</span><span>{{cursor?.date??'—'}}</span><span>开 {{num(cursor?.open,3)}}</span><span>高 {{num(cursor?.high,3)}}</span><span>低 {{num(cursor?.low,3)}}</span><span>收 {{num(cursor?.close,3)}}</span><span v-if="cursor?.is_partial">本周期未结束</span></div>
 <div v-if="failed" class="notice error-notice">{{failed}}</div><div ref="host" class="chart" :class="{'chart-clickable':!expanded}" :role="expanded?'img':'button'" tabindex="0" :aria-label="expanded?(label??'ETF')+' K线大图，支持滚轮缩放、拖拽平移和双击复位':(label??'ETF')+' K线，点击放大；支持滚轮缩放和拖拽平移'" data-testid="etf-chart" @pointerdown.capture="chartPointerDown" @pointermove.capture="chartPointerMove" @pointercancel.capture="resetCompactPointer" @click="openCompactChart" @keydown.enter.prevent="openCompactChart" @keydown.space.prevent="openCompactChart" @dblclick.stop="reset"/>
 <div class="chart-legend" data-testid="chart-indicators"><span v-for="key in ['macd_dif','macd_dea','macd_hist','kdj_k','kdj_d','kdj_j','rsi14']" :key="key">{{key.toUpperCase()}} {{num(cursor?.indicators[key],key.startsWith('macd')?6:2)}}</span></div>
 <div v-if="levels.length" class="chart-legend" aria-label="当前支撑压力快照价位"><span v-for="(l,i) in levels" :key="i" :title="Array.isArray(l.methods)?l.methods.join('、'):''" :class="{bear:levelDirection(l)==='support',bull:levelDirection(l)==='resistance'}">{{levelDirectionLabel(l)}} {{num(levelPrice(l),3)}}</span></div>
 <details v-if="levels.length" class="zone-notes" data-testid="chart-level-evidence"><summary>查看支撑压力价位依据（{{levels.length}}）</summary><p class="small-note">窄图保留原价格线，长说明移到这里，避免遮挡蜡烛；结构价位只计独立价格触碰。</p><ul><li v-for="(l,i) in levels" :key="i">{{levelDirectionLabel(l)}} {{num(levelPrice(l),3)}} · {{Array.isArray(l.methods)?l.methods.join(' / '):'价格研究'}}{{l.category==='price_structure'?` · ${l.touch_count} 次独立触碰`:''}}</li></ul></details>
 <section class="zone-notes" data-testid="chart-box-evidence" aria-label="日线箱体证据"><strong>箱体研究 · {{periodNames[data.interval]??data.interval}}</strong><p role="status">{{structureText}}</p><ul v-if="displayedBox"><li>{{boxState[displayedBox.state]??displayedBox.state}} · {{displayedBox.origin_at}} 至 {{displayedBox.valid_until??data.price_structures?.source_as_of_date??'—'}}；上沿 {{num(displayedBox.upper,3)}}（{{displayedBox.upper_touch_count}} 次）、下沿 {{num(displayedBox.lower,3)}}（{{displayedBox.lower_touch_count}} 次）；{{displayedBox.volume_confirmation_available?'量能字段可用':'量能确认不可用'}}。确认日 {{displayedBox.confirmed_at??'未确认'}}。</li></ul><ul v-else-if="candidateBox"><li>候选未确认 · {{candidateBox.origin_at}} 至 {{candidateBox.as_of_date??'—'}}；上沿 {{num(candidateBox.upper,3)}}（{{candidateBox.upper_touch_count??'—'}} 次）、下沿 {{num(candidateBox.lower,3)}}（{{candidateBox.lower_touch_count??'—'}} 次）。</li></ul><p v-if="displayedBox?.intraday_state" role="status" data-testid="chart-box-intraday-attempt">盘中{{intradaySide[displayedBox.intraday_state.side]??'边界'}}越界尝试 · {{displayedBox.intraday_state.observed_at??'时间待核实'}}；这是临时观察，不改变已结算箱体状态。</p><p v-if="data.price_structures?.read_as_of" class="small-note">输入截止 {{data.price_structures.source_as_of_date??'—'}} · 页面读取 {{data.price_structures.read_as_of}}</p></section>
 <p v-if="basisTransition&&priceBasis==='raw'" class="small-note" role="status">原始行情按来源数值显示；与拆分调整研究序列价格口径不同，未能映射的指标及支撑压力已隐藏。</p><p v-else-if="priceBasis==='research'" class="small-note" role="status">当前显示拆分调整研究价格；该序列只用于价格连续性研究，不代表总收益。</p><p v-if="selected.includes('CHAN')" class="small-note" role="status" data-testid="chart-chan-note">{{chanNote}}</p><p class="small-note">{{periodNames[data.interval]??data.interval}}的价格研究参考；MACD/KDJ/RSI只确认历史价格拐点，不将指标数值换成价格。缠论勾选绘制简化笔、线段和中枢，不是完整 CZSC。水平价位中的重叠区仍是近似。打开全部不表示更多独立证据。</p><div class="chart-bottom"><span>滚轮缩放 · 拖拽平移 · 双击复位</span><span>{{priceBasis==='research'?data.research_price_basis:data.display_price_basis??(data.adjust==='none'?'未复权':data.adjust)}} · {{data.indicator_version}}</span></div>
 <ChanEvidenceCard v-if="selected.includes('CHAN')" :key="`${data.ts_code}:${data.interval}:${data.chan_observation?.observation_id ?? ''}`" :observation="data.chan_observation" />
 </section></template>
<style scoped>.zone-notes{padding:10px 8px;overflow-wrap:anywhere}.zone-notes summary{cursor:pointer;min-height:40px}.zone-notes li{margin:8px 0;font-size:13px;line-height:1.7}.chart-workspace{background:var(--surface,#12181e)}.study-controls{display:flex;gap:12px;flex-wrap:wrap;padding:12px 4px;align-items:center}.study-controls label{display:flex;align-items:center;gap:5px;font-size:13px}.study-controls input{width:auto}.expanded-chart{position:fixed;inset:clamp(8px,3vh,28px) clamp(8px,3vw,36px);z-index:2000;padding:18px;overflow:auto;border:1px solid var(--border);border-radius:12px;background:var(--surface,#12181e);box-shadow:0 0 0 100vmax #000b,0 24px 80px #000c}.expanded-chart .chart{height:min(68dvh,760px);min-height:420px}.chart-clickable{cursor:zoom-in}.chart-clickable:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}.chart-top{flex-wrap:wrap;gap:12px}.chart-legend{font-size:13px;line-height:1.8}.small-note{padding:8px;font-size:13px}.chart-actions{position:relative}.indicator-picker{position:relative}.indicator-picker>summary{list-style:none;border:1px solid var(--border);border-radius:6px;padding:9px 12px;cursor:pointer;color:var(--accent);min-height:36px;display:flex;align-items:center;gap:9px}.indicator-picker>summary span{font-size:11px;background:#13353f;padding:1px 5px;border-radius:4px}.indicator-menu{position:absolute;right:0;top:calc(100% + 9px);width:330px;max-width:calc(100vw - 48px);max-height:min(620px,70dvh);overflow:auto;z-index:60;background:#131e29;border:1px solid #344656;border-radius:10px;padding:16px;box-shadow:0 18px 44px #0009}.indicator-menu header{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:16px}.indicator-menu p{font-size:12px;color:var(--muted);margin:10px 0}.indicator-menu hr{border:0;border-top:1px solid #30414f;margin:16px 0}.applied-indicators{display:flex;gap:7px;flex-wrap:wrap}.indicator-chip{border:1px solid #31586d;color:#81cdf1;background:#192e3e;border-radius:6px;padding:7px 10px}.indicator-option{display:flex;gap:12px;align-items:flex-start;min-height:58px;padding:10px 5px;border-radius:6px}.indicator-option:hover{background:#203242}.indicator-option input{width:16px;height:16px;flex:none;margin:3px 0}.indicator-option b{font-size:13px;font-weight:500}.indicator-option small{display:block;font-size:11px;line-height:1.7;margin-top:4px}.study-caption{color:var(--muted);font-size:12px;font-weight:400;margin:0 6px}.study-controls{border-block:1px solid var(--border);padding:12px 18px}.chart-top{background:#0e151f}.chart-legend strong{color:var(--text)}@media(max-width:600px){.chart-actions{width:100%}.indicator-picker{position:relative}.indicator-menu{left:0;right:auto;width:min(330px,100%);max-width:100%}.chart-actions>.button,.indicator-picker>summary{min-height:44px}.indicator-option{min-height:62px}.chart-top{padding:12px}.study-controls{padding:10px 12px;gap:9px}}
@media(max-width:600px){.expanded-chart{inset:6px;padding:10px}.expanded-chart .chart{height:78dvh;min-height:560px;max-height:720px}.expanded-chart .study-controls{max-height:120px;overflow:auto}}</style>
