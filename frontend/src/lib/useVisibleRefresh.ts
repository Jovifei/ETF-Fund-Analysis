import { onActivated, onBeforeUnmount, onDeactivated, onMounted } from 'vue'

type Refresh = () => void | Promise<unknown>

export function useVisibleRefresh(refresh: Refresh, intervalMs = 60_000): void {
  let active = false
  let generation = 0
  let timer: ReturnType<typeof setTimeout> | undefined

  const visible = () => typeof document === 'undefined' || !document.hidden
  const clear = () => {
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
  }
  const schedule = (current: number) => {
    if (active && current === generation && visible()) {
      timer = setTimeout(() => void run(current), intervalMs)
    }
  }
  const run = async (current: number) => {
    if (!active || current !== generation || !visible()) return
    clear()
    try {
      await refresh()
    } catch {
      // Query owners keep request errors in their own visible state.
    } finally {
      schedule(current)
    }
  }
  const activate = (refreshNow: boolean) => {
    if (active) return
    active = true
    const current = ++generation
    if (visible()) {
      if (refreshNow) void run(current)
      else schedule(current)
    }
  }
  const deactivate = () => {
    active = false
    generation += 1
    clear()
  }
  const visibilityChanged = () => {
    if (!active) return
    const current = ++generation
    clear()
    if (visible()) void run(current)
  }

  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', visibilityChanged)
  onMounted(() => activate(false))
  onActivated(() => activate(true))
  onDeactivated(deactivate)
  onBeforeUnmount(() => {
    deactivate()
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', visibilityChanged)
  })
}
