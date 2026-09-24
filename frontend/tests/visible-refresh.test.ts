import { defineComponent, h, KeepAlive, nextTick, ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useVisibleRefresh } from '../src/lib/useVisibleRefresh'

let setActive!: (value: boolean) => void
const refresh = vi.fn(async () => undefined)
const page = defineComponent({
  setup() {
    useVisibleRefresh(refresh, 1_000)
    return () => h('div', 'overview')
  },
})
const host = defineComponent({
  setup() {
    const active = ref(true)
    setActive = value => { active.value = value }
    return () => h(KeepAlive, null, { default: () => active.value ? h(page) : null })
  },
})

beforeEach(() => {
  vi.useFakeTimers()
  refresh.mockClear()
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
})

afterEach(() => vi.useRealTimers())

it('refreshes immediately when a kept page is reactivated and stops after unmount', async () => {
  const wrapper = mount(host)
  await flushPromises()
  expect(refresh).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1_000)
  expect(refresh).toHaveBeenCalledTimes(1)

  setActive(false)
  await nextTick()
  await vi.advanceTimersByTimeAsync(5_000)
  expect(refresh).toHaveBeenCalledTimes(1)

  setActive(true)
  await nextTick()
  await flushPromises()
  expect(refresh).toHaveBeenCalledTimes(2)

  wrapper.unmount()
  await vi.advanceTimersByTimeAsync(5_000)
  expect(refresh).toHaveBeenCalledTimes(2)
})
