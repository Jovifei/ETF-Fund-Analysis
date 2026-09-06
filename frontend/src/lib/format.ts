import type { Forecast, Metric, SupportLevel } from './types'
export const horizons = [1, 3, 5, 10] as const
export const grades = ['可加仓', '可入场', '可试探', '观望', '减仓']
export function num(value: unknown, digits = 2): string { return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits }) : '—' }
export function pct(value: unknown, digits = 2): string { return typeof value === 'number' && Number.isFinite(value) ? `${value > 0 ? '+' : ''}${num(value * 100, digits)}%` : '—' }
export function direction(value: unknown) { return typeof value !== 'number' || !Number.isFinite(value) || value === 0 ? 'neutral' : value > 0 ? 'bull' : 'bear' }
export function compact(value: unknown): string { if (typeof value !== 'number' || !Number.isFinite(value)) return '—'; return value >= 1e8 ? `${num(value / 1e8)} 亿` : value >= 1e4 ? `${num(value / 1e4)} 万` : num(value) }
export function stamp(value: unknown, withDate = true): string {
  if (typeof value !== 'string' || !value) return '尚无记录'
  const date = new Date(value.length === 10 ? `${value}T00:00:00+08:00` : /Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}+08:00`)
  return Number.isNaN(date.valueOf()) ? '时间未知' : new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', ...(withDate ? { month: '2-digit', day: '2-digit' } as const : {}), hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}
export function olderThan(value: string | null | undefined, seconds: number) { if (!value) return true; const date = new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}+08:00`); return !Number.isFinite(date.valueOf()) || Date.now() - date.valueOf() > seconds * 1000 }
export function record(value: unknown): Record<string, unknown> { return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {} }
export function numeric(value: unknown): number | null { return typeof value === 'number' && Number.isFinite(value) ? value : null }
export function levelPrice(level: SupportLevel | number | null | undefined): number | null { return typeof level === 'number' ? level : numeric(level?.price ?? level?.level) }
export function frequency(forecast: Forecast | undefined) { return forecast && typeof forecast.p_up === 'number' ? `${num(forecast.p_up * 100, 0)}%` : '—' }
// A calibrated string alone is not a profile-bound model/data/horizon proof.
export function forecastLabel(_forecast?: Forecast) { return '历史相似样本上涨频率' }
export function metricLabel(value: Metric | undefined) { return value?.label ?? '数据不足' }
export const statusNames: Record<string, string> = { queued: '等待处理', running: '处理中', completed: '待审核结果', succeeded: '已完成', partial: '部分完成', failed: '失败', cancelled: '已取消', expired: '已过期', pending: '待审核', accepted: '已采纳', rejected: '未采纳', mock: '演示数据', observed: '最近观测', fresh: '快照时有效', stale: '历史数据', unverified: '未核验', missing: '缺失', degraded: '已降级', research: '研究用途', incomplete: '证据不完整', active: '已配对', revoked: '已撤销', preview: '待确认', confirmed: '已导入', undone: '已撤销导入' }
export function statusName(value: unknown) { return typeof value === 'string' ? statusNames[value] ?? value : '未知' }
