<script setup lang="ts">
import { horizons, num, pct, frequency, forecastLabel } from '../lib/format'
import type { Forecast } from '../lib/types'
defineProps<{ forecasts: Record<string, Forecast> }>()
</script>
<template><div class="forecast-grid"><article v-for="h in horizons" :key="h" class="forecast-card"><h3>{{h}} 个交易日 · 研究情景</h3><strong>{{pct(forecasts[h]?.expected_return)}}</strong><p>{{forecastLabel(forecasts[h])}} {{frequency(forecasts[h])}}</p><p>收益区间 {{pct(forecasts[h]?.q10)}} ～ {{pct(forecasts[h]?.q90)}}</p><p>样本 {{num(forecasts[h]?.sample_count,0)}} · {{forecasts[h]?.as_of_date ?? '无快照'}}</p><p>未取得可展示校准概率的完整资格</p></article></div></template>
