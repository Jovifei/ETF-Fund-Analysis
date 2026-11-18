import { describe, expect, it } from 'vitest'
import { classifyBar, signalSeries, atrPercentileThreshold, tradeScore } from '../src/lib/tradeSignal'
import type { ChartBar, StructureV1 } from '../src/lib/types'

function bar(date: string, indicators: Record<string, number | null>): ChartBar {
  return { date, open: 1, high: 1, low: 1, close: 1, volume: null, amount: null, indicators }
}

function structure(over: Partial<StructureV1> = {}): StructureV1 {
  return { schema_version: 'structure-v1', ts_code: 'X', as_of: '2026-11-16', ...over }
}

describe('tradeSignal classifyBar', () => {
  it('超卖金叉：J<20 且 MACD 由负转正 → 买点', () => {
    const prev = bar('2026-11-13', { kdj_j: 15, macd_hist: -0.01, rsi14: 28, rsi6: 25, ma5: 1, ma10: 1, td_sell_setup: 0, atr_pct: 0.02 })
    const cur = bar('2026-11-16', { kdj_j: 12, macd_hist: 0.005, rsi14: 29, rsi6: 27, ma5: 1, ma10: 1, td_sell_setup: 0, atr_pct: 0.02 })
    const signals = classifyBar({ current: cur, previous: prev, atrWarning: false })
    expect(signals.some(s => s.kind === 'buy')).toBe(true)
  })

  it('超卖：J<20 且 RSI14<30 → 买点', () => {
    const cur = bar('2026-11-16', { kdj_j: 15, macd_hist: -0.01, rsi14: 25, rsi6: 30, ma5: 1, ma10: 1, td_sell_setup: 0, atr_pct: 0.02 })
    const signals = classifyBar({ current: cur, atrWarning: false })
    expect(signals.some(s => s.kind === 'buy')).toBe(true)
  })

  it('超买见顶：RSI14>70 且 J>80 → 卖点', () => {
    const cur = bar('2026-11-16', { kdj_j: 90, macd_hist: 0.01, rsi14: 78, rsi6: 80, ma5: 1, ma10: 1, td_sell_setup: 0, atr_pct: 0.02 })
    const signals = classifyBar({ current: cur, atrWarning: false })
    expect(signals.some(s => s.kind === 'sell')).toBe(true)
  })

  it('死叉：MACD 由正转负 → 卖点', () => {
    const prev = bar('2026-11-13', { kdj_j: 50, macd_hist: 0.01, rsi14: 50, rsi6: 50, ma5: 1, ma10: 1, td_sell_setup: 0, atr_pct: 0.02 })
    const cur = bar('2026-11-16', { kdj_j: 50, macd_hist: -0.004, rsi14: 50, rsi6: 50, ma5: 1, ma10: 1, td_sell_setup: 0, atr_pct: 0.02 })
    const signals = classifyBar({ current: cur, previous: prev, atrWarning: false })
    expect(signals.some(s => s.kind === 'sell')).toBe(true)
  })

  it('TD 卖出序列 ≥9 → 卖点', () => {
    const cur = bar('2026-11-16', { kdj_j: 60, macd_hist: 0.01, rsi14: 55, rsi6: 55, ma5: 1, ma10: 1, td_sell_setup: 9, atr_pct: 0.02 })
    const signals = classifyBar({ current: cur, atrWarning: false })
    expect(signals.some(s => s.kind === 'sell' && s.reason.includes('TD'))).toBe(true)
  })

  it('中性行情不产生买卖信号（无 atr_warning 时不标警示）', () => {
    const cur = bar('2026-11-16', { kdj_j: 50, macd_hist: 0.01, rsi14: 50, rsi6: 50, ma5: 1, ma10: 1, td_sell_setup: 3, atr_pct: 0.02 })
    const prev = bar('2026-11-13', { kdj_j: 50, macd_hist: 0.02, rsi14: 50, rsi6: 50, ma5: 1, ma10: 1, td_sell_setup: 3, atr_pct: 0.02 })
    const signals = classifyBar({ current: cur, previous: prev, atrWarning: false })
    expect(signals.some(s => s.kind === 'buy' || s.kind === 'sell')).toBe(false)
  })

  it('atrWarning=true 时标记 ATR 警示', () => {
    const cur = bar('2026-11-16', { kdj_j: 50, macd_hist: 0.01, rsi14: 50, rsi6: 50, ma5: 1, ma10: 1, td_sell_setup: 3, atr_pct: 0.05 })
    const signals = classifyBar({ current: cur, atrWarning: true })
    expect(signals.some(s => s.kind === 'atr_warning')).toBe(true)
  })

  it('同一根K线同时满足超买见顶与 TD9：合并为一条卖点，两个理由都保留', () => {
    const cur = bar('2026-11-16', { kdj_j: 90, macd_hist: 0.01, rsi14: 78, rsi6: 80, ma5: 1, ma10: 1, td_sell_setup: 9, atr_pct: 0.02 })
    const signals = classifyBar({ current: cur, atrWarning: false })
    const sells = signals.filter(s => s.kind === 'sell')
    expect(sells.length).toBe(1)
    expect(sells[0].reason).toContain('超买见顶')
    expect(sells[0].reason).toContain('TD')
  })
})

