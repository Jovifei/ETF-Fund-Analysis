<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Star, Search } from 'lucide-vue-next'
import { useQuery } from '../lib/query'
import { useFavorites } from '../stores/favorites'
import { errorText } from '../lib/api'
import { num, pct, direction, wyckoffLabel, dowLabel, atrRiskLabel, wyckoffDetail, dowDetail, atrDetail, record } from '../lib/format'
import { decisionRows, historicalClose, explainStatus, shortStatus } from '../lib/decisionSummary'
import DecisionSummary from './DecisionSummary.vue'
import { withGeneration } from '../lib/generation'

const props = defineProps<{generation?: string|number|null; ready?: boolean}>()
const favorites = useFavorites(), favoriteError = ref('')
const router = useRouter(), frame = ref<HTMLIFrameElement | null>(null), height = ref(900)
const horizon = ref(1), filter = ref(''), revision = ref(0), ready = ref(false)
const showIframe = ref(false), selectedGrade = ref('all'), onlyFavorites = ref(false)

const outlook = useQuery<{items: Record<string, {forecasts: Record<string, unknown>}>}>('/api/workspace/research-outlook')
// Query the horizon the user actually selected. The response carries decision_horizon
// (the batch's captured horizon) — when they differ, rows arrive with grade=数据异常
// and grade_reason=selected_horizon_grade_not_published; the UI explains that openly
// instead of silently substituting another horizon.
const q = useQuery<Record<string, unknown>>(() => props.ready === false ? null : withGeneration(`/api/decision-board?horizon=${horizon.value}`, props.generation))
const horizonMismatch = computed(() => {
  const captured = (q.data.value as Record<string, unknown> | null)?.decision_horizon
  return typeof captured === 'number' && captured !== horizon.value
})
const displayed = computed(() => q.data.value ? {
  ...q.data.value,
  rows: ((q.data.value.rows ?? []) as Record<string, unknown>[]).map(row => ({
    ...row,
    forecasts: {
      ...(outlook.data.value?.items[String(row.ts_code)]?.forecasts ?? {}),
      ...((row.forecasts ?? {}) as Record<string, unknown>)
    }
  }))
} : null)

const rows = computed(() => decisionRows(displayed.value, filter.value))

const gradeCounts = computed(() => {
  const all = decisionRows(displayed.value, '')
  const counts: Record<string, number> = { all: all.length, bull: 0, neutral: 0, bear: 0, invalid: 0 }
  for (const r of all) {
    const g = String(r.grade ?? '')
    if (['可加仓', '可入场'].includes(g)) counts.bull++
    else if (g === '中性观察') counts.neutral++
    else if (g === '减仓') counts.bear++
    else if (g === '数据异常') counts.invalid++
  }
  return counts
})

const filteredRows = computed(() => {
  let list = rows.value
  if (onlyFavorites.value) {
    list = list.filter(r => !!favorites.entries[String(r.ts_code)])
  }
  if (selectedGrade.value === 'bull') {
    list = list.filter(r => ['可加仓', '可入场'].includes(String(r.grade ?? '')))
  } else if (selectedGrade.value === 'neutral') {
    list = list.filter(r => String(r.grade ?? '') === '中性观察')
  } else if (selectedGrade.value === 'bear') {
    list = list.filter(r => String(r.grade ?? '') === '减仓')
  } else if (selectedGrade.value === 'invalid') {
    list = list.filter(r => String(r.grade ?? '') === '数据异常')
  }
  return list
})

function forecast(row: Record<string, unknown>) {
  return record(record(row.forecasts)[String(horizon.value)])
}

function mobileControls(value: {filter: string; horizon: number}) {
  if (![1, 3, 7, 20, 60].includes(value.horizon)) return
  revision.value += 1; filter.value = value.filter.slice(0, 128); horizon.value = value.horizon
}

function toggleFav(code: string) {
  favoriteError.value = ''
  favorites.toggle(code).catch(e => { favoriteError.value = errorText(e) })
}

