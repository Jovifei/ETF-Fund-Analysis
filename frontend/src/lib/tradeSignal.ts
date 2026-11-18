/**
 * Trade-signal 基线触发规则（v0，纯阈值判定）。
 *
 * 只消费服务端已提供、本项目已计算好的指标快照（CORE_FIELDS），在浏览器做
 * 阈值映射：不实现任何金融公式，不重算 MACD/KDJ/RSI/ATR。产出研究用途的
 * 买卖标记，research_only=true / not_calibrated，不构成操作级信号。
 *
 * 规则随 B-c（软约束自适应权重 + IC 更新）演进，本模块只承载第一版写死的
 * 基线启发式。
 *
 * 版本：trade-signal-baseline-v0（research_only，不属于生产策略的
 * signal-v0.7.6 体系，也不改变规范五档决策；权重/阈值改动须经 B-c 版本化）。
 */
import type { ChartBar, StructureV1 } from './types'

export type SignalKind = 'buy' | 'sell' | 'atr_warning'
export interface TradeSignal {
  /** 触发该信号的 K 线日期（YYYY-MM-DD）。 */
  date: string
  kind: SignalKind
  /** 触发依据的可读说明。 */
  reason: string
}

/** 0-100 综合买卖强度分及其分档。research_only，非操作信号。 */
export interface TradeScore {
  score: number
  tier: '可加' | '可试' | '观望' | '可减'
  /** 各因子归一化后的贡献明细。 */
  components: Record<string, number>
  label: string
}

const tierOf = (score: number): TradeScore['tier'] => (
  score >= 70 ? '可加' : score >= 55 ? '可试' : score >= 40 ? '观望' : '可减'
)

function clamp(v: number): number { return Math.max(0, Math.min(100, v)) }

/**
 * 由当前 K 线指标 + 结构因子合成 0-100 研究买卖强度（基线 v0 权重）。
 * 权重：KDJ_J 0.25 + RSI14 0.20 + MACD_hist 归一 0.20 + ATR_pct(反) 0.10
 *      + wyckoff_score 0.15 + dow_score 0.10。总权 1.0。
 * 基线 v0 固定权重，随 B-c（IC 软约束更新）演进。
 */
export function tradeScore(current: ChartBar, structure?: StructureV1 | null): TradeScore | null {
  const ind = current.indicators ?? {}
  const j = num(ind.kdj_j)
  const rsi14 = num(ind.rsi14)
  const macd = num(ind.macd_hist)
  const atrPct = num(ind.atr_pct)

  // KDJ_J 0-100 已是 0-100 量纲，直接作为子分；高位是超买(偏减)，低位超卖(偏加)。
  const kdjSub = j != null ? 100 - j : 50

  // RSI14 此处刻意按「趋势强度」而非「超买反转」解释（50 中性枢，>50 偏强）。
  // 与 KDJ 的反转口径不同是基线 v0 的已知取舍：单靠阈值无法同时表达趋势与超买，
  // 待 B-c 用历史 IC 校准权重/口径，不在此处偷偷调参。
  const rsiSub = rsi14 != null ? clamp(50 + (rsi14 - 50)) : 50

  // MACD_hist 用 ATR_pct 量纲估算强度（对不同标的量级不同，作为相对强度）。
  const macdSub = macd != null && atrPct != null && atrPct > 0
    ? clamp(50 + 50 * Math.max(-1, Math.min(1, macd / atrPct)))
    : 50

  // ATR_pct：波动越大越偏风险（减）；用小/大 0-100 反比。缺省 50。
  const atrSub = atrPct != null ? clamp(50 - Math.min(50, atrPct * 2000)) : 50

  // 结构因子：wyckoff_score/dow_score 带符号强度分（正值偏强），映射到 0-100。
  const wyckoffSub = structure?.wyckoff_score != null ? clamp(50 + structure.wyckoff_score * 10) : 50
  const dowSub = structure?.dow_score != null ? clamp(50 + structure.dow_score * 10) : 50

  const components: Record<string, number> = {
    kdj: kdjSub, rsi: rsiSub, macd: macdSub, atr_inverse: atrSub,
    wyckoff: wyckoffSub, dow: dowSub,
  }
  const weights: Record<string, number> = { kdj: 0.25, rsi: 0.2, macd: 0.2, atr_inverse: 0.1, wyckoff: 0.15, dow: 0.1 }
  const score = Math.round(Object.entries(weights).reduce((acc, [k, w]) => acc + w * (components[k] ?? 50), 0))
  const tier = tierOf(score)
  return { score, tier, components, label: `trade_score ${score} · ${tier} · 研究参考` }
}

