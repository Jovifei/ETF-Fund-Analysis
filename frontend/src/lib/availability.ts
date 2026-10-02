export type AvailabilityStatus = 'available' | 'unavailable' | 'blocked' | 'unknown' | 'aligned' | 'separate' | 'active' | 'disabled'

export const availabilityModuleOrder = [
  'instrument',
  'price',
  'history',
  'price_basis',
  'indicators',
  'volume',
  'forecasts',
  'decision',
  'support_resistance',
] as const

export const availabilityLabels: Record<string, string> = {
  instrument: '标的',
  price: '价格',
  history: '历史行情',
  price_basis: '价格口径',
  indicators: '指标',
  volume: '量能',
  forecasts: '预测',
  decision: '研究决策',
  support_resistance: '支撑压力',
}

export const availabilityReasonLabels: Record<string, string> = {
  price_basis_mismatch: '价格口径不一致，相关叠加已限制。',
  volume_missing_or_unverified: '成交量缺失或单位未核验。',
  support_resistance_not_generated: '支撑压力快照尚未生成。',
  forecast_feature_shortage: '预测特征不足。',
  decision_quantity_unqualified: '决策使用的量化资格未满足。',
}

export function availabilityReason(reason: unknown): string {
  if (typeof reason !== 'string') return '原因未记录'
  return availabilityReasonLabels[reason] ?? reason
}
