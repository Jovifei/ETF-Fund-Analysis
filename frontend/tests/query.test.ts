import { effectScope } from 'vue'
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
