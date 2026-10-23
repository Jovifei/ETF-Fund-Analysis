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
  const first = query.refresh(), second = query.refresh()
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
  await query.refresh()
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


it.each(['old-first', 'new-first'])('manual reload starts a fresh GET and rejects a late old generation (%s)', async order => {
  const releases: Array<(value: unknown) => void> = []
  vi.mocked(api).mockImplementation(() => new Promise(resolve => { releases.push(resolve) }))
  const scope = effectScope()
  const query = scope.run(() => useQuery<{generation:number}>('/api/workspace/overview?limit=1'))!
  try {
    const automatic = query.refresh()
    // The producer publishes generation 2 while the automatic generation-1 GET is in flight.
    const manual = query.reload()
    expect(api).toHaveBeenCalledTimes(2)
    expect(manual).not.toBe(automatic)
    expect(vi.mocked(api).mock.calls[0][1]?.signal?.aborted).toBe(true)
    expect(query.refresh()).toBe(manual)
    if (order === 'old-first') {
      releases[0]({ generation: 1 }); await automatic
      expect(query.data.value).toBeNull()
      expect(query.loading.value).toBe(true)
      expect(query.refresh()).toBe(manual)
    }
    releases[1]({ generation: 2 }); await manual
    if (order === 'new-first') { releases[0]({ generation: 1 }); await automatic }
    expect(query.data.value?.generation).toBe(2)
    expect(query.error.value).toBe('')
    expect(query.loading.value).toBe(false)
  } finally { scope.stop(); releases.forEach(resolve => resolve({ generation: -1 })) }
})

it('each explicit reload supersedes prior work, including a late failed manual request', async () => {
  const attempts: Array<{resolve:(value: unknown) => void; reject:(error: unknown) => void}> = []
  vi.mocked(api).mockImplementation(() => new Promise((resolve, reject) => { attempts.push({ resolve, reject }) }))
  const scope = effectScope()
  const query = scope.run(() => useQuery<{generation:number}>('/api/workspace/overview?limit=1'))!
  try {
    const first = query.refresh(), second = query.reload(), third = query.reload()
    expect(api).toHaveBeenCalledTimes(3)
    expect(vi.mocked(api).mock.calls.slice(0, 2).every(call => call[1]?.signal?.aborted)).toBe(true)
    attempts[0].resolve({ generation: 1 }); await first
    attempts[1].reject(new Error('old failure')); await second
    expect(query.error.value).toBe('')
    expect(query.loading.value).toBe(true)
    expect(query.refresh()).toBe(third)
    attempts[2].resolve({ generation: 3 }); await third
    expect(query.data.value?.generation).toBe(3)
  } finally { scope.stop(); attempts.forEach(attempt => attempt.resolve({ generation: -1 })) }
})
