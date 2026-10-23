import { effectScope, ref, nextTick } from 'vue'
import { expect, it, vi, afterEach } from 'vitest'
import { useQuery } from '../src/lib/query'
import { api } from '../src/lib/api'
vi.mock('../src/lib/api', () => ({ api: vi.fn(), errorText: () => 'error' }))
afterEach(() => vi.resetAllMocks())
it('quiet task refresh preserves displayed content while the result is pending', async () => {
  vi.mocked(api).mockResolvedValueOnce({ status: 'queued' })
  const scope = effectScope()
  const query = scope.run(() => useQuery<{status:string}>('/api/example'))!
  await Promise.resolve(); await Promise.resolve()
  expect(query.data.value?.status).toBe('queued')
  let release!: (value: unknown) => void
  vi.mocked(api).mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
  const pending = query.refresh()
  expect(query.loading.value).toBe(false)
  expect(query.data.value?.status).toBe('queued')
  release({ status: 'completed' }); await pending
  expect(query.data.value?.status).toBe('completed')
  scope.stop()
})
it('disposal prevents a late polling response writing to a replaced user page', async () => {
  let release!: (value: unknown) => void
  vi.mocked(api).mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
  const scope = effectScope()
  const query = scope.run(() => useQuery<{status:string}>('/api/example'))!
  scope.stop(); release({ status: 'private-old-result' })
  await Promise.resolve(); await Promise.resolve()
  expect(query.data.value).toBeNull()
})

it('coalesces concurrent refreshes for the same URL instead of aborting useful work', async () => {
  let release!: (value: unknown) => void
  vi.mocked(api).mockImplementation(() => new Promise(resolve => { release = resolve }))
  const scope = effectScope()
  const query = scope.run(() => useQuery<{generation:number}>('/api/board?generation=1'))!
  const first = query.refresh(), second = query.reload()
  expect(api).toHaveBeenCalledTimes(1)
  release({ generation: 1 })
  await Promise.all([first, second])
  expect(query.data.value?.generation).toBe(1)
  scope.stop()
})
it('a changed URL replaces the request, and disabling a query clears old errors', async () => {
  vi.mocked(api).mockRejectedValueOnce(new Error('failed'))
  const url = ref<string|null>('/api/board?generation=1')
  const scope = effectScope()
  const query = scope.run(() => useQuery(url))!
  await query.reload()
  expect(query.error.value).toBe('error')
  url.value = null
  await nextTick()
  expect(query.error.value).toBe('')
  expect(query.data.value).toBeNull()
  scope.stop()
})

it('a late previous generation cannot replace the new generation', async () => {
  const releases: Array<(value: unknown) => void> = []
  vi.mocked(api).mockImplementation(() => new Promise(resolve => { releases.push(resolve) }))
  const url = ref('/api/board?generation=1')
  const scope = effectScope()
  const query = scope.run(() => useQuery<{generation:number}>(url))!
  url.value = '/api/board?generation=2'
  await nextTick()
  expect(api).toHaveBeenCalledTimes(2)
  expect(vi.mocked(api).mock.calls[0][1]?.signal?.aborted).toBe(true)
  releases[1]({ generation: 2 })
  await Promise.resolve(); await Promise.resolve()
  releases[0]({ generation: 1 })
  await Promise.resolve(); await Promise.resolve()
  expect(query.data.value?.generation).toBe(2)
  scope.stop()
})
