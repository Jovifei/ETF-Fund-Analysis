<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { ChartAdapter } from '../lib/chartAdapter'
import { num, stamp } from '../lib/format'
import type { ChartBar, ChartData } from '../lib/types'
const props = defineProps<{ data: ChartData; cost?: number | null }>()
const host = ref<HTMLElement | null>(null), cursor = ref<ChartBar>(), failed = ref(''), range = ref(100)
let adapter: ChartAdapter | null = null
async function mount() { await nextTick(); adapter?.destroy(); adapter = null; failed.value = ''; cursor.value = props.data.bars.at(-1); if (!host.value || !props.data.available) return; try { adapter = new ChartAdapter(host.value, props.data, props.cost ?? null, bar => { cursor.value = bar }); } catch { failed.value = '图表初始化失败，请重新加载。指标数值仍可在下方查看。' } }
function setRange(value: number) { range.value = value; adapter?.range(value) }
function reset() { range.value = 100; adapter?.reset() }
onMounted(mount); watch(() => [props.data, props.cost], mount); onBeforeUnmount(() => { adapter?.destroy(); adapter = null })
</script>
<template><div><div class="chart-top"><div class="range-buttons" aria-label="图表显示范围"><button v-for="n in [60,100,250]" :key="n" :class="{active:range===n}" @click="setRange(n)">{{ n }} 根</button></div><button class="button small" @click="reset" data-testid="chart-reset">复位图表</button></div><div class="chart-legend" aria-live="off"><span>{{ cursor?.date ?? '—' }}</span><span>开 {{num(cursor?.open,3)}}</span><span>高 {{num(cursor?.high,3)}}</span><span>低 {{num(cursor?.low,3)}}</span><span>收 {{num(cursor?.close,3)}}</span><span v-if="cursor?.is_partial">盘中未收盘</span></div><div v-if="failed" class="notice error-notice">{{failed}}</div><div ref="host" class="chart" role="img" aria-label="ETF K线，支持滚轮缩放、拖拽平移和双击复位" data-testid="etf-chart" @dblclick="reset"/><div class="chart-legend" data-testid="chart-indicators"><span v-for="key in ['macd_dif','macd_dea','macd_hist','kdj_k','kdj_d','kdj_j','rsi14']" :key="key">{{key.toUpperCase()}} {{num(cursor?.indicators[key],key.startsWith('macd')?6:2)}}</span></div><div class="chart-bottom"><span>滚轮缩放 · 拖拽平移 · 双击复位</span><span>{{data.adjust==='none'?'未复权':data.adjust}} · {{data.indicator_version}}</span></div></div></template>
