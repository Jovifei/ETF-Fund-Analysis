import { numeric, record } from './format'

// Read-only projection of the SAME board as the original table. No scoring,
// interpolation, alternate grades, data fetches or qualification decisions.
export function decisionRows(board: unknown, filter: string): Record<string, unknown>[] {
  const items=record(board).rows, query=filter.trim().toLocaleLowerCase()
  if (!Array.isArray(items)) return []
  return items.map(record).filter(row => typeof row.ts_code==='string' && /^\d{6}\.(SH|SZ|BJ)$/.test(row.ts_code)
    && (!query || [row.ts_code,row.name,row.theme_l1,row.theme_l2,row.grade,record(row.sector).label]
      .filter(value=>typeof value==='string').join(' ').toLocaleLowerCase().includes(query)))
}
export function historicalClose(row: Record<string, unknown>): {price: number|null; date: string|null} {
  const bars=Array.isArray(row.history)?row.history.map(record):[]
  const bar=bars.filter(value=>value.is_forecast!==true && value.not_actual!==true && value.is_provisional!==true).at(-1)
  return {price:numeric(bar?.close), date:typeof bar?.date==='string'?bar.date:null}
}
const names: Record<string,string>={
  historical_price_only:'仅历史价格；完整量价资格不足',
  quote_stale_at_snapshot_generation:'报价在生成快照时已过期',
  quote_unverified_or_degraded:'报价源时间未核验或来源降级',
  indicator_missing:'指标尚未形成',
  legacy_snapshot_requires_rebuild:'旧快照需要任务重算',
  provisional_unverified_research_only:'临时盘中观察，源时间未核验',
}
export function explainStatus(row: Record<string, unknown>): string {
  const key=typeof row.data_status==='string'?row.data_status:'unknown'
  const reason=typeof row.grade_reason==='string'?row.grade_reason:'缺少解释，请在数据健康页核对'
  return `${names[key]??'数据状态待核验'} · ${key} — ${reason}`
}
