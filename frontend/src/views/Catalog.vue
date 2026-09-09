<script setup lang="ts">
import {ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {useQuery} from '../lib/query'
import {num,pct,direction} from '../lib/format'
import type {SearchItem} from '../lib/types'
import PageState from '../components/PageState.vue'
import Badge from '../components/Badge.vue'
import FavoriteButton from '../components/FavoriteButton.vue'
const route=useRoute(),router=useRouter(),text=ref(String(route.query.q??'')),search=ref(text.value),offset=ref(0),q=useQuery<{items:SearchItem[];total:number;has_more:boolean}>(()=>'/api/search/instruments?limit=100&offset='+offset.value+'&q='+encodeURIComponent(search.value))
watch(()=>route.query.q,value=>{text.value=String(value??'');search.value=text.value;offset.value=0})
function openInstrument(code:string){ void router.push('/etf/'+code) }
function openRow(event:MouseEvent|KeyboardEvent, code:string){ const target=event.target as HTMLElement|null; if (target?.closest('a,button,input,select')) return; openInstrument(code) }
</script>
<template><div class="page-heading"><div><p class="eyebrow">INSTRUMENT WORKSPACE</p><h1>ETF 分析</h1><p>选择一只 ETF，进入唯一的 K 线、指标、价位与研究页面。</p></div></div><div class="card"><form class="toolbar" @submit.prevent="search=text;offset=0"><input v-model="text" aria-label="筛选基金目录" placeholder="代码、名称或行业…" maxlength="64"/><button class="button primary">搜索目录</button><span class="muted" style="font-size:11px">全品类 ETF / LOF 目录；未加入研究池的基金同样可搜索</span></form><PageState :loading="q.loading.value" :error="q.error.value" :empty="!q.data.value?.items.length" @retry="q.reload"><div class="table-scroll"><table><thead><tr><th>基金</th><th>行业</th><th class="numeric">最后报价</th><th class="numeric">涨跌</th><th>数据</th><th>操作</th></tr></thead><tbody><tr v-for="item in q.data.value?.items" :key="item.ts_code" class="catalog-row" tabindex="0" @click="openRow($event,item.ts_code)" @keydown.enter.self="openInstrument(item.ts_code)"><td class="name-cell"><RouterLink :to="'/etf/'+item.ts_code" @click.stop>{{item.name}}</RouterLink><small>{{item.ts_code}} · {{item.kind}}</small></td><td>{{item.theme??'—'}}</td><td class="numeric">{{num(item.quote.price,3)}}</td><td class="numeric" :class="direction(item.quote.change_ratio)">{{pct(item.quote.change_ratio)}}</td><td><Badge :value="item.quote.status"/></td><td><FavoriteButton :code="item.ts_code"/><RouterLink class="button small" :to="'/etf/'+item.ts_code" @click.stop>打开分析</RouterLink></td></tr></tbody></table></div></PageState><div class="table-footer"><span>匹配 {{q.data.value?.total??0}} 个 · 第 {{Math.floor(offset/100)+1}} 页 · 来源覆盖以实际同步为准</span><div class="actions"><button class="button small" :disabled="offset===0" @click="offset=Math.max(0,offset-100)">上一页</button><button class="button small" :disabled="!q.data.value?.has_more" @click="offset+=100">下一页</button></div></div><p class="card-body small-note">目录不等于计算池。新基金可打开详情查看数据缺口，并明确初始化；搜索本身不抓行情。<RouterLink to="/#market-boards">返回总览同步目录</RouterLink></p></div></template>
<style scoped>
.catalog-row { cursor: pointer; }
.catalog-row:focus-visible td { outline: 2px solid var(--accent, #27c5d8); outline-offset: -2px; }
</style>
