<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Search, ArrowUpRight, Star, BriefcaseBusiness, Sparkles, X } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { api, errorText } from '../lib/api'
import { pct, direction } from '../lib/format'
import type { SearchItem } from '../lib/types'
const router = useRouter(), root = ref<HTMLElement | null>(null), query = ref(''), open = ref(false), rows = ref<SearchItem[]>([]), loading = ref(false), error = ref(''), message = ref(''), active = ref(0), saving = ref('')
let controller: AbortController | null = null, timer: ReturnType<typeof setTimeout> | undefined, sequence = 0
watch(query, () => {
  clearTimeout(timer); controller?.abort(); const current = ++sequence
  error.value = ''; message.value = ''; active.value = 0; rows.value = []
  if (!query.value.trim()) { loading.value = false; return }
  loading.value = true; open.value = true
  timer = setTimeout(async () => {
    controller = new AbortController()
    try { const data = await api<{ items: SearchItem[] }>(`/api/search/instruments?q=${encodeURIComponent(query.value.trim())}&limit=8`, { signal: controller.signal }); if (current === sequence) rows.value = data.items }
    catch (e) { if (current === sequence) error.value = errorText(e) }
    finally { if (current === sequence) loading.value = false }
  }, 220)
})
function close() { open.value = false }
function go(row: SearchItem, action: string) { close(); if (action === 'chart') void router.push(`/etf/${row.ts_code}`); else if (action === 'holding') void router.push({ path: '/holdings', query: { code: row.ts_code } }); else void router.push({ path: '/ai', query: { code: row.ts_code } }) }
async function addWatch(row: SearchItem) { if (saving.value) return; saving.value = row.ts_code; try { await api('/api/watchlist/entries', { method: 'POST', body: { code: row.ts_code } }); row.watched = true; message.value = `${row.name}已加入自选，未修改持仓。` } catch (e) { error.value = errorText(e) } finally { saving.value = '' } }
function key(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
  if (event.target instanceof HTMLInputElement && event.key === 'ArrowDown') { event.preventDefault(); open.value = true; active.value = Math.min(Math.max(0, rows.value.length - 1), active.value + 1) }
  if (event.target instanceof HTMLInputElement && event.key === 'ArrowUp') { event.preventDefault(); active.value = Math.max(0, active.value - 1) }
  if (event.target instanceof HTMLInputElement && event.key === 'Enter' && open.value && rows.value[active.value]) { event.preventDefault(); go(rows.value[active.value], 'chart') }
}
function outside(event: PointerEvent) { if (root.value && !root.value.contains(event.target as Node)) close() }
onMounted(() => document.addEventListener('pointerdown', outside))
onBeforeUnmount(() => { clearTimeout(timer); controller?.abort(); ++sequence; document.removeEventListener('pointerdown', outside) })
</script>
<template><div ref="root" class="search-wrap" @keydown="key"><div class="search-field"><Search :size="17"/><input v-model="query" aria-label="搜索 ETF 或 LOF" role="combobox" aria-autocomplete="list" :aria-expanded="open && !!query" aria-controls="global-etf-search-results" autocomplete="off" placeholder="搜索 ETF / LOF 代码、名称、行业…" @focus="open = true"><kbd>ETF / LOF</kbd><button v-if="query" class="icon-button" aria-label="清空搜索" @click="query = ''; close()"><X :size="14"/></button></div><div v-if="open && query" id="global-etf-search-results" class="search-panel" role="region" aria-label="基金搜索结果"><div class="search-meta">已同步证券目录 · 选择下一步操作</div><div v-if="loading" class="search-message" role="status">正在搜索…</div><div v-if="error" class="search-message" role="alert">{{ error }}</div><div v-if="!loading && !error && !rows.length" class="search-message">没有匹配结果。请检查代码，或前往设置同步证券目录。</div><div v-for="(row, index) in rows" :key="row.ts_code" class="search-result" :class="{ active: active === index }"><div class="search-result-title"><strong>{{ row.name }}</strong><small>{{ row.ts_code }} · {{ row.kind }}</small><span :class="direction(row.quote.change_ratio)">{{ pct(row.quote.change_ratio) }}</span></div><div class="search-actions"><button class="button small" @click="go(row, 'chart')"><ArrowUpRight :size="13"/>看图</button><button class="button small" :disabled="row.watched || !!saving" @click="addWatch(row)"><Star :size="13"/>{{ row.watched ? '已自选' : '加自选' }}</button><button class="button small" @click="go(row, 'holding')"><BriefcaseBusiness :size="13"/>录入持仓</button><button class="button small" @click="go(row, 'ai')"><Sparkles :size="13"/>AI 草稿</button></div></div><div v-if="message" class="search-message" role="status">{{ message }}</div><div class="search-meta">查看与打开草稿不会调用模型或产生交易。 <button class="text-button" @click="close">收起</button></div></div></div></template>
