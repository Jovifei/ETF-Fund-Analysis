import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, abortAllRequests, csrfToken, ApiError } from '../src/lib/api'
afterEach(() => { abortAllRequests(); vi.unstubAllGlobals(); document.cookie = 'fund-csrf=; Max-Age=0' })
describe('same-origin API boundary', () => {
  it('parses only the dedicated CSRF cookie', () => { expect(csrfToken('fund-session=hidden; fund-csrf=test-proof')).toBe('test-proof'); expect(csrfToken('unrelated=bad')).toBe('') })
  it('does not attach secrets or a body to GET', async () => { const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ items: [] }) }); vi.stubGlobal('fetch', fetch); await api('/api/search/instruments?q=ETF'); const opts = fetch.mock.calls[0][1]; expect(opts.credentials).toBe('same-origin'); expect(opts.headers.Authorization).toBeUndefined(); expect(opts.body).toBeUndefined(); expect(opts.cache).toBe('no-store') })
  it('sends CSRF for explicit writes and emits session expiry', async () => { document.cookie = 'fund-csrf=proof'; const listener = vi.fn(); window.addEventListener('session-expired', listener); const fetch = vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: 'session_expired' }) }); vi.stubGlobal('fetch', fetch); await expect(api('/api/holdings/512480.SH', { method: 'DELETE' })).rejects.toBeInstanceOf(ApiError); expect(fetch.mock.calls[0][1].headers['X-CSRF-Token']).toBe('proof'); expect(listener).toHaveBeenCalledOnce(); window.removeEventListener('session-expired', listener) })
  it('rejects other origins before network', async () => { const fetch = vi.fn(); vi.stubGlobal('fetch', fetch); await expect(api('https://example.com/api/x')).rejects.toBeInstanceOf(ApiError); expect(fetch).not.toHaveBeenCalled() })
})

it('does not deliver private JSON after logout during body parsing', async () => {
  let release!: (value: unknown) => void
  const body = new Promise(resolve => { release = resolve })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => body }))
  const request = api('/api/workspace/holdings')
  await Promise.resolve()
  abortAllRequests()
  release({ private: 'previous-user' })
  await expect(request).rejects.toMatchObject({ name: 'AbortError' })
})
it('a late 401 cannot expire a newer session', async () => {
  let release!: (value: unknown) => void
  const body = new Promise(resolve => { release = resolve })
  const listener = vi.fn()
  window.addEventListener('session-expired', listener)
  try {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401, json: () => body }))
    const request = api('/api/workspace/holdings')
    await Promise.resolve()
    abortAllRequests()
    release({ detail: 'session_expired' })
    await expect(request).rejects.toMatchObject({ name: 'AbortError' })
    expect(listener).not.toHaveBeenCalled()
  } finally { window.removeEventListener('session-expired', listener) }
})
