<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { withGeneration } from '../lib/generation'
import { useQuery } from '../lib/query'
import { num, pct, direction } from '../lib/format'
import { acquireDialogScrollLock, releaseDialogScrollLock } from '../lib/dialogScrollLock'
import type { ChartData, Detail } from '../lib/types'
import EtfChart from './EtfChart.vue'
import Badge from './Badge.vue'

export interface SectorItem {
  sector_name: string
  board_type: string
  sector_pct_change?: number | null
  source_as_of?: string
  source?: string
  is_mock?: boolean
  up_count?: number | null
  down_count?: number | null
  flat_count?: number | null
  total_count?: number | null
}

export interface RepresentativeMapping {
  sector_name: string
  theme_l1: string
  theme_l2: string
  representative_etf: {
    ts_code: string
    symbol: string
    name: string
    fund_company: string
  }
  tracking_index: {
    code: string
    name: string
  }
  mapping_type: string
  basis: string
  effective_from: string
  effective_to: string
  qualification: string
  status: string
}

const props = defineProps<{
  modelValue: boolean
  sector: SectorItem | null
  generation?: string | number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'close': []
}>()

let scrollLockToken: symbol | null = null

watch(() => props.modelValue, (isOpen) => {
  if (isOpen) {
    scrollLockToken = acquireDialogScrollLock()
  } else {
    releaseDialogScrollLock(scrollLockToken)
    scrollLockToken = null
  }
})

onBeforeUnmount(() => {
  if (scrollLockToken) {
    releaseDialogScrollLock(scrollLockToken)
    scrollLockToken = null
  }
})

function close() {
  emit('update:modelValue', false)
  emit('close')
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.modelValue) {
    close()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
})

const activeTab = ref<'rep_etf' | 'index_breadth'>('rep_etf')
const interval = ref('1d')

// 1. Fetch representative mappings
const repMapQuery = useQuery<{ mappings: RepresentativeMapping[]; total: number }>(
  () => props.modelValue ? '/api/workspace/sectors/representatives' : null
)

const currentMapping = computed<RepresentativeMapping | null>(() => {
  if (!props.sector || !repMapQuery.data.value?.mappings) return null
  const name = props.sector.sector_name.trim()
  const mappings = repMapQuery.data.value.mappings
  // Exact match
  const exact = mappings.find(m => m.sector_name === name)
  if (exact) return exact
  // Substring match
  const sub = mappings.find(m => name.includes(m.sector_name) || m.sector_name.includes(name))
  return sub ?? null
})

const repCode = computed(() => currentMapping.value?.representative_etf.ts_code ?? null)
const indexCode = computed(() => currentMapping.value?.tracking_index.code ?? null)

// 2. Fetch Representative ETF Detail & Decision
const etfDetailUrl = computed(() => {
  if (!repCode.value) return null
  return withGeneration(
    `/api/workspace/instruments/${encodeURIComponent(repCode.value)}`,
    props.generation
  )
})
const etfDetailQuery = useQuery<Detail>(etfDetailUrl)

// 3. Fetch Representative ETF Chart
const etfChartUrl = computed(() => {
  if (!repCode.value) return null
  const asOf = etfDetailQuery.data.value?.read_as_of
  const asOfParam = asOf ? `&as_of=${encodeURIComponent(asOf)}` : ''
  return withGeneration(
    `/api/workspace/instruments/${encodeURIComponent(repCode.value)}/chart?interval=${interval.value}&limit=250${asOfParam}`,
    props.generation
  )
})
const etfChartQuery = useQuery<ChartData>(etfChartUrl)

// 4. Fetch Index Chart
const indexChartUrl = computed(() => {
  if (!indexCode.value) return null
  return withGeneration(
    `/api/workspace/indexes/${encodeURIComponent(indexCode.value)}/chart?limit=250`,
    props.generation
  )
})
const indexChartQuery = useQuery<ChartData>(indexChartUrl)

// Breadth statistics calculation
const breadthStats = computed(() => {
  const up = props.sector?.up_count ?? 0
  const down = props.sector?.down_count ?? 0
  const flat = props.sector?.flat_count ?? 0
  const total = props.sector?.total_count || (up + down + flat) || 1
  return {
    up,
    down,
    flat,
    total,
    upPct: Math.round((up / total) * 100),
    downPct: Math.round((down / total) * 100),
    flatPct: Math.round((flat / total) * 100),
  }
})

