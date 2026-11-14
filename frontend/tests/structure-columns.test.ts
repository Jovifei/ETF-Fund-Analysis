import { describe, expect, it } from 'vitest'
import {
  wyckoffLabel,
  dowLabel,
  atrRiskLabel,
  wyckoffDetail,
  dowDetail,
  atrDetail,
} from '../src/lib/format'

describe('Structure columns formatting and backward compatibility', () => {
  it('returns — for nullish or empty structure_v1 without crashing', () => {
    for (const val of [null, undefined, {}, { wyckoff_phase: '' }]) {
      expect(wyckoffLabel(val as any)).toBe('—')
      expect(dowLabel(val as any)).toBe('—')
      expect(atrRiskLabel(val as any)).toBe('—')
      expect(wyckoffDetail(val as any)).toContain('历史快照未包含结构因子')
      expect(dowDetail(val as any)).toContain('历史快照未包含结构因子')
      expect(atrDetail(val as any)).toContain('历史快照未包含结构因子')
    }
  })

  it('never defaults missing structure to low risk, bullish, or accumulation', () => {
    const empty = {}
    expect(atrRiskLabel(empty)).not.toBe('低波')
    expect(wyckoffLabel(empty)).not.toBe('吸筹')
    expect(dowLabel(empty)).not.toBe('上升趋势')
  })

  it('formats known Wyckoff phases correctly', () => {
    expect(wyckoffLabel({ wyckoff_phase: 'accumulation' })).toBe('吸筹')
    expect(wyckoffLabel({ wyckoff_phase: 'markup' })).toBe('拉升')
    expect(wyckoffLabel({ wyckoff_phase: 'distribution' })).toBe('派发')
    expect(wyckoffLabel({ wyckoff_phase: 'markdown' })).toBe('下跌')
    expect(wyckoffLabel({ wyckoff_phase: 'range' })).toBe('震荡')
    expect(wyckoffLabel({ wyckoff_phase: 'unknown' })).toBe('未知')

    const detail = wyckoffDetail({
      wyckoff_phase: 'accumulation',
      wyckoff_score: 0.45,
      wyckoff_confidence: 0.65,
      as_of: '2026-11-09',
    })
    expect(detail).toContain('吸筹')
    expect(detail).toContain('+0.45')
    expect(detail).toContain('65%')
    expect(detail).toContain('2026-11-09')
  })

  it('formats known Dow phases correctly', () => {
    expect(dowLabel({ dow_phase: 'uptrend' })).toBe('上升趋势')
    expect(dowLabel({ dow_phase: 'downtrend' })).toBe('下降趋势')
    expect(dowLabel({ dow_phase: 'correction_in_uptrend' })).toBe('升势回调')
    expect(dowLabel({ dow_phase: 'rally_in_downtrend' })).toBe('跌势反弹')
    expect(dowLabel({ dow_phase: 'sideways' })).toBe('横盘')
    expect(dowLabel({ dow_phase: 'unknown' })).toBe('未知')

    const detail = dowDetail({
      dow_phase: 'uptrend',
      dow_score: 0.70,
      dow_confidence: 0.65,
      as_of: '2026-11-09',
    })
    expect(detail).toContain('上升趋势')
    expect(detail).toContain('+0.70')
    expect(detail).toContain('65%')
    expect(detail).toContain('2026-11-09')
  })

  it('formats ATR risk buckets and decimal percentage scaling correctly', () => {
    expect(atrRiskLabel({ atr_risk_bucket: 'low' })).toBe('低波')
    expect(atrRiskLabel({ atr_risk_bucket: 'mid' })).toBe('中波')
    expect(atrRiskLabel({ atr_risk_bucket: 'high' })).toBe('高波')
    expect(atrRiskLabel({ atr_risk_bucket: 'extreme' })).toBe('极端')

    const detail = atrDetail({
      atr14: 0.0456,
      atr_pct: 0.0125, // 1.25% in decimal
      as_of: '2026-11-09',
      atr_risk_bucket: 'mid',
    })
    expect(detail).toContain('ATR14: 0.0456')
    expect(detail).toContain('ATR百分比: 1.25%')
    expect(detail).toContain('规则: atr_pct_fixed_v1')
    expect(detail).toContain('数据日期: 2026-11-09')
  })
})
