<script setup lang="ts">
import {ref} from 'vue'
import {useQuery} from '../lib/query'
import {num,pct,direction} from '../lib/format'
import type {SearchItem} from '../lib/types'
import PageState from '../components/PageState.vue'
import Badge from '../components/Badge.vue'
const text=ref(''),search=ref(''),q=useQuery<{items:SearchItem[]}>(()=>'/api/search/instruments?limit=100&q='+encodeURIComponent(search.value))
</script>
<template><div class="page-heading"><div><p class="eyebrow">INSTRUMENT WORKSPACE</p><h1>ETF 分析</h1><p>选择一只 ETF，进入唯一的 K 线、指标、价位与研究页面。</p></div></div><div class="card"><form class="toolbar" @submit.prevent="search=text"><input v-model="text" aria-label="筛选基金目录" placeholder="代码、名称或行业…" maxlength="64"/><button class="button primary">搜索目录</button><span class="muted" style="font-size:11px">只读已同步目录，新增标的不在搜索时采集</span></form><PageState :loading="q.loading.value" :error="q.error.value" :empty="!q.data.value?.items.length" @retry="q.reload"><div class="table-scroll"><table><thead><tr><th>基金</th><th>行业</th><th class="numeric">最后报价</th><th class="numeric">涨跌</th><th>数据</th><th>操作</th></tr></thead><tbody><tr v-for="item in q.data.value?.items" :key="item.ts_code"><td class="name-cell"><RouterLink :to="'/etf/'+item.ts_code">{{item.name}}</RouterLink><small>{{item.ts_code}} · {{item.kind}}</small></td><td>{{item.theme??'—'}}</td><td class="numeric">{{num(item.quote.price,3)}}</td><td class="numeric" :class="direction(item.quote.change_ratio)">{{pct(item.quote.change_ratio)}}</td><td><Badge :value="item.quote.status"/></td><td><RouterLink class="button small" :to="'/etf/'+item.ts_code">打开分析</RouterLink></td></tr></tbody></table></div></PageState></div></template>