interface AdjustmentInfo {
  applied?: boolean
  base_grade?: string
  final_grade?: string
  weight?: number
  [key: string]: unknown
}

function getLevelPrice(level: unknown): number | null {
  if (level == null) return null
  if (typeof level === 'number') return level
  if (typeof level === 'object') {
    const obj = level as Record<string, unknown>
    if (typeof obj.price === 'number') return obj.price
    if (typeof obj.level === 'number') return obj.level
  }
  return null
}

const GRADE_NAMES: Record<string, string> = {
  '5': '5档 · 可加仓',
  '4': '4档 · 可入场',
  '3': '3档 · 可试探',
  '2': '2档 · 观望',
  '1': '1档 · 减仓',
}
function gradeName(grade: string): string {
  return GRADE_NAMES[grade] ?? grade
}

// Decision, Levels & Structure
const decision = computed(() => etfDetailQuery.data.value?.decision)
const gradeFinal = computed(() => decision.value?.grade_final || decision.value?.grade || '—')
const gradeBase = computed(() => decision.value?.grade_base || '—')
const adjustment = computed<AdjustmentInfo | null>(() => {
  const adj = decision.value?.adjustment
  if (adj && typeof adj === 'object') return adj as AdjustmentInfo
  return null
})
const supportResistance = computed(() => decision.value?.support_resistance || etfChartQuery.data.value?.support_resistance)
const structureFactors = computed(() => {
  const d = decision.value as Record<string, unknown> | undefined
  const structV1 = d?.structure_v1 as Record<string, unknown> | undefined
  const structShadow = d?.structure_shadow as Record<string, unknown> | undefined
  return {
    wyckoff: structV1?.wyckoff_phase || structShadow?.signal || '未定义',
    dow: structV1?.dow_phase || '未定义',
    atrBucket: structV1?.atr_risk_bucket || '未评定',
  }
})

function onPeriodChange(newPeriod: string) {
  interval.value = newPeriod
}
</script>

