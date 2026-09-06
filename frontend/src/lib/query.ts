import { onScopeDispose, ref, shallowRef, watch, toValue, type MaybeRefOrGetter } from 'vue'
import { api, errorText } from './api'
export function useQuery<T>(url: MaybeRefOrGetter<string | null>) {
  const data = shallowRef<T | null>(null), loading = ref(false), error = ref('')
  let controller: AbortController | null = null, sequence = 0
  async function reload() {
    controller?.abort()
    const current = ++sequence, path = toValue(url)
    if (!path) { data.value = null; loading.value = false; return }
    controller = new AbortController(); loading.value = true; error.value = ''
    try { const value = await api<T>(path, { signal: controller.signal }); if (current === sequence) data.value = value }
    catch (e) { if (current === sequence) error.value = errorText(e) }
    finally { if (current === sequence) loading.value = false }
  }
  watch(() => toValue(url), () => { data.value = null; void reload() }, { immediate: true })
  onScopeDispose(() => { ++sequence; controller?.abort() })
  return { data, loading, error, reload }
}
