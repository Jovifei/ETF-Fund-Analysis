<script setup lang="ts">
import { computed } from 'vue'
import { stamp } from '../lib/format'
import type { ContextReadView } from '../lib/types'
const props = defineProps<{ view: ContextReadView }>()
const label = computed(() => {
  const labels: Record<string, string> = { available: '已有观察', partial: '部分数据',
    carried_forward: '沿用既有数据', unpublished: '本批次未发布', unavailable: '当前不可用' }
  if (props.view.reason === 'optional_refresh_failed') return '本次更新失败'
  return labels[props.view.availability ?? ''] ?? '状态未知'
})
const reason = computed(() => {
  const reasons: Record<string, string> = { optional_refresh_failed: '可选上下文更新失败，缺失项保持为空。',
    not_refreshed_today: '本交易日尚未更新。', fast_slot_reuses_same_day_refresh: '本时段沿用同日已存观察，未重新采集。',
    market_context_not_published: '展示包未包含市场上下文。', local_display_generation_unavailable: '所选批次不可用，请主动读取最新批次。',
    local_bundle_unavailable: '尚无可读取的展示包。', market_context_empty: '本批次没有上下文观察。',
    coverage_incomplete: '仅展示已取得的上下文，缺失项保持为空。' }
  return reasons[props.view.reason ?? ''] ?? props.view.reason
})
</script>
<template>
  <div class="notice context-read-status" role="status">
    <strong>{{label}}</strong><span v-if="view.is_expired"> · 展示包已过期</span><span v-if="view.historical_identity"> · 历史版本</span>
    <span v-if="reason"> · {{reason}}</span>
    <small>批次 {{view.generation ?? view.requested_generation ?? '未知'}} · 来源日期 {{view.source_as_of ?? '未知'}} · 生成 {{stamp(view.generated_at)}} · 上下文更新 {{stamp(view.refreshed_at)}} · 读取 {{stamp(view.read_at)}}</small>
  </div>
</template>
<style scoped>
.context-read-status { display: block; }
.context-read-status small { display: block; margin-top: 4px; overflow-wrap: anywhere; }
</style>
