import { effectScope } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { useQuery } from '../src/lib/query'
import { abortAllRequests } from '../src/lib/api'

// Exercise the real API client: query-level sequencing alone cannot protect session epochs.
afterEach(() => { abortAllRequests(); vi.unstubAllGlobals() })

it.each([200, 401])('manual reload ignores a superseded %i response during JSON parsing', async status => {
  const bodies: Array<(value: unknown) => void> = []
  const fetch = vi.fn().mockImplementation(() => {
    const code = bodies.length === 0 ? status : 200
    const body = new Promise(resolve => { bodies.push(resolve) })
    return Promise.resolve({ ok: code === 200, status: code, json: () => body })
  })
  vi.stubGlobal('fetch', fetch)
  const expired = vi.fn()
  window.addEventListener('session-expired', expired)
  const scope = effectScope()
  const query = scope.run(() => useQuery<{generation:number}>('/api/workspace/overview?limit=1'))!
  try {
    const automatic = query.refresh()
    await flushPromises() // The automatic response headers arrived; JSON is still pending.
    const manual = query.reload()
    await flushPromises()
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
    bodies[1]({ generation: 2 }); await manual
    bodies[0](status === 401 ? { detail: 'session_expired' } : { generation: 1 })
    await automatic
    expect(expired).not.toHaveBeenCalled()
    expect(query.data.value?.generation).toBe(2)
    expect(query.error.value).toBe('')
  } finally {
    scope.stop(); bodies.forEach(resolve => resolve({}))
    window.removeEventListener('session-expired', expired)
  }
})

it.each([200, 401])('a reload after logout rejects the old session %i body', async status => {
  const bodies: Array<(value: unknown) => void> = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => {
    const code = bodies.length === 0 ? status : 200
    const body = new Promise(resolve => { bodies.push(resolve) })
    return Promise.resolve({ ok: code === 200, status: code, json: () => body })
  }))
  const expired = vi.fn()
  window.addEventListener('session-expired', expired)
  const scope = effectScope()
  const query = scope.run(() => useQuery<{generation:number}>('/api/workspace/overview?limit=1'))!
  try {
    const oldSession = query.refresh()
    await flushPromises()
    abortAllRequests() // A real session epoch change, not just a query sequence change.
    const newSession = query.reload()
    await flushPromises()
    expect(bodies).toHaveLength(2)
    bodies[1]({ generation: 3 }); await newSession
    bodies[0](status === 401 ? { detail: 'session_expired' } : { generation: 1 })
    await oldSession
    expect(expired).not.toHaveBeenCalled()
    expect(query.data.value?.generation).toBe(3)
  } finally {
    scope.stop(); bodies.forEach(resolve => resolve({}))
    window.removeEventListener('session-expired', expired)
  }
})

it('a current-session 401 still emits session expiry after an explicit reload', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401,
    json: async () => ({ detail: 'session_expired' }) }))
  const expired = vi.fn()
  window.addEventListener('session-expired', expired)
  const scope = effectScope()
  const query = scope.run(() => useQuery('/api/workspace/overview?limit=1'))!
  try {
    await query.reload()
    expect(expired).toHaveBeenCalledOnce()
    expect(query.error.value).toContain('登录已失效')
  } finally { scope.stop(); window.removeEventListener('session-expired', expired) }
})