function navigateTo(code: string) {
  void router.push(withGeneration(`/etf/${code}`, q.data.value?.generation as string|number|undefined))
}

function deliver() {
  if (ready.value) {
    frame.value?.contentWindow?.postMessage({
      type: 'etf-board:state',
      board: displayed.value,
      favorites: Object.keys(favorites.entries),
      favoriteBusy: Object.keys(favorites.busy).filter(code => favorites.busy[code]),
      revision: revision.value,
      horizon: horizon.value,
      filter: filter.value,
      error: q.error.value
    }, window.location.origin)
  }
}

function receive(event: MessageEvent) {
  if (event.origin !== window.location.origin || event.source !== frame.value?.contentWindow) return
  const value = event.data
  if (value?.type === 'etf-board:ready') { ready.value = true; deliver() }
  if (value?.type === 'etf-board:height' && Number.isFinite(value.height)) height.value = Math.max(240, Math.min(100000, value.height))
  if (value?.type === 'etf-board:controls' && [1, 3, 7, 20, 60].includes(value.horizon) && Number.isSafeInteger(value.revision) && value.revision >= revision.value) {
    revision.value = value.revision; horizon.value = value.horizon; filter.value = String(value.filter ?? '').slice(0, 128)
  }
  if (value?.type === 'etf-board:favorite' && typeof value.code === 'string' && /^\d{6}\.(SH|SZ|BJ)$/.test(value.code)) {
    favoriteError.value = ''; favorites.toggle(value.code).catch(e => { favoriteError.value = errorText(e) })
  }
  if (value?.type === 'etf-board:navigate' && typeof value.code === 'string' && /^\d{6}\.(SH|SZ|BJ)$/.test(value.code)) {
    void router.push(withGeneration(`/etf/${value.code}`, q.data.value?.generation as string|number|undefined))
  }
}