describe('tradeSignal signalSeries + atrPercentileThreshold', () => {
  it('首根无 previous 不产生跨线信号，中性纯 ATR 序列只在高分位触发警示', () => {
    const bars: ChartBar[] = []
    for (let i = 0; i < 10; i++) {
      bars.push(bar(`2026-11-${String(i + 1).padStart(2, '0')}`, { kdj_j: 50, macd_hist: i === 0 ? 0 : 0.01, rsi14: 50, rsi6: 50, ma5: 1, ma10: 1, td_sell_setup: 0, atr_pct: 0.01 + i * 0.001 }))
    }
    const signals = signalSeries(bars)
    // p95 下 10 根序列约有 0.5 根触发 ATR 警示，最多 1 根
    const atrSignals = signals.filter(s => s.kind === 'atr_warning')
    expect(atrSignals.length).toBeLessThanOrEqual(1)
  })

  it('atrPercentileThreshold 高分为时取到靠后值的日期', () => {
    const bars: ChartBar[] = [
      bar('d1', { atr_pct: 0.1, kdj_j: 50, macd_hist: 0, rsi14: 50, rsi6: 50, ma5: 1, ma10: 1, td_sell_setup: 0 }),
      bar('d2', { atr_pct: 0.9, kdj_j: 50, macd_hist: 0, rsi14: 50, rsi6: 50, ma5: 1, ma10: 1, td_sell_setup: 0 }),
      bar('d3', { atr_pct: 0.5, kdj_j: 50, macd_hist: 0, rsi14: 50, rsi6: 50, ma5: 1, ma10: 1, td_sell_setup: 0 }),
    ]
    const { threshold, byDate } = atrPercentileThreshold(bars, 0.9)
    expect(threshold).not.toBeNull()
    expect(byDate.get('d2')).toBe(true)
    expect(byDate.get('d1')).toBe(false)
  })
})

describe('tradeSignal tradeScore', () => {
  it('强势指标 + 强势结构 → 高 score（可加/可试）', () => {
    const cur = bar('2026-11-16', { kdj_j: 20, macd_hist: 0.02, rsi14: 65, atr_pct: 0.01, td_sell_setup: 0 })
    const ts = tradeScore(cur, structure({ wyckoff_score: 4, dow_score: 3, atr_risk_bucket: 'low' }))
    expect(ts).not.toBeNull()
    expect(ts!.score).toBeGreaterThan(60)
    expect(['可加', '可试']).toContain(ts!.tier)
  })

  it('弱势指标 + 弱势结构 → 低 score（观望/可减）', () => {
    const cur = bar('2026-11-16', { kdj_j: 90, macd_hist: -0.02, rsi14: 30, atr_pct: 0.02, td_sell_setup: 0 })
    const ts = tradeScore(cur, structure({ wyckoff_score: -4, dow_score: -3, atr_risk_bucket: 'extreme' }))
    expect(ts).not.toBeNull()
    expect(ts!.score).toBeLessThan(40)
    expect(['观望', '可减']).toContain(ts!.tier)
  })

  it('缺结构因子时退化为技术因子合成（不抛错）', () => {
    const cur = bar('2026-11-16', { kdj_j: 50, macd_hist: 0, rsi14: 50, atr_pct: 0.015 })
    const ts = tradeScore(cur, null)
    expect(ts).not.toBeNull()
    expect(ts!.score).toBeGreaterThanOrEqual(0)
    expect(ts!.score).toBeLessThanOrEqual(100)
  })
})