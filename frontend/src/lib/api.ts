/** One same-origin client. Never stores access credentials in browser storage. */
export class ApiError extends Error { constructor(public status: number, public code: string) { super(code); this.name = 'ApiError' } }
const requests = new Set<AbortController>()
export function abortAllRequests() { for (const controller of requests) controller.abort(); requests.clear() }
export function csrfToken(cookie = document.cookie): string {
  for (const name of ['__Host-fund-csrf', 'fund-csrf']) {
    const entry = cookie.split(';').map(v => v.trim()).find(v => v.startsWith(name + '='))
    if (entry) { try { return decodeURIComponent(entry.slice(name.length + 1)) } catch { return '' } }
  }
  return ''
}
export async function api<T>(path: string, options: { method?: string; body?: unknown; signal?: AbortSignal; timeout?: number; blob?: boolean } = {}): Promise<T> {
  if (!path.startsWith('/api/') || path.startsWith('//') || path.includes('://')) throw new ApiError(0, 'invalid_api_path')
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (options.signal?.aborted) controller.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  requests.add(controller)
  const timer = setTimeout(abort, options.timeout ?? 20000)
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }
  const form = options.body instanceof FormData
  if (options.body !== undefined && !form) headers['Content-Type'] = 'application/json'
  if (!['GET', 'HEAD'].includes(method)) headers['X-CSRF-Token'] = csrfToken()
  try {
    const response = await fetch(path, { method, headers, credentials: 'same-origin', cache: 'no-store', signal: controller.signal, body: options.body === undefined ? undefined : form ? options.body as FormData : JSON.stringify(options.body) })
    if (!response.ok) {
      let code = `http_${response.status}`
      const data: unknown = await response.json().catch(() => null)
      if (data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string' && /^[a-z0-9_]{3,100}$/.test(data.detail)) code = data.detail
      if (response.status === 401) window.dispatchEvent(new Event('session-expired'))
      throw new ApiError(response.status, code)
    }
    if (options.blob) return await response.blob() as T
    return response.status === 204 ? undefined as T : await response.json() as T
  } finally { clearTimeout(timer); requests.delete(controller); options.signal?.removeEventListener('abort', abort) }
}
export function errorText(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') return '请求已取消或超时，请重试。'
  if (error instanceof ApiError) {
    if (error.status === 401) return '登录已失效，请重新登录。'
    if (error.status === 403) return '没有权限，或会话校验失败。请刷新后重试。'
    if (error.status === 409) return `数据状态已变化，请刷新核对后重试（${error.code}）。`
    if (error.status === 429) return '任务或调用频率已达到上限，请稍后重试。'
    if (error.status === 503) return `服务尚未就绪，请检查配置和数据状态（${error.code}）。`
    if ([400, 413, 415, 422].includes(error.status)) return `输入不符合要求，请核对文件格式、字段与数据（${error.code}）。`
    if (error.status === 404) return '未找到记录；它可能尚未同步或不属于当前账户。'
    return `请求失败（${error.code}），请稍后重试。`
  }
  return '连接失败，请检查网络和服务状态。'
}
export async function download(path: string, filename: string) {
  const data = await api<Blob>(path, { blob: true })
  downloadBlob(data, filename)
}
export function downloadBlob(data: Blob, filename: string) {
  const href = URL.createObjectURL(data), link = document.createElement('a')
  link.href = href; link.download = filename; link.click()
  setTimeout(() => URL.revokeObjectURL(href), 1000)
}
