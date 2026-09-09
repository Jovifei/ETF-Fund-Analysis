import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { api } from '../lib/api'
import { useSession } from './session'
export const useFavorites = defineStore('favorites', () => {
  const session = useSession(), entries = ref<Record<string, number>>({}), loaded = ref(false)
  const busy = ref<Record<string, boolean>>({})
  let pending: Promise<void> | null = null, sequence = 0
  function clear() { sequence++; entries.value = {}; busy.value = {}; loaded.value = false; pending = null }
  watch(() => session.generation, clear, { flush: 'sync' })
  async function reload() {
    const current = ++sequence, generation = session.generation
    const result = await api<{ items: { ts_code: string; id: number }[] }>('/api/workspace/watchlist')
    if (current !== sequence || generation !== session.generation) return
    entries.value = Object.fromEntries(result.items.map(item => [item.ts_code, item.id])); loaded.value = true
  }
  async function ensure() {
    if (loaded.value) return
    if (!pending) { const task = reload(); pending = task; task.finally(() => { if (pending === task) pending = null }).catch(() => {}) }
    await pending
  }
  async function toggle(code: string) {
    if (!/^\d{6}\.(SH|SZ|BJ)$/.test(code) || busy.value[code]) return
    const generation = session.generation
    busy.value = { ...busy.value, [code]: true }
    try {
      await ensure(); if (generation !== session.generation) return
      const id = entries.value[code]
      if (id) await api('/api/watchlist/entries/' + id, { method: 'DELETE' })
      else await api('/api/watchlist/entries', { method: 'POST', body: { code } })
      if (generation !== session.generation) return
      await reload()
    } finally { if (generation === session.generation) busy.value = { ...busy.value, [code]: false } }
  }
  return { entries, loaded, busy, reload, ensure, toggle }
})
