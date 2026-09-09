<script setup lang="ts">
import { ref } from 'vue'
import {num,pct,frequency,forecastLabel} from '../lib/format'
import type {Forecast} from '../lib/types'
defineProps<{forecasts:Record<string,Forecast>}>()
const advanced=ref(false),names:Record<number,string>={1:'明日 · 1交易日',3:'3交易日',5:'一周 · 5交易日',10:'10交易日',20:'约一月 · 20交易日'}
</script><template><div><div class="forecast-grid"><article v-for="h in advanced?[1,3,5,10,20]:[1,5,20]" :key="h" class="forecast-card"><h3>{{names[h]}} · 研究</h3><strong>{{pct(forecasts[h]?.expected_return)}}</strong><p>{{forecastLabel(forecasts[h])}} {{frequency(forecasts[h])}}</p><p>历史收益区间 {{pct(forecasts[h]?.q10)}} ～ {{pct(forecasts[h]?.q90)}}</p><p>样本 {{num(forecasts[h]?.sample_count,0)}} · 基准 {{forecasts[h]?.as_of_date??'尚未计算'}}</p><p>{{forecasts[h]?.explanation??'已有结果保持原模型口径；没有结果时需准备足够历史并计算，不补造预测。'}}</p><small>{{forecasts[h]?.model_version??'无模型快照'}} · 未校准、非收益保证</small></article></div><label class="small-note"><input type="checkbox" v-model="advanced"/>显示兼容的3/10交易日研究</label><p class="small-note">周/月K是历史聚合；5/20日预测是从同一基准向前看5/20个交易日，不是把日预测相加。20日只是约一月，不是自然月保证。</p></div></template>
