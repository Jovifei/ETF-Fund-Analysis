<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery } from '../lib/query'
import { useFavorites } from '../stores/favorites'
import { errorText } from '../lib/api'
const favorites=useFavorites(), favoriteError=ref('')
const router = useRouter(), frame = ref<HTMLIFrameElement | null>(null), height = ref(900)
const horizon = ref(1), filter = ref(''), revision = ref(0), ready = ref(false)
const q = useQuery<Record<string, unknown>>(() => `/api/decision-board?horizon=${horizon.value}`)
function deliver() {
  if (ready.value) frame.value?.contentWindow?.postMessage({ type: 'etf-board:state', board: q.data.value,
    favorites: Object.keys(favorites.entries), favoriteBusy: Object.keys(favorites.busy).filter(code=>favorites.busy[code]), revision: revision.value, horizon: horizon.value, filter: filter.value, error: q.error.value }, window.location.origin)
}
function receive(event: MessageEvent) {
  if (event.origin !== window.location.origin || event.source !== frame.value?.contentWindow) return
  const value = event.data
  if (value?.type === 'etf-board:ready') { ready.value = true; deliver() }
  if (value?.type === 'etf-board:height' && Number.isFinite(value.height)) height.value = Math.max(240, Math.min(100000, value.height))
  if (value?.type === 'etf-board:controls' && [1,3,5,10].includes(value.horizon) && Number.isSafeInteger(value.revision) && value.revision >= revision.value) {
    revision.value = value.revision; horizon.value = value.horizon; filter.value = String(value.filter ?? '').slice(0,128)
  }
  if(value?.type==='etf-board:favorite' && typeof value.code==='string' && /^\d{6}\.(SH|SZ|BJ)$/.test(value.code)){ favoriteError.value=''; favorites.toggle(value.code).catch(e=>{favoriteError.value=errorText(e)}) }
  if (value?.type === 'etf-board:navigate' && typeof value.code === 'string' && /^\d{6}\.(SH|SZ|BJ)$/.test(value.code)) void router.push(`/etf/${value.code}`)
}
watch([q.data, q.error, horizon, filter, revision, () => favorites.entries, () => favorites.busy], deliver)
onMounted(() => {window.addEventListener('message', receive);favorites.ensure().catch(e=>{favoriteError.value=errorText(e)})})
onBeforeUnmount(() => window.removeEventListener('message', receive))
defineExpose({ reload: q.reload })
</script>
<template><section id="etf-decisions" class="card section original-board" aria-labelledby="decision-heading">
  <div class="card-header"><div><h2 id="decision-heading">ETF 决策快照</h2><p>原版五档分组与指标模板 · 点击基金进入同一工作站分析</p></div>
    <button class="button small" :disabled="q.loading.value" @click="q.reload">重新读取快照</button></div>
  <p v-if="q.error.value" class="notice warning-notice" role="alert">{{ q.error.value }}</p>
  <p v-if="favoriteError" class="notice" role="alert">{{favoriteError}}</p><iframe ref="frame" title="原版 ETF 决策快照" src="/internal/decision-board-frame" :style="{ height: height + 'px' }"
    style="width:100%;border:0;display:block" @load="ready=true;deliver()"/>
</section></template>