<template>
  <div v-if="modelValue" class="drawer-backdrop" @click="close">
    <aside class="sector-drawer" role="dialog" aria-modal="true" @click.stop>
      <!-- Drawer Header -->
      <header class="drawer-header">
        <div class="header-main">
          <div class="title-row">
            <h2>{{ sector?.sector_name }} 板块研判</h2>
            <span class="sector-tag">{{ sector?.board_type === 'concept' ? '概念板块' : '行业板块' }}</span>
          </div>
          <div class="header-metrics">
            <span class="pct-badge" :class="direction(sector?.sector_pct_change)">
              涨跌幅 {{ pct(sector?.sector_pct_change == null ? null : Number(sector?.sector_pct_change) / 100) }}
            </span>
            <small class="muted">快照日期: {{ sector?.source_as_of ?? '—' }}</small>
            <span v-if="sector?.is_mock" class="mock-badge">演示数据</span>
          </div>
        </div>
        <button class="close-btn" aria-label="关闭抽屉" @click="close">&times;</button>
      </header>

      <!-- Representative Mapping Info -->
      <section class="rep-bar" :class="{ 'has-mapping': !!currentMapping }">
        <div v-if="currentMapping" class="rep-content">
          <div class="rep-title">
            <strong>主力代表 ETF：{{ currentMapping.representative_etf.name }} ({{ currentMapping.representative_etf.ts_code }})</strong>
            <span class="fund-company-badge">{{ currentMapping.representative_etf.fund_company }}</span>
            <Badge :value="currentMapping.mapping_type === 'primary_tracker' ? '主力跟踪' : '代理映射'" />
          </div>
          <p class="rep-basis">依据：{{ currentMapping.basis }}</p>
          <div class="rep-meta">
            <span>跟踪指数：{{ currentMapping.tracking_index.name }} ({{ currentMapping.tracking_index.code }})</span>
            <span>有效期：{{ currentMapping.effective_from }} ~ {{ currentMapping.effective_to }}</span>
            <span>口径资质：{{ currentMapping.qualification }}</span>
          </div>
        </div>
        <div v-else class="rep-content rep-empty">
          <p>当前板块暂无经过资质认定的代表 ETF 映射关系（将仅展示纯板块走势与广度）。</p>
        </div>
      </section>

      <!-- Tabs Navigation -->
      <nav class="drawer-tabs">
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'rep_etf' }"
          :disabled="!currentMapping"
          @click="activeTab = 'rep_etf'"
        >
          主力代表 ETF 行情与研判 (实盘 K 线 / 支撑压力 / 结构因子)
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'index_breadth' }"
          @click="activeTab = 'index_breadth'"
        >
          纯板块指数走势与广度 (指数 / 涨跌柱状图)
        </button>
      </nav>

      <!-- Tab 1: Representative ETF K-Line, Support/Resistance, and Decision -->
      <div v-if="activeTab === 'rep_etf' && currentMapping" class="tab-body">
        <!-- Decision & Support/Resistance Summary -->
        <div class="decision-cards">
          <article class="card stat-card">
            <div class="label">研判结论 (五档)</div>
            <div class="val-row">
              <strong class="grade-val" :class="gradeFinal">{{ gradeName(gradeFinal) }}</strong>
              <small v-if="gradeBase && gradeBase !== gradeFinal" class="base-grade-note">
                (基准: {{ gradeName(gradeBase) }})
              </small>
            </div>
            <p v-if="adjustment?.applied" class="adjust-note">
              结构因子调整：{{ adjustment.base_grade }} &rarr; {{ adjustment.final_grade }} (权重 {{ adjustment.weight }})
            </p>
            <p v-else class="adjust-note muted">结构决策未触发换档 (门槛未破)</p>
          </article>

          <article class="card stat-card">
            <div class="label">水平支撑 / 压力位</div>
            <div class="sr-levels">
              <span class="sr-item resistance">
                压力位: {{ getLevelPrice(supportResistance?.nearest_resistance) != null ? num(getLevelPrice(supportResistance?.nearest_resistance)) : '—' }}
              </span>
              <span class="sr-item support">
                支撑位: {{ getLevelPrice(supportResistance?.nearest_support) != null ? num(getLevelPrice(supportResistance?.nearest_support)) : '—' }}
              </span>
            </div>
            <small class="muted">来源: 箱体与结构枢轴计算</small>
          </article>

          <article class="card stat-card">
            <div class="label">结构因子评估 (威科夫/道氏/ATR)</div>
            <div class="struct-items">
              <span>威科夫: <strong>{{ structureFactors.wyckoff }}</strong></span>
              <span>道氏结构: <strong>{{ structureFactors.dow }}</strong></span>
              <span>ATR 风险: <strong>{{ structureFactors.atrBucket }}</strong></span>
            </div>
            <small class="muted">Prefix Invariance 严格对齐</small>
          </article>
        </div>

        <!-- Period Toolbar -->
        <div class="chart-toolbar">
          <div class="period-btns">
            <button
              v-for="p in [{ id: '1d', label: '日 K' }, { id: '1w', label: '周 K' }, { id: '30m', label: '30 分钟' }, { id: '60m', label: '小时 K' }]"
              :key="p.id"
              class="button small"
              :class="{ primary: interval === p.id }"
              @click="interval = p.id"
            >
              {{ p.label }}
            </button>
          </div>
          <span class="chart-disclaimer">▲/▼ 仅作为当时可用的历史研究事件，不构成成交或实盘指令</span>
        </div>

        <!-- Chart Container -->
        <div class="chart-wrapper">
          <EtfChart
            v-if="etfChartQuery.data.value?.bars?.length"
            :data="etfChartQuery.data.value"
            :allowMinutes="true"
            @period="onPeriodChange"
          />
          <div v-else-if="etfChartQuery.loading.value" class="chart-loading">
            加载代表 ETF 图表数据中...
          </div>
          <div v-else class="chart-empty">
            <p>{{ etfChartQuery.error.value || '暂无该周期的 K 线数据' }}</p>
          </div>
        </div>
      </div>

      <!-- Tab 2: Sector Index & Breadth Histogram -->
      <div v-if="activeTab === 'index_breadth' || !currentMapping" class="tab-body">
        <!-- Breadth Histogram / Ratio Bar -->
        <div class="breadth-panel card">
          <div class="breadth-header">
            <h3>板块涨跌广度比例柱状图</h3>
            <span class="breadth-counts">
              上涨 <span class="up-text">{{ breadthStats.up }}</span> 家 ({{ breadthStats.upPct }}%) ·
              下跌 <span class="down-text">{{ breadthStats.down }}</span> 家 ({{ breadthStats.downPct }}%) ·
              平盘 {{ breadthStats.flat }} 家
            </span>
          </div>
          <!-- Proportion Stacked Bar -->
          <div class="stacked-bar-container">
            <div class="bar-segment up" :style="{ width: breadthStats.upPct + '%' }" :title="`上涨 ${breadthStats.up} 家 (${breadthStats.upPct}%)`"></div>
            <div class="bar-segment down" :style="{ width: breadthStats.downPct + '%' }" :title="`下跌 ${breadthStats.down} 家 (${breadthStats.downPct}%)`"></div>
            <div class="bar-segment flat" :style="{ width: breadthStats.flatPct + '%' }" :title="`平盘 ${breadthStats.flat} 家 (${breadthStats.flatPct}%)`"></div>
          </div>
          <div class="breadth-legend">
            <span><i class="dot up"></i> 上涨 {{ breadthStats.upPct }}%</span>
            <span><i class="dot down"></i> 下跌 {{ breadthStats.downPct }}%</span>
            <span><i class="dot flat"></i> 平盘 {{ breadthStats.flatPct }}%</span>
          </div>
        </div>

        <!-- Pure Index Chart -->
        <div class="index-chart-panel card">
          <div class="index-header">
            <h3>纯板块指数走势：{{ currentMapping?.tracking_index.name ?? sector?.sector_name }} ({{ currentMapping?.tracking_index.code ?? '无直接指数代码' }})</h3>
            <small class="muted">来源: 系统内置指数行情源与历史缓存</small>
          </div>
          <div class="chart-wrapper">
            <EtfChart
              v-if="indexChartQuery.data.value?.bars?.length"
              :data="indexChartQuery.data.value"
            />
            <div v-else-if="indexChartQuery.loading.value" class="chart-loading">
              加载指数历史走势中...
            </div>
            <div v-else class="chart-empty">
              <p>{{ indexChartQuery.error.value || '该板块暂未配置独立指数历史行情或指数源未同步。建议切换至「主力代表 ETF」查看实盘日 K 与买卖研判。' }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer Disclaimer -->
      <footer class="drawer-footer">
        <small class="watermark">
          板块研判系统 · 研究向不可操作 · actionable=false · 不连接券商 · 不自动下单
        </small>
      </footer>
    </aside>
  </div>
</template>

<style scoped>
.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.sector-drawer {
  width: min(880px, 92vw);
  height: 100%;
  background: var(--bg-card, #161b22);
  color: var(--text, #c9d1d9);
  border-left: 1px solid var(--border, #30363d);
  display: flex;
  flex-direction: column;
  box-shadow: -8px 0 24px rgba(0, 0, 0, 0.5);
  animation: slideIn 0.25s ease-out;
  overflow: hidden;
}

@keyframes slideIn {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

.drawer-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border, #30363d);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  background: rgba(0, 0, 0, 0.15);
}

.title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title-row h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-bright, #f0f6fc);
}

.sector-tag {
  background: var(--bg-tag, #21262d);
  color: var(--accent, #27c5d8);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--border, #30363d);
}

.header-metrics {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
}

.pct-badge {
  font-weight: 600;
  font-size: 14px;
}

.pct-badge.up, .up-text { color: var(--danger, #f85149); }
.pct-badge.down, .down-text { color: var(--success, #3fb950); }

.mock-badge {
  font-size: 11px;
  color: #d29922;
  border: 1px solid #d29922;
  padding: 1px 6px;
  border-radius: 3px;
}

.close-btn {
  background: none;
  border: none;
  color: var(--muted, #8b949e);
  font-size: 28px;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
  transition: color 0.15s;
}

.close-btn:hover {
  color: var(--text-bright, #f0f6fc);
}

/* Representative Mapping Bar */
.rep-bar {
  padding: 12px 20px;
  background: rgba(39, 197, 216, 0.05);
  border-bottom: 1px solid var(--border, #30363d);
}

.rep-bar.has-mapping {
  background: rgba(39, 197, 216, 0.08);
}

.rep-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
}

.fund-company-badge {
  background: #1f6feb26;
  color: #58a6ff;
  border: 1px solid #388bfd4d;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
}

.rep-basis {
  margin: 4px 0;
  font-size: 12px;
  color: var(--text, #c9d1d9);
}

.rep-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 11px;
  color: var(--muted, #8b949e);
}

.rep-empty {
  font-size: 12px;
  color: var(--muted, #8b949e);
}

/* Tabs */
.drawer-tabs {
  display: flex;
  border-bottom: 1px solid var(--border, #30363d);
  background: rgba(0, 0, 0, 0.2);
}

.tab-btn {
  flex: 1;
  padding: 10px 16px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--muted, #8b949e);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover:not(:disabled) {
  color: var(--text, #c9d1d9);
}

.tab-btn.active {
  color: var(--accent, #27c5d8);
  border-bottom-color: var(--accent, #27c5d8);
  background: rgba(39, 197, 216, 0.05);
}

.tab-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Tab Body */
.tab-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.decision-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.decision-cards .stat-card {
  padding: 12px;
  background: var(--bg-tile, #0d1117);
  border: 1px solid var(--border, #30363d);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.val-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.grade-val {
  font-size: 18px;
  color: var(--accent, #27c5d8);
}

.grade-val.可加仓, .grade-val.可入场 { color: var(--danger, #f85149); }
.grade-val.减仓 { color: var(--success, #3fb950); }

.base-grade-note {
  font-size: 12px;
  color: var(--muted, #8b949e);
}

.adjust-note {
  margin: 2px 0 0;
  font-size: 11px;
  color: #d29922;
}

.sr-levels {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  font-weight: 500;
}

.sr-item.resistance { color: #f0883e; }
.sr-item.support { color: #58a6ff; }

.struct-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
}

.chart-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.period-btns {
  display: flex;
  gap: 6px;
}

.chart-disclaimer {
  font-size: 11px;
  color: var(--muted, #8b949e);
}

.chart-wrapper {
  min-height: 380px;
  background: var(--bg-tile, #0d1117);
  border: 1px solid var(--border, #30363d);
  border-radius: 6px;
  padding: 10px;
  position: relative;
}

.chart-loading, .chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 350px;
  color: var(--muted, #8b949e);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

/* Breadth Progress Bar */
.breadth-panel {
  padding: 16px;
  background: var(--bg-tile, #0d1117);
  border: 1px solid var(--border, #30363d);
  border-radius: 6px;
}

.breadth-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.breadth-header h3 {
  margin: 0;
  font-size: 14px;
}

.breadth-counts {
  font-size: 12px;
  color: var(--text, #c9d1d9);
}

.stacked-bar-container {
  height: 20px;
  background: #21262d;
  border-radius: 10px;
  display: flex;
  overflow: hidden;
  border: 1px solid var(--border, #30363d);
}

.bar-segment {
  height: 100%;
  transition: width 0.3s ease;
}

.bar-segment.up { background: var(--danger, #f85149); }
.bar-segment.down { background: var(--success, #3fb950); }
.bar-segment.flat { background: #8b949e; }

.breadth-legend {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--muted, #8b949e);
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}

.dot.up { background: var(--danger, #f85149); }
.dot.down { background: var(--success, #3fb950); }
.dot.flat { background: #8b949e; }

.index-chart-panel {
  padding: 16px;
  background: var(--bg-tile, #0d1117);
  border: 1px solid var(--border, #30363d);
  border-radius: 6px;
}

.index-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.index-header h3 {
  margin: 0;
  font-size: 14px;
}

/* Footer */
.drawer-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--border, #30363d);
  background: rgba(0, 0, 0, 0.2);
  text-align: center;
}

.watermark {
  color: var(--muted, #8b949e);
  font-size: 11px;
}
</style>
