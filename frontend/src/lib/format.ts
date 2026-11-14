import type { Forecast, Metric, SupportLevel } from './types'
export const horizons = [1, 3, 7, 20, 60] as const
export const horizonLabels: Record<number, string> = { 1: '明日', 3: '3日', 7: '7日', 20: '一个月', 60: '3个月' }
export const grades = ['可加仓', '可入场', '可试探', '观望', '减仓']
export function num(value: unknown, digits = 2): string { return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits }) : '—' }
export function pct(value: unknown, digits = 2): string { return typeof value === 'number' && Number.isFinite(value) ? `${value > 0 ? '+' : ''}${num(value * 100, digits)}%` : '—' }
export function direction(value: unknown) { return typeof value !== 'number' || !Number.isFinite(value) || value === 0 ? 'neutral' : value > 0 ? 'bull' : 'bear' }
export function compact(value: unknown): string { if (typeof value !== 'number' || !Number.isFinite(value)) return '—'; return value >= 1e8 ? `${num(value / 1e8)} 亿` : value >= 1e4 ? `${num(value / 1e4)} 万` : num(value) }
export function stamp(value: unknown, withDate = true): string {
  if (typeof value !== 'string' || !value) return '尚无记录'
  const date = parseTimestamp(value)
  return !date ? '时间未知' : new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', ...(withDate ? { month: '2-digit', day: '2-digit' } as const : {}), hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}
export function olderThan(value: string | null | undefined, seconds: number) { const date = parseTimestamp(value); return !date || Date.now() - date.valueOf() > seconds * 1000 }
export function record(value: unknown): Record<string, unknown> { return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {} }
export function numeric(value: unknown): number | null { return typeof value === 'number' && Number.isFinite(value) ? value : null }
export function levelPrice(level: SupportLevel | number | null | undefined): number | null { return typeof level === 'number' ? level : numeric(level?.price ?? level?.level) }
export function levelDirection(level: SupportLevel): 'support' | 'resistance' | 'unknown' {
  // Nullish kind is absent; any explicit unknown kind must not borrow type's direction.
  const value = level.kind ?? level.type
  return value === 'support' || value === 'resistance' ? value : 'unknown'
}
export function levelDirectionLabel(level: SupportLevel): string {
  const value = levelDirection(level)
  return value === 'support' ? '支撑' : value === 'resistance' ? '压力' : '方向未知'
}
export function frequency(forecast: Forecast | undefined) { return forecast && typeof forecast.p_up === 'number' ? `${num(forecast.p_up * 100, 0)}%` : '—' }
// A calibrated string alone is not a profile-bound model/data/horizon proof.
export function forecastLabel(_forecast?: Forecast) { return '历史相似样本上涨频率' }
export function metricLabel(value: Metric | undefined) { return value?.label ?? '数据不足' }
export type RelativeAge = { valid: boolean; future: boolean; hours: number | null }
function parseTimestamp(value: unknown): Date | null {
  if (typeof value !== 'string' || !value.trim()) return null
  const raw = value.trim()
  const normalized = raw.length === 10 ? `${raw}T00:00:00+08:00` : /Z$|[+-]\d\d:\d\d$/.test(raw) ? raw : `${raw}+08:00`
  const date = new Date(normalized)
  return Number.isFinite(date.valueOf()) ? date : null
}
export function relativeAge(value: unknown, now = Date.now()): RelativeAge {
  const date = parseTimestamp(value)
  if (!date || !Number.isFinite(now)) return { valid: false, future: false, hours: null }
  const delta = now - date.valueOf()
  return delta < 0 ? { valid: true, future: true, hours: null } : { valid: true, future: false, hours: delta / 3600000 }
}
export const statusNames: Record<string, string> = { external_unverified: '外部来源未验证', invalid: '数据异常', queued: '等待处理', running: '处理中', completed: '待审核结果', succeeded: '已完成', partial: '部分完成', failed: '失败', cancelled: '已取消', expired: '已过期', pending: '待审核', accepted: '已采纳', rejected: '未采纳', mock: '演示数据', observed: '最近观测', fresh: '快照时有效', stale: '历史数据', unverified: '未核验', missing: '缺失', degraded: '已降级', research: '研究用途', incomplete: '证据不完整', active: '已配对', revoked: '已撤销', preview: '待确认', confirmed: '已导入', undone: '已撤销导入' }
export function statusName(value: unknown) { return typeof value === 'string' ? statusNames[value] ?? value : '未知' }

export const wyckoffLabels: Record<string, string> = { unknown: '未知', accumulation: '吸筹', markup: '拉升', distribution: '派发', markdown: '下跌', reaccumulation: '再吸筹', redistribution: '再派发', range: '震荡' }
export const dowLabels: Record<string, string> = { unknown: '未知', uptrend: '上升趋势', downtrend: '下降趋势', correction_in_uptrend: '升势回调', rally_in_downtrend: '跌势反弹', sideways: '横盘' }
export const atrRiskLabels: Record<string, string> = { unknown: '未知', low: '低波', mid: '中波', high: '高波', extreme: '极端' }

export function wyckoffLabel(structure?: { wyckoff_phase?: string } | null): string {
  if (!structure || !structure.wyckoff_phase) return '—'
  return wyckoffLabels[structure.wyckoff_phase] ?? structure.wyckoff_phase
}

export function dowLabel(structure?: { dow_phase?: string } | null): string {
  if (!structure || !structure.dow_phase) return '—'
  return dowLabels[structure.dow_phase] ?? structure.dow_phase
}

export function atrRiskLabel(structure?: { atr_risk_bucket?: string } | null): string {
  if (!structure || !structure.atr_risk_bucket) return '—'
  return atrRiskLabels[structure.atr_risk_bucket] ?? structure.atr_risk_bucket
}

export function atrDetail(structure?: { atr14?: number | null; atr_pct?: number | null; as_of?: string; atr_risk_bucket?: string } | null): string {
  if (!structure || structure.atr14 == null) return '历史快照未包含结构因子或样本不足'
  const atrVal = num(structure.atr14, 4)
  const pctVal = structure.atr_pct != null ? `${num(structure.atr_pct * 100, 2)}%` : '—'
  const dateVal = structure.as_of ?? '未知'
  return `ATR14: ${atrVal} · ATR百分比: ${pctVal} · 规则: atr_pct_fixed_v1 · 数据日期: ${dateVal}`
}

export function wyckoffDetail(structure?: { wyckoff_phase?: string; wyckoff_score?: number; wyckoff_confidence?: number; as_of?: string } | null): string {
  if (!structure || !structure.wyckoff_phase) return '历史快照未包含结构因子或样本不足'
  const label = wyckoffLabel(structure)
  const scoreVal = structure.wyckoff_score != null ? (structure.wyckoff_score >= 0 ? '+' : '') + num(structure.wyckoff_score, 2) : '—'
  const confVal = structure.wyckoff_confidence != null ? num(structure.wyckoff_confidence * 100, 0) + '%' : '—'
  const dateVal = structure.as_of ?? '未知'
  return `威科夫结构: ${label} (phase=${structure.wyckoff_phase}) · 分数: ${scoreVal} · 置信度: ${confVal} · 数据日期: ${dateVal}`
}

export function dowDetail(structure?: { dow_phase?: string; dow_score?: number; dow_confidence?: number; as_of?: string } | null): string {
  if (!structure || !structure.dow_phase) return '历史快照未包含结构因子或样本不足'
  const label = dowLabel(structure)
  const scoreVal = structure.dow_score != null ? (structure.dow_score >= 0 ? '+' : '') + num(structure.dow_score, 2) : '—'
  const confVal = structure.dow_confidence != null ? num(structure.dow_confidence * 100, 0) + '%' : '—'
  const dateVal = structure.as_of ?? '未知'
  return `道氏趋势: ${label} (phase=${structure.dow_phase}) · 分数: ${scoreVal} · 置信度: ${confVal} · 数据日期: ${dateVal}`
}
