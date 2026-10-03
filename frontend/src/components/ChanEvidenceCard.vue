<script setup lang="ts">
import { computed, ref } from 'vue'
import { record } from '../lib/format'
import type { ChanObservation } from '../lib/types'

const props = defineProps<{ observation?: ChanObservation | null }>()
const showAll = ref(false)
const available = computed(() => props.observation?.available === true && props.observation.drawable === true && props.observation.source === 'persisted_r4c_observed_revision')
const metadata = computed(() => record(props.observation?.revision_evidence))
const provided = computed(() => Array.isArray(metadata.value.transitions))
const text = (value: unknown) => typeof value === 'string' && value.trim() ? value : null
const display = (value: unknown) => text(value) ?? '未知'
const sequence = computed(() => Number.isSafeInteger(metadata.value.sequence_number) && Number(metadata.value.sequence_number) > 0 ? String(metadata.value.sequence_number) : '未知')
const cutoff = computed(() => {
  const value = text(metadata.value.cutoff_at)
  if (!value || !/^\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:\.\d{1,6})?$/.test(value)) return '未知'
  const normalized = value.replace(' ', 'T'), date = new Date(`${normalized}Z`)
  return Number.isFinite(date.valueOf()) && date.toISOString().slice(0, 19) === normalized.slice(0, 19) ? `${value} UTC` : '未知'
})
const transitions = computed(() => (Array.isArray(metadata.value.transitions) ? metadata.value.transitions : []).map(value => {
  const row = record(value), key = text(row.structure_key), current = text(row.revision_id), prior = text(row.prior_revision_id)
  let label = '变化状态未知'
  const flagsKnown = typeof row.reappearance === 'boolean' && (!row.reappearance || row.status === 'OBSERVED_NEW')
  if (key && flagsKnown) {
    if (row.status === 'OBSERVED_NEW' && current && row.prior_revision_id === null) label = row.reappearance === true ? '再次观察到' : '本次新增观察'
    else if (row.status === 'OBSERVED_CHANGED' && current && prior) label = '本次观察有变化'
    else if (row.status === 'OBSERVED_UNCHANGED' && current && prior) label = '与上次观察一致'
    else if (row.status === 'OBSERVED_ABSENT' && row.revision_id === null && prior) label = '本次未观察到'
  }
  return { label, key: key ?? '未知', current: current ?? (label === '本次未观察到' ? '本次无修订' : '未知'), prior: prior ?? '未知' }
}))
const visible = computed(() => showAll.value ? transitions.value : transitions.value.slice(0, 5))
</script>

<template>
  <details v-if="available" class="chan-evidence" data-testid="chan-evidence-card">
    <summary>查看已保存缠论证据<span v-if="provided"> · {{transitions.length}} 条变化记录</span></summary>
    <div class="evidence-content">
      <p class="evidence-limit">仅说明当前保存的观测与前次记录的差异。引擎确认未知；来源截止不是确认时间，也不代表历史当时可见。“本次未观察到”不表示结构失效。</p>
      <dl class="evidence-metadata">
        <dt>观测 ID</dt><dd>{{display(observation?.observation_id)}}</dd>
        <dt>观测序号</dt><dd>{{sequence}}</dd>
        <dt>引擎 / 版本</dt><dd>{{display(observation?.engine_id)}} / {{display(observation?.engine_version)}}</dd>
        <dt>方言</dt><dd>{{display(observation?.dialect_id)}}</dd>
        <dt>价格口径</dt><dd>{{display(observation?.price_basis_id)}}</dd>
        <dt>来源截止</dt><dd>{{cutoff}}</dd>
        <dt>输入修订 ID</dt><dd>{{display(metadata.input_revision_id)}}</dd>
        <dt>输入哈希</dt><dd>{{display(metadata.input_hash)}}</dd>
      </dl>
      <p v-if="!provided">当前响应未提供修订变化记录。</p>
      <p v-else-if="!transitions.length">本次观测没有修订变化条目。</p>
      <ol v-else class="transition-list">
        <li v-for="(item, index) in visible" :key="index" data-testid="chan-transition">
          <strong>{{item.label}}</strong>
          <dl><dt>结构 ID</dt><dd>{{item.key}}</dd><dt>当前修订</dt><dd>{{item.current}}</dd><dt>前次修订</dt><dd>{{item.prior}}</dd></dl>
        </li>
      </ol>
      <button v-if="transitions.length > 5" type="button" class="button small evidence-more" :aria-expanded="showAll" data-testid="chan-evidence-more" @click="showAll = !showAll">{{showAll ? '收起更多记录' : `展开其余 ${transitions.length - 5} 条记录`}}</button>
    </div>
  </details>
</template>

<style scoped>
.chan-evidence{margin:8px;border:1px solid var(--border);border-radius:8px;overflow-wrap:anywhere;font-size:13px;line-height:1.7}
summary{min-height:44px;padding:10px 12px;cursor:pointer;box-sizing:border-box}
summary:focus-visible,.evidence-more:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
summary span{color:var(--muted)}
.evidence-content{padding:0 12px 12px}.evidence-limit{color:var(--muted);margin:0 0 12px}
dl{display:grid;grid-template-columns:minmax(84px,120px) minmax(0,1fr);gap:4px 12px;margin:8px 0}dt{color:var(--muted)}dd{margin:0;min-width:0}
.transition-list{padding-left:22px;margin:16px 0}.transition-list li{margin:12px 0;padding-bottom:8px;border-bottom:1px solid var(--border)}
.evidence-more{min-height:44px;white-space:normal}
@media(max-width:430px){dl{grid-template-columns:1fr;gap:2px}.evidence-content{padding:0 10px 10px}dd{margin-bottom:8px}.transition-list{padding-left:18px}}
</style>
