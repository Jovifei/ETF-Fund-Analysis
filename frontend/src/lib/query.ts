import { onScopeDispose, ref, shallowRef, watch, toValue, type MaybeRefOrGetter } from 'vue'
import { api, errorText } from './api'
export function useQuery<T>(url: MaybeRefOrGetter<string | null>) {
  const data = shallowRef<T | null>(null), loading = ref(false), error = ref('')
  let controller: AbortController | null = null, sequence = 0
  let pending: { path: string; promise: Promise<void>; controller: AbortController } | null = null
  function load(quiet = false, force = false): Promise<void> {
    const path = toValue(url)
    // Automatic reads may coalesce; an explicit reread must observe a newly published batch.
    if (!force && pending && pending.path === path && !pending.controller.signal.aborted) return pending.promise
    controller?.abort()
    const current = ++sequence
    if (!path) { pending = null; data.value = null; loading.value = false; error.value = ''; return Promise.resolve() }
    const active = new AbortController()
    controller = active; loading.value = !quiet || data.value === null; error.value = ''
    const promise = (async () => {
      try { const value = await api<T>(path, { signal: active.signal }); if (current === sequence) data.value = value }
      catch (e) {
        const cancelled = e instanceof DOMException && e.name === 'AbortError'
        if (current === sequence && !cancelled) error.value = errorText(e)
      }
      finally { if (current === sequence) { loading.value = false; pending = null } }
    })()
    pending = { path, promise, controller: active }
    return promise
  }
  const reload = () => load(false, true)
  const refresh = () => load(true)
  watch(() => toValue(url), () => { data.value = null; void load() }, { immediate: true })
  onScopeDispose(() => { ++sequence; controller?.abort(); pending = null })
  return { data, loading, error, reload, refresh }
}
