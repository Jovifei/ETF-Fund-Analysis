<script setup lang="ts">
import { computed, onActivated, onDeactivated, onBeforeUnmount, ref, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { RefreshCw } from 'lucide-vue-next'
import { useQuery } from '../lib/query'
import { api, errorText } from '../lib/api'
import { num, pct, direction, stamp, record, numeric } from '../lib/format'
import { useSession } from '../stores/session'
import OriginalDecisionBoard from '../components/OriginalDecisionBoard.vue'
import Badge from '../components/Badge.vue'
import EtfChart from '../components/EtfChart.vue'
import PageState from '../components/PageState.vue'
import type { ChartData, DataJob } from '../lib/types'
defineOptions({ name: 'MarketOverview' })
type IndexChart = ChartData & {summary?:{price:number|null;change_ratio:number|null;source_time:string|null}}
const route = useRoute(), router = useRouter(), session = useSession(), board = ref<InstanceType<typeof OriginalDecisionBoard> | null>(null)
const market = useQuery<Record<string, unknown>>('/api/market-context')
const sectors = useQuery<Record<string, unknown>>('/api/workspace/sectors')
const discovery = useQuery<Record<string, unknown>>('/api/workspace/discovery')
const indexCache=useQuery<{items:Record<string,unknown>[]}>('/api/workspace/indexes')
const contextCards = computed(() => {
  const items=(Array.isArray(market.data.value?.latest_view)?market.data.value!.latest_view:[]).map(record).filter(x=>['index','tradable_proxy'].includes(String(x.context_kind)))
  for(const cached of indexCache.data.value?.items??[]){
    const at=items.findIndex(x=>x.context_id===cached.context_id)
    if(at<0) items.push(cached)
    else if(items[at].observed_value==null||String(cached.source_timestamp).slice(0,10)>String(items[at].source_timestamp??'').slice(0,10))items[at]=cached
  }
  return items
})
const selectedContextId = ref('')
const selectedContext = computed(() => contextCards.value.find(x => String(x.context_id) === selectedContextId.value))
const contextHistory = useQuery<IndexChart>(() => selectedContextId.value ? `/api/workspace/indexes/${encodeURIComponent(selectedContextId.value)}/chart?limit=500` : null)
function openContext(item: Record<string, unknown>) {
  const code = String(item.display_code ?? '').trim()
  if (item.is_tradable_proxy && code) { void router.push(`/etf/${encodeURIComponent(code)}`); return }
  selectedContextId.value = String(item.context_id ?? '')
}
async function syncIndex() {
  busy.value=true; error.value=''; notice.value=''
  try { await api<{job:DataJob}>('/api/workspace/data-jobs',{method:'POST',body:{task:'index_history',codes:[],lookback_days:1200,request_key:crypto.randomUUID()}}); notice.value='三只 A 股指数历史已排队；完成后点重新读取。历史缓存跨重启保留。' }
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
const allBoards = computed(() => (Array.isArray(sectors.data.value?.boards) ? sectors.data.value!.boards : []).map(record))
const breadth = computed(() => allBoards.value.filter(x => x.board_type === 'market'))
const sectorKind = ref('industry'), sectorFilter = ref(''), showAll = ref(false)
const filtered = computed(() => allBoards.value.filter(x => x.board_type === sectorKind.value && (!sectorFilter.value || String(x.sector_name).includes(sectorFilter.value))).sort((a,b) => (numeric(b.sector_pct_change) ?? -Infinity) - (numeric(a.sector_pct_change) ?? -Infinity)))
const sectorItems = computed(() => filtered.value.slice(0, showAll.value ? 2000 : 12))
const busy = ref(false), notice = ref(''), error = ref('')
const canSync = computed(() => session.role === 'admin' || !session.identifier)
async function syncDiscovery() {
  busy.value = true; error.value = ''; notice.value = ''
  try { await api('/api/workspace/discovery/refresh', { method: 'POST' }); notice.value = '目录与板块任务已排队；由工作器采集，完成后自动重新读取。'; await discovery.reload() }
  catch (e) { error.value = errorText(e) } finally { busy.value = false }
}
async function reload() { await Promise.all([market.reload(), sectors.reload(), discovery.reload(), board.value?.reload(), contextHistory.reload(), indexCache.reload()]) }
let timer: ReturnType<typeof setInterval> | undefined, scrollY = 0
onActivated(async () => {
  await nextTick()
  if (!route.hash) window.scrollTo(0, scrollY)
  clearInterval(timer)
  timer = setInterval(() => { if (!document.hidden) void reload() }, 60000)
})
onDeactivated(() => { scrollY = window.scrollY; clearInterval(timer) })
onBeforeUnmount(() => clearInterval(timer))
async function recompute(){if(busy.value)return;busy.value=true;error.value='';try{await api('/api/workspace/data-jobs',{method:'POST',body:{task:'recompute',request_key:crypto.randomUUID()}});notice.value='已排队重算已存历史：不重新取行情，不调用模型。完成后点击重新读取；可在设置查看任务。'}catch(e){error.value=errorText(e)}finally{busy.value=false}}
</script>
<template><section>
  <div class="page-heading"><div><p class="eyebrow">MARKET OVERVIEW / ETF</p><h1>市场总览</h1><p>A 股市场 → 行业 / 概念板块 → ETF 决策快照。所有分析都在同一工作站。</p></div>
    <button class="button" @click="reload"><RefreshCw :size="14"/>重新读取</button></div>
  <nav class="section-tabs" aria-label="总览内容"><a href="#market-boards">行业与概念</a><a href="#etf-decisions">ETF 决策快照</a><RouterLink to="/analysis">搜索全部 ETF / LOF</RouterLink></nav>
  <div v-if="route.query.mode === '1430'" class="notice warning-notice">14:30 为同一总览的研究模式，不是另一套动作。历史分钟验证尚未取得资格。</div>
  <div class="cards market-context-cards"><article v-for="item in contextCards" :key="String(item.context_id)" class="stat-card market-context-card" role="button" tabindex="0" :aria-label="`查看${item.label}历史数据`" @click="openContext(item)" @keydown.enter="openContext(item)"><div class="label">{{ item.label }}</div><div class="value">{{ num(item.observed_value) }} <span class="delta" :class="direction(numeric(item.today_pct_change))">{{ pct(numeric(item.today_pct_change) == null ? null : Number(item.today_pct_change)/100) }}</span></div><small>{{item.freshness==='historical'?(item.is_partial?'盘中日线未收盘':'最近历史收盘'):'最近观测'}} · {{ item.source ?? '尚未取得指数数据' }} · {{ stamp(item.source_timestamp) }} · {{ item.freshness ?? 'unavailable' }}</small><span class="small-note">{{ item.is_tradable_proxy && item.display_code ? '打开对应 ETF K 线' : '查看指数 K 线' }}</span></article>
    <article v-if="!contextCards.length" class="stat-card"><div class="label">市场指数上下文</div><div class="value">待同步</div><small>{{ market.error.value || '使用原有市场数据接入，不使用 ETF 样本冒充指数。' }}</small></article></div>
  <section v-if="selectedContext" class="card market-context-detail" aria-live="polite"><div class="card-header"><div><h2>{{selectedContext.label}} · 指数 K 线</h2><small>最近历史收盘 {{num(contextHistory.data.value?.summary?.price)}} · {{pct(contextHistory.data.value?.summary?.change_ratio)}} · {{contextHistory.data.value?.source_as_of??'尚未同步'}}；不冒充今日实时</small></div><div class="actions"><button v-if="canSync" class="button small" :disabled="busy" @click="syncIndex">下载指数历史</button><button class="button small" @click="contextHistory.reload()">重新读取 K 线</button><button class="button small" @click="selectedContextId=''">关闭</button></div></div><PageState :loading="contextHistory.loading.value" :error="contextHistory.error.value" :empty="!contextHistory.data.value?.available" title="指数历史尚未准备" description="需要管理员下载真实开高低收数据。旧点位快照不拼成蜡烛图；下载失败保留已有历史。" @retry="contextHistory.reload"><EtfChart v-if="contextHistory.data.value?.available" :data="contextHistory.data.value" :label="String(selectedContext.label)"/></PageState></section>
  <div class="card section" data-testid="full-market-breadth"><div class="card-header"><h2>全市场涨跌宽度</h2><small>独立 A 股快照，非 ETF 样本</small></div><div class="card-body"><div v-for="item in breadth" :key="String(item.sector_name)" class="actions"><strong>{{ item.sector_name }}</strong><span class="bull">上涨 {{ num(record(item.breadth).up,0) }}</span><span class="bear">下跌 {{ num(record(item.breadth).down,0) }}</span><span>平盘 {{ num(record(item.breadth).flat,0) }}</span><small>{{ item.source }} · {{ item.source_as_of }}</small></div><p v-if="!breadth.length" class="muted">尚无全市场宽度快照，缺失项不填零。</p></div></div>
  <section id="market-boards" class="card section" aria-labelledby="boards-heading"><div class="card-header"><div><h2 id="boards-heading">行业与概念板块</h2><p>读取原有行业 / 概念 / 全市场快照；每类数据独立显示。</p></div><button v-if="canSync" class="button" :disabled="busy" @click="syncDiscovery">同步市场目录与板块</button></div>
    <div class="toolbar"><button class="button" :class="{primary:sectorKind==='industry'}" @click="sectorKind='industry';showAll=false">行业板块</button><button class="button" :class="{primary:sectorKind==='concept'}" @click="sectorKind='concept';showAll=false">概念板块</button><input v-model="sectorFilter" aria-label="筛选板块" placeholder="筛选板块名称"/><small>{{ filtered.length }} 个板块 · 可搜索基金 {{ discovery.data.value?.catalog_count ?? '—' }} 个</small></div>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p><p v-if="error" class="notice warning-notice" role="alert">{{ error }}</p>
    <div v-if="!sectorItems.length" class="card-body muted">{{ sectors.error.value || '该类别尚无数据。同步任务完成后会显示；其他类别的数据不会被一起隐藏。' }}<span v-if="!canSync"> 请管理员在总览同步。</span></div>
    <div class="sector-grid"><article v-for="s in sectorItems" :key="String(s.board_type)+String(s.sector_name)" class="sector-tile" :class="direction(s.sector_pct_change)"><strong>{{ s.sector_name }}</strong><span class="numeric">{{ pct(numeric(s.sector_pct_change)==null?null:Number(s.sector_pct_change)/100) }}</span><small>{{ s.source }} · {{ s.source_as_of }} · {{ s.is_mock ? '演示' : '源时间未验证' }}</small><RouterLink class="text-button" :to="{path:'/analysis',query:{q:String(s.sector_name)}}">查找相关 ETF →</RouterLink></article></div>
    <div class="table-footer"><span>板块快照日期 {{ sectors.data.value?.source_as_of ?? '未知' }}；匹配 ETF 按名称 / 主题检索，不冒充成分映射。</span><button v-if="filtered.length>12" class="button small" @click="showAll=!showAll">{{ showAll?'收起':'显示全部板块' }}</button></div>
    <div class="card-body"><span v-for="job in (Array.isArray(discovery.data.value?.jobs)?discovery.data.value!.jobs:[])" :key="String(record(job).task)" class="small-note">{{ record(job).task }}：<Badge :value="String(record(job).status)"/> {{ stamp(record(job).finished_at ?? record(job).created_at) }}　</span><RouterLink to="/settings">查看采集步骤和失败原因</RouterLink></div>
  </section>
  <div class="toolbar"><button v-if="canSync" class="button" :disabled="busy" @click="recompute">重算已存历史指标</button><span class="small-note">已有 K 线但决策快照为空：可先离线重算。单只基金数据不全，不影响其他标的；无历史时在 ETF 详情补齐。</span></div>
  <OriginalDecisionBoard ref="board"/>
</section></template>
<style scoped>
.market-context-card { cursor: pointer; }
.market-context-card:focus-visible { outline: 2px solid var(--accent, #27c5d8); outline-offset: 2px; }
.market-context-card .small-note { display: block; margin-top: 8px; }
.market-context-detail { margin-top: 16px; }
.market-context-chart { display: block; width: 100%; min-height: 150px; color: var(--accent, #27c5d8); background: rgba(0, 0, 0, .12); border-radius: 8px; }
</style>