/** 单个 K 线在相邻序列中的指标上下文（用于判断金叉/死叉等跨线状态）。 */
export interface SignalContext {
  /** 当前 K 线，indicators 必含 CORE_FIELDS 字段。 */
  current: ChartBar
  /** 上一根 K 线（允许为 undefined，序列首根不产生跨线信号）。 */
  previous?: ChartBar
  /** 当前 K 线的 ATR_pct 是否达到「高波动警示」阈值（由序列分位决定）。 */
  atrWarning: boolean
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** 逐根判定当前 K 线是否触发买卖/警示信号。纯函数、无副作用。 */
export function classifyBar(ctx: SignalContext): TradeSignal[] {
  const out: TradeSignal[] = []
  const cur = ctx.current.indicators ?? {}
  const prev = ctx.previous?.indicators ?? {}
  const atrWarning = ctx.atrWarning

  const j = num(cur.kdj_j)
  const rsi14 = num(cur.rsi14)
  const macdHist = num(cur.macd_hist)
  const prevMacdHist = num(prev.macd_hist)
  const tdSell = num(cur.td_sell_setup)
  const atrPct = num(cur.atr_pct)

  // 买点（只留超卖反转类事件信号；同根K线多条件命中时合并理由，不互相吞掉）
  const buyReasons: string[] = []
  if (j != null && macdHist != null && prevMacdHist != null && j < 20 && prevMacdHist <= 0 && macdHist > 0) {
    buyReasons.push('J<20 且 MACD 由负转正（超卖金叉）')
  }
  if (j != null && rsi14 != null && j < 20 && rsi14 < 30) {
    buyReasons.push('J<20 且 RSI14<30（超卖）')
  }
  if (buyReasons.length) out.push({ date: ctx.current.date, kind: 'buy', reason: buyReasons.join('；') })

  // 卖点（同上：合并理由）
  const sellReasons: string[] = []
  if (rsi14 != null && j != null && rsi14 > 70 && j > 80) {
    sellReasons.push('RSI14>70 且 J>80（超买见顶）')
  }
  if (macdHist != null && prevMacdHist != null && prevMacdHist >= 0 && macdHist < 0) {
    sellReasons.push('MACD 由正转负（死叉）')
  }
  if (tdSell != null && tdSell >= 9) {
    sellReasons.push('TD 卖出序列 ≥9')
  }
  if (sellReasons.length) out.push({ date: ctx.current.date, kind: 'sell', reason: sellReasons.join('；') })

  // ATR 高波动警示：仅在超过序列分位阈值时标记
  if (atrWarning) {
    out.push({ date: ctx.current.date, kind: 'atr_warning', reason: `ATR_pct=${atrPct != null ? atrPct.toFixed(3) : '—'}` })
  }

  return out
}

/** 计算序列 ATR_pct 的给定分位阈值（缺省 0.95）。返回可复用的阈值。 */
export function atrPercentileThreshold(bars: ChartBar[], q = 0.95): { threshold: number | null; byDate: Map<string, boolean> } {
  const values: number[] = []
  for (const bar of bars) {
    const v = num(bar.indicators?.atr_pct)
    if (v != null) values.push(v)
  }
  if (!values.length) return { threshold: null, byDate: new Map() }
  const sorted = [...values].sort((a, b) => a - b)
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))
  const threshold = sorted[idx]
  const byDate = new Map<string, boolean>()
  for (const bar of bars) {
    const v = num(bar.indicators?.atr_pct)
    byDate.set(bar.date, v != null && threshold != null && v >= threshold)
  }
  return { threshold, byDate }
}

/** 对整段历史 K 线序列求全部信号。序列按时间正序。首根不产生跨线信号。 */
export function signalSeries(bars: ChartBar[]): TradeSignal[] {
  const { byDate } = atrPercentileThreshold(bars, 0.95)
  const out: TradeSignal[] = []
  for (let i = 0; i < bars.length; i++) {
    out.push(...classifyBar({
      current: bars[i],
      previous: i > 0 ? bars[i - 1] : undefined,
      atrWarning: byDate.get(bars[i].date) === true,
    }))
  }
  return out
}