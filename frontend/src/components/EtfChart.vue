<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { ChartAdapter, groupsForLevel } from '../lib/chartAdapter'
import { num, levelPrice } from '../lib/format'
import type { ChartBar, ChartData } from '../lib/types'
const props=defineProps<{data:ChartData;cost?:number|null;label?:string;allowMinutes?:boolean}>()
const emit=defineEmits<{period:[value:string]}>()
const root=ref<HTMLElement|null>(null),host=ref<HTMLElement|null>(null),cursor=ref<ChartBar>(),failed=ref(''),range=ref(100),fullscreen=ref(false)
const periods=computed(()=>[...['1d','1w','1mo'],...(props.allowMinutes?['30m','60m']:[])])
const periodNames:Record<string,string>={'1d':'日 K','1w':'周 K','1mo':'月 K','30m':'30 分钟','60m':'小时 K'}
const groups=['MA','PIVOT','BOLL','ATR','FIB','MACD','KDJ','RSI','CHAN']
const names:Record<string,string>={MA:'均线',PIVOT:'价格拐点',BOLL:'布林带',ATR:'波幅带',FIB:'斐波那契',MACD:'MACD',KDJ:'KDJ',RSI:'RSI',CHAN:'重叠区近似'}
const selected=ref(['MA','PIVOT','MACD','KDJ','RSI'])
const levels=computed(()=>props.data.sr_overlay_allowed?[...(props.data.support_resistance?.levels??[])].filter(x=>levelPrice(x)!=null&&groupsForLevel(x).some(g=>selected.value.includes(g))).sort((a,b)=>Math.abs(levelPrice(a)!-(props.data.bars.at(-1)?.close??0))-Math.abs(levelPrice(b)!-(props.data.bars.at(-1)?.close??0))).slice(0,12):[])
let adapter:ChartAdapter|null=null,mountRevision=0
async function mount(){const revision=++mountRevision;await nextTick();if(revision!==mountRevision)return;adapter?.destroy();adapter=null;failed.value='';cursor.value=props.data.bars.at(-1);if(!host.value||!props.data.available)return;try{adapter=new ChartAdapter(host.value,props.data,props.cost??null,b=>cursor.value=b,selected.value);adapter.range(range.value)}catch{failed.value='图表初始化失败，请重新读取。数值仍可在下方查看。'}}
function reset(){range.value=100;adapter?.reset()}
async function toggleFullscreen(){if(fullscreen.value){if(document.fullscreenElement)await document.exitFullscreen().catch(()=>{});fullscreen.value=false}else{fullscreen.value=true;await root.value?.requestFullscreen?.().catch(()=>{})}await nextTick();adapter?.chart.resize()}
function escape(event:KeyboardEvent){if(event.key==='Escape'){fullscreen.value=false;void nextTick(()=>adapter?.chart.resize())}}
function fullscreenChanged(){fullscreen.value=!!document.fullscreenElement}
onMounted(()=>{void mount();document.addEventListener('keydown',escape);document.addEventListener('fullscreenchange',fullscreenChanged)})
watch(()=>[props.data,props.cost,selected.value.join(',')],mount)
onBeforeUnmount(()=>{++mountRevision;adapter?.destroy();adapter=null;document.removeEventListener('keydown',escape);document.removeEventListener('fullscreenchange',fullscreenChanged)})
</script>
<template><section ref="root" class="chart-workspace" :class="{'expanded-chart':fullscreen}">
 <div class="chart-top"><div class="range-buttons" aria-label="K线周期"><button v-for="p in periods" :key="p" :class="{active:data.interval===p}" :aria-pressed="data.interval===p" @click="emit('period',p)">{{periodNames[p]}}</button></div><div class="actions"><details><summary>显示范围</summary><div class="range-buttons"><button v-for="n in [60,100,250]" :key="n" @click="range=n;adapter?.range(n)">{{n}} 根</button></div></details><button class="button small" @click="reset" data-testid="chart-reset">复位图表</button><button class="button small" data-testid="chart-fullscreen" @click="toggleFullscreen">{{fullscreen?'退出全屏':'全屏图表'}}</button></div></div>
 <div class="study-controls" aria-label="辅助线与指标"><label v-for="g in groups" :key="g"><input v-model="selected" type="checkbox" :value="g"/>{{names[g]}}</label><button class="button small" @click="selected=[...groups]">打开全部</button><button class="button small" @click="selected=[]">隐藏全部</button></div>
 <div class="chart-legend"><span v-if="data.cost_overlay_allowed&&cost" style="color:#d8b776" data-testid="chart-cost-label">我的成本 {{num(cost,3)}}</span><span>{{cursor?.date??'—'}}</span><span>开 {{num(cursor?.open,3)}}</span><span>高 {{num(cursor?.high,3)}}</span><span>低 {{num(cursor?.low,3)}}</span><span>收 {{num(cursor?.close,3)}}</span><span v-if="cursor?.is_partial">本周期未结束</span></div>
 <div v-if="failed" class="notice error-notice">{{failed}}</div><div ref="host" class="chart" role="img" :aria-label="(label??'ETF')+' K线，支持滚轮缩放、拖拽平移和双击复位'" data-testid="etf-chart" @dblclick="reset"/>
 <div class="chart-legend" data-testid="chart-indicators"><span v-for="key in ['macd_dif','macd_dea','macd_hist','kdj_k','kdj_d','kdj_j','rsi14']" :key="key">{{key.toUpperCase()}} {{num(cursor?.indicators[key],key.startsWith('macd')?6:2)}}</span></div>
 <div v-if="levels.length" class="chart-legend" aria-label="当前支撑压力快照价位"><span v-for="(l,i) in levels" :key="i" :title="Array.isArray(l.methods)?l.methods.join('、'):''" :class="String(l.kind).includes('support')?'bear':'bull'">{{String(l.kind).includes('support')?'支撑':'压力'}} {{num(levelPrice(l),3)}}</span></div>
 <p class="small-note">{{periodNames[data.interval]??data.interval}}的价格研究参考；MACD/KDJ/RSI只确认历史价格拐点，不将指标数值换成价格。重叠区是缠论近似，不是完整笔、线段和中枢。打开全部不表示更多独立证据。</p><div class="chart-bottom"><span>滚轮缩放 · 拖拽平移 · 双击复位</span><span>{{data.adjust==='none'?'未复权':data.adjust}} · {{data.indicator_version}}</span></div>
 </section></template>
<style scoped>.chart-workspace{background:var(--surface,#12181e)}.study-controls{display:flex;gap:12px;flex-wrap:wrap;padding:12px 4px;align-items:center}.study-controls label{display:flex;align-items:center;gap:5px;font-size:13px}.study-controls input{width:auto}.expanded-chart,.chart-workspace:fullscreen{position:fixed;inset:0;z-index:2000;padding:18px;overflow:auto}.expanded-chart .chart,.chart-workspace:fullscreen .chart{height:calc(100dvh - 270px);min-height:360px}.chart-top{flex-wrap:wrap;gap:12px}.chart-legend{font-size:13px;line-height:1.8}.small-note{padding:8px;font-size:13px}</style>
