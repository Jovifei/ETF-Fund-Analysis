<script setup lang="ts">
import {num,pct,direction} from '../lib/format'
import type {Reading} from '../lib/types'
defineProps<{readings:Reading[]}>()
</script><template><div class="reading-grid"><article v-for="item in readings" :key="item.key"><strong>{{item.label}}</strong><div class="reading-numbers"><span :class="direction(item.change)">{{num(item.value,item.key.startsWith('macd')?6:2)}}</span><small>上根 {{num(item.previous,2)}} · 变化 {{pct(item.change_ratio)}}</small></div><p>{{item.explanation}}</p></article></div></template>
<style scoped>.reading-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:14px}.reading-grid article{border:1px solid #29323d;border-radius:8px;padding:14px}.reading-numbers{display:flex;flex-direction:column;margin:8px 0}.reading-numbers span{font-size:21px;font-variant-numeric:tabular-nums}.reading-numbers small{font-size:12px;border-top:1px solid #29323d;margin-top:4px;padding-top:4px}.reading-grid p{font-size:14px;line-height:1.7;margin:8px 0 0}</style>
