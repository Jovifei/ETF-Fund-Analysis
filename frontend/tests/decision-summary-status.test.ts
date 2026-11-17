import { describe, expect, it } from 'vitest'
import { decisionRows, explainStatus, historicalClose, shortStatus } from '../src/lib/decisionSummary'

const baseRow = {
  ts_code: '510300.SH',
  name: '沪深300ETF',
  grade: '观望',
  grade_reason: 'J < 90 · 信号偏弱',
  data_status: 'quote_stale_at_snapshot_generation',
  quote: { is_mock: false, status: 'stale' },
  history: [
    { date: '2026-11-14', close: 0.41, is_forecast: false },
    { date: '2026-11-17', close: 0.422, is_forecast: false, not_actual: null, is_provisional: null },
  ],
}

describe('shortStatus (P5 inline machine-state label)', () => {
  it('maps the after-close snapshot state to a short readable label', () => {
    expect(shortStatus(baseRow)).toBe('收盘快照·非实时')
  })

  it('labels provisional observations without pretending they are confirmed', () => {
    expect(shortStatus({ ...baseRow, data_status: 'provisional_research_only' })).toBe('临时观察')
  })

  it('falls back to 待核验 for unknown states instead of implying verified', () => {
    expect(shortStatus({ ...baseRow, data_status: 'some_new_state' })).toBe('状态待核验')
  })

  it('marks mock data explicitly', () => {
    expect(shortStatus({ ...baseRow, data_status: 'mock', quote: { is_mock: true } })).toBe('演示数据')
  })

  it('labels verified healthy rows as 已核验 — not 待核验 (review finding)', () => {
    const healthy = { ...baseRow,
      data_status: 'confirmed_indicator_with_verified_quote',
      grade_reason: 'J < 90 · KDJ有余量 · 结构向好',
      quote: { is_mock: false, status: 'fresh' } }
    expect(shortStatus(healthy)).toBe('已核验')
    expect(explainStatus(healthy)).toContain('已核验：完整报价 + 指标')
    expect(explainStatus(healthy)).not.toContain('待核验')
  })

  it('maps quote_source_time_missing and quote_future states', () => {
    expect(shortStatus({ ...baseRow, data_status: 'quote_source_time_missing' })).toBe('源时间缺失')
    expect(shortStatus({ ...baseRow, data_status: 'quote_future_at_snapshot_generation' })).toBe('报价时间异常')
    expect(explainStatus({ ...baseRow, data_status: 'quote_future_at_snapshot_generation' }))
      .toContain('报价时间晚于快照生成')
  })
})

describe('explainStatus (P5 full detail, incl. selected_horizon_grade_not_published)', () => {
  it('explains the unpublished-horizon grade reason honestly', () => {
    const row = { ...baseRow, grade: '数据异常', grade_reason: 'selected_horizon_grade_not_published' }
    const text = explainStatus(row)
    expect(text).toContain('所选期限的分级未发布')
    expect(text).toContain('selected_horizon_grade_not_published')
  })

  it('keeps the real grade reason in the explanation for normal rows', () => {
    expect(explainStatus(baseRow)).toContain('J < 90 · 信号偏弱')
  })
})

describe('historicalClose (P1 data date)', () => {
  it('returns the latest non-forecast close together with its date', () => {
    const r = historicalClose(baseRow)
    expect(r.price).toBe(0.422)
    expect(r.date).toBe('2026-11-17')
  })

  it('skips forecast/provisional bars when finding the close', () => {
    const row = { ...baseRow, history: [
      { date: '2026-11-17', close: 0.999, is_forecast: true },
      { date: '2026-11-16', close: 0.41, is_provisional: true },
      { date: '2026-11-15', close: 0.405, is_forecast: false },
    ] }
    expect(historicalClose(row).price).toBe(0.405)
    expect(historicalClose(row).date).toBe('2026-11-15')
  })
})

describe('decisionRows filter (unchanged contract check)', () => {
  it('keeps only valid ts_codes and applies the text filter', () => {
    const board = { rows: [baseRow, { ts_code: 'bad' }, { ...baseRow, ts_code: '159915.SZ', name: '创业板ETF' }] }
    expect(decisionRows(board, '').length).toBe(2)
    expect(decisionRows(board, '创业板').map(r => r.ts_code)).toEqual(['159915.SZ'])
  })
})