watch([q.data, outlook.data, q.error, horizon, filter, revision, () => favorites.entries, () => favorites.busy], deliver)
onMounted(() => {
  window.addEventListener('message', receive)
  favorites.ensure().catch(e => { favoriteError.value = errorText(e) })
})
onBeforeUnmount(() => window.removeEventListener('message', receive))
defineExpose({
  reload: () => Promise.all([q.reload(), outlook.reload()]),
  refresh: () => Promise.all([q.refresh(), outlook.refresh()])
})
</script>
<template><section id="etf-decisions" class="card section original-board" aria-labelledby="decision-heading">
  <div class="card-header"><div><h2 id="decision-heading">ETF 决策研判矩阵</h2><p>核心 34 只标的 · 统一五档分级与多周期技术指标 · 点击整行进入标的详情</p></div>
    <div class="actions">
      <button type="button" class="text-button" @click="showIframe = !showIframe">
        {{ showIframe ? '切回原生表格' : '原版嵌入视图' }}
      </button>
      <button class="button small" :disabled="q.loading.value" @click="q.reload">重新读取快照</button>
    </div>
  </div>
  <p v-if="q.error.value" class="notice warning-notice" role="alert">{{ q.error.value }}</p>
  <p v-if="horizonMismatch" class="notice warning-notice" role="status" data-testid="horizon-mismatch-notice">
    所选期限（{{ horizon }} 日）的分级在本批次未发布：批次分级按 {{ (q.data.value as Record<string, unknown>)?.decision_horizon }} 日档采集，因此下表「决策分级」列显示为数据异常；「{{ horizon }} 日研究收益」列为该期限的真实预测值。不用其他期限顶替分级。
  </p>
  <DecisionSummary :board="displayed" :filter="filter" :horizon="horizon" @controls="mobileControls"/>
  <p v-if="favoriteError" class="notice" role="alert">{{favoriteError}}</p>

  <div v-if="!showIframe" class="native-decision-wrapper">
    <div class="board-toolbar">
      <div class="grade-filter-group" role="tablist" aria-label="分级筛选">
        <button type="button" class="grade-pill" :class="{ active: selectedGrade === 'all' }" @click="selectedGrade = 'all'">
          全部 <span class="count">{{ gradeCounts.all }}</span>
        </button>
        <button type="button" class="grade-pill bull" :class="{ active: selectedGrade === 'bull' }" @click="selectedGrade = 'bull'">
          关注加仓 <span class="count">{{ gradeCounts.bull }}</span>
        </button>
        <button type="button" class="grade-pill neutral" :class="{ active: selectedGrade === 'neutral' }" @click="selectedGrade = 'neutral'">
          中性观察 <span class="count">{{ gradeCounts.neutral }}</span>
        </button>
        <button type="button" class="grade-pill bear" :class="{ active: selectedGrade === 'bear' }" @click="selectedGrade = 'bear'">
          减仓回避 <span class="count">{{ gradeCounts.bear }}</span>
        </button>
        <button v-if="gradeCounts.invalid > 0" type="button" class="grade-pill warn" :class="{ active: selectedGrade === 'invalid' }" @click="selectedGrade = 'invalid'">
          数据异常 <span class="count">{{ gradeCounts.invalid }}</span>
        </button>
      </div>

      <div class="board-filter-controls">
        <label class="board-search">
          <Search :size="13"/>
          <input v-model="filter" placeholder="搜索代码、名称…" aria-label="搜索决策标的">
        </label>
        <label class="board-horizon">
          <span>研究期限</span>
          <select v-model.number="horizon" aria-label="研究期限">
            <option :value="1">1 日</option>
            <option :value="3">3 日</option>
            <option :value="7">7 日</option>
            <option :value="20">20 日</option>
            <option :value="60">60 日</option>
          </select>
        </label>
        <button type="button" class="fav-toggle-btn" :class="{ active: onlyFavorites }" @click="onlyFavorites = !onlyFavorites">
          <Star :size="13"/>
          <span>{{ onlyFavorites ? '已选自选' : '只看自选' }}</span>
        </button>
      </div>
    </div>

    <div class="table-scroll decision-table-wrap">
      <table class="decision-table">
        <thead>
          <tr>
            <th style="width: 38px"></th>
            <th>标的 / 代码</th>
            <th class="numeric">最新收盘</th>
            <th class="numeric">涨跌幅</th>
            <th>决策分级</th>
            <th>MACD (DIF/DEA)</th>
            <th class="numeric">KDJ-J</th>
            <th class="numeric">RSI</th>
            <th class="numeric">{{ horizon }}日研究收益</th>
            <th>威科夫结构</th>
            <th>道氏趋势</th>
            <th>ATR 波动</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in filteredRows"
            :key="String(row.ts_code)"
            class="decision-row"
            tabindex="0"
            @click="navigateTo(String(row.ts_code))"
            @keydown.enter="navigateTo(String(row.ts_code))"
          >
            <td class="fav-cell" @click.stop="toggleFav(String(row.ts_code))">
              <button type="button" class="star-btn" :aria-label="favorites.entries[String(row.ts_code)] ? '取消自选' : '设为自选'">
                <Star :size="15" :class="{ filled: favorites.entries[String(row.ts_code)] }"/>
              </button>
            </td>
            <td class="name-cell">
              <strong>{{ row.name }}</strong>
              <small class="mono">{{ row.ts_code }} · {{ record(row.sector).label ?? row.theme_l1 ?? '' }}</small>
            </td>
            <td class="numeric mono">
              {{ num(historicalClose(row).price, 3) }}<small class="muted mono"> · {{ historicalClose(row).date ?? '无日期' }}</small>
            </td>
            <td class="numeric mono" :class="direction(record(row.returns).today)">
              {{ pct(record(row.returns).today) }}
            </td>
            <td>
              <span class="grade" :data-grade="row.grade">{{ row.grade ?? '未知' }}</span>
              <small class="row-status">{{ shortStatus(row) }}</small>
              <details class="reason-detail">
                <summary>原因</summary>
                <div class="reason-detail-body">{{ explainStatus(row) }}</div>
              </details>
            </td>
            <td class="mono">
              {{ num(record(row.macd).dif, 3) }} / {{ num(record(row.macd).dea, 3) }}
            </td>
            <td class="numeric mono">{{ num(record(row.kdj).j, 1) }}</td>
            <td class="numeric mono">{{ num(record(row.rsi).value, 1) }}</td>
            <td class="numeric mono" :class="direction(forecast(row).expected_return)">
              {{ pct(forecast(row).expected_return) }}
            </td>
            <td>
              <details class="structure-detail">
                <summary class="structure-badge wyckoff" :title="wyckoffDetail(row.structure_v1 as any)">{{ wyckoffLabel(row.structure_v1 as any) }}</summary>
                <div class="structure-detail-body">{{ wyckoffDetail(row.structure_v1 as any) }}</div>
              </details>
            </td>
            <td>
              <details class="structure-detail">
                <summary class="structure-badge dow" :title="dowDetail(row.structure_v1 as any)">{{ dowLabel(row.structure_v1 as any) }}</summary>
                <div class="structure-detail-body">{{ dowDetail(row.structure_v1 as any) }}</div>
              </details>
            </td>
            <td>
              <details class="structure-detail" :class="String((row.structure_v1 as any)?.atr_risk_bucket ?? '')">
                <summary class="structure-badge atr" :class="String((row.structure_v1 as any)?.atr_risk_bucket ?? '')" :title="atrDetail(row.structure_v1 as any)">{{ atrRiskLabel(row.structure_v1 as any) }}</summary>
                <div class="structure-detail-body">{{ atrDetail(row.structure_v1 as any) }}</div>
              </details>
            </td>
          </tr>
          <tr v-if="!filteredRows.length">
            <td colspan="12" class="empty-cell">没有匹配条件的标的，请调整筛选条件。</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="table-footer">
      <span>已展示 {{ filteredRows.length }} / {{ rows.length }} 只标的 · 点击任意标的进入多周期技术分析</span>
      <span class="small-note">not_calibrated · 收益区间不代表确定性保证</span>
    </div>
  </div>

  <iframe v-else ref="frame" title="原版 ETF 决策快照" src="/internal/decision-board-frame" :style="{ height: height + 'px' }"
    style="width:100%;border:0;display:block" @load="ready=true;deliver()"/>
