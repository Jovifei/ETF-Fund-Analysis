<script setup lang="ts">
import {ref} from 'vue'
import {useQuery} from '../lib/query'
import {api,errorText} from '../lib/api'
import {num,pct,direction,stamp} from '../lib/format'
import type {SearchItem} from '../lib/types'
import PageState from '../components/PageState.vue'
import Badge from '../components/Badge.vue'
const q=useQuery<{items:(SearchItem&{id:number;note?:string})[]}>('/api/workspace/watchlist'),message=ref(''),busy=ref<number|null>(null)
async function remove(id:number){if(!window.confirm('只取消自选，不会删除持仓。继续吗？'))return;busy.value=id;try{await api('/api/watchlist/entries/'+id,{method:'DELETE'});await q.reload()}catch(e){message.value=errorText(e)}finally{busy.value=null}}
</script>
<template><div class="page-heading"><div><p class="eyebrow">MY WATCHLIST</p><h1>我的自选</h1><p>把注意力留给关注的标的。自选不是持仓，不代表已经买入。</p></div><RouterLink class="button primary" to="/analysis">＋ 发现 ETF</RouterLink></div><div v-if="message" class="notice" role="alert">{{message}}</div><div class="card"><PageState :loading="q.loading.value" :error="q.error.value" :empty="!q.data.value?.items.length" title="还没有自选 ETF" description="使用顶部搜索，选择“加入自选”；查看图表不要求先添加自选。" @retry="q.reload"><div class="table-scroll"><table><thead><tr><th>ETF</th><th>行业</th><th class="numeric">最后报价</th><th class="numeric">涨跌</th><th>数据状态</th><th>操作</th></tr></thead><tbody><tr v-for="item in q.data.value?.items" :key="item.id"><td class="name-cell"><RouterLink :to="'/etf/'+item.ts_code">{{item.name}}</RouterLink><small>{{item.ts_code}}</small></td><td>{{item.theme}}</td><td class="numeric">{{num(item.quote.price,3)}}</td><td class="numeric" :class="direction(item.quote.change_ratio)">{{pct(item.quote.change_ratio)}}</td><td><Badge :value="item.quote.status"/><small>{{stamp(item.quote.source_time)}}</small></td><td><div class="button-row"><RouterLink class="button small" :to="{path:'/holdings',query:{code:item.ts_code}}">录入持仓</RouterLink><button class="text-button" :disabled="busy===item.id" @click="remove(item.id)">取消自选</button></div></td></tr></tbody></table></div></PageState></div></template>
