<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Search, ArrowUpRight, Star, BriefcaseBusiness, Sparkles, X } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { api, errorText } from '../lib/api'
import { pct, direction } from '../lib/format'
import type { SearchItem } from '../lib/types'
const router = useRouter(), query = ref(''), open = ref(false), rows = ref<SearchItem[]>([]), loading = ref(false), error = ref(''), message = ref(''), active = ref(0)
let controller: AbortController | null = null, timer: ReturnType<typeof setTimeout> | undefined, sequence = 0
const listId = 'global-etf-search-results'
watch(query, () => {
  clearTimeout(timer); controller?.abort(); const current = ++sequence; error.value = ''; message.value = ''; active.value = 0
  if (!query.value.trim()) { rows.value = []; loading.value = false; return }
  loading.value = true; open.value = true
  timer = setTimeout(async () => { controller = new AbortController(); try { const data = await api<{ items: SearchItem[] }>(`/api/search/instruments?q=${encodeURIComponent(query.value.trim())}&limit=8`, { signal: controller.signal }); if (current === sequence) rows.value = data.items } catch (e) { if (current === sequence) error.value = errorText(e) } finally { if (current === sequence) loading.value = false } }, 220)
})
function close() { open.value = false }
function go(row: SearchItem, action: string) { close(); if (action === 'chart') void router.push(`/etf/${row.ts_code}`); else if (action === 'holding') void router.push({ path: '/holdings', query: { add: row.ts_code } }); else void router.push({ path: '/ai', query: { code: row.ts_code } }) }
async function watchlist(row: SearchItem) { try { await api('/api/watchlist/entries', { method: 'POST', body: { code: row.ts_code } }); row.watched = true; message.value = `${row.name}已加入自选，未修改持仓。` } catch (e) { error.value = errorText(e) } }
function key(event: KeyboardEvent) { if (event.key === 'Escape') close(); if (event.key === 'ArrowDown') { event.preventDefault(); open.value = true; active.value = Math.min(rows.value.length - 1, active.value + 1) } if (event.key === 'ArrowUp') { event.preventDefault(); active.value = Math.max(0, active.value - 1) } if (event.key === 'Enter' && open.value && rows.value[active.value]) { event.preventDefault(); go(rows.value[active.value], 'chart') } }
onBeforeUnmount(() => { clearTimeout(timer); controller?.abort(); ++sequence })
</script>
<template><div class="global-search" @keydown="key"><Search :size="18" class="search-icon"/><input v-model="query" aria-label="搜索 ETF 或 LOF" role="combobox" :aria-expanded="open" :aria-controls="listId" :aria-activedescendant="rows.length ? `search-result-${active}` : undefined" autocomplete="off" placeholder="搜索 ETF / LOF 代码、名称、行业…" @focus="open = true"><kbd>ETF</kbd><button v-if="query" class="icon-button clear-search" aria-label="清空搜索" @click="query = ''; close()"><X :size="14"/></button><div v-if="open && query" class="search-popup"><p class="search-caption">已同步证券目录 · 选择下一步操作</p><p v-if="loading" class="muted padded" role="status">正在搜索…</p><p v-if="error" class="error-text padded" role="alert">{{ error }}</p><p v-if="!loading && !error && !rows.length" class="muted padded">没有匹配结果。请检查代码，或前往设置同步证券目录。</p><div :id="listId" role="listbox"><div v-for="(row, index) in rows" :id="`search-result-${index}`" :key="row.ts_code" role="option" :aria-selected="active === index" class="search-row" :class="{ selected: active === index }"><div class="search-result-heading"><div><strong>{{ row.name }}</strong><small>{{ row.ts_code }} · {{ row.kind }} · {{ row.theme }}</small></div><span :class="direction(row.quote.change_ratio)">{{ pct(row.quote.change_ratio) }}</span></div><div class="search-actions"><button @click="go(row, 'chart')"><ArrowUpRight :size="14"/>看图</button><button :disabled="row.watched" @click="watchlist(row)"><Star :size="14"/>{{ row.watched ? '已自选' : '加自选' }}</button><button @click="go(row, 'holding')"><BriefcaseBusiness :size="14"/>录入持仓</button><button @click="go(row, 'ai')"><Sparkles :size="14"/>AI 草稿</button></div></div></div><p v-if="message" class="success-text padded" role="status">{{ message }}</p><div class="search-caption">查看与打开草稿不会调用模型或产生交易。<button class="text-button" @click="close">收起</button></div></div></div></template>