</section></template>
<style scoped>
.decision-table td { position: relative; }
.row-status { display: block; font-size: 10px; color: var(--muted, #8b949e); margin-top: 2px; }
.reason-detail { margin-top: 2px; font-size: 10px; }
.reason-detail > summary { color: var(--muted, #8b949e); cursor: pointer; }
.reason-detail > summary::-webkit-details-marker { display: none; }
.reason-detail > summary::before { content: '▸ '; }
.reason-detail[open] > summary::before { content: '▾ '; }
.reason-detail[open] > summary { color: var(--text, #c9d1d9); }
.reason-detail-body { position: absolute; z-index: 30; left: 4px; min-width: 220px; max-width: 320px;
  background: var(--bg, #161b22); color: var(--text, #c9d1d9); border: 1px solid var(--border, #24292f);
  border-radius: 6px; padding: 8px 10px; font-size: 11px; box-shadow: 0 4px 12px rgba(0,0,0,.4); }
.structure-detail { display: inline-block; }
.structure-detail > summary { list-style: none; cursor: help; }
.structure-detail > summary::-webkit-details-marker { display: none; }
.structure-detail[open] .structure-detail-body { position: absolute; z-index: 30; min-width: 220px; max-width: 320px;
  background: var(--bg, #161b22); color: var(--text, #c9d1d9); border: 1px solid var(--border, #24292f);
  border-radius: 6px; padding: 8px 10px; font-size: 11px; box-shadow: 0 4px 12px rgba(0,0,0,.4); }
.structure-detail:focus-within { outline: 2px solid var(--accent, #27c5d8); outline-offset: 1px; }
</style>
