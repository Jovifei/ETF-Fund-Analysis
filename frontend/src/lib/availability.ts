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
  feature_or_sample_shortage: '预测特征或样本不足。',
  history_too_short: '预测历史样本不足。',
  forecast_values_unavailable: '预测快照没有可读数值。',
  feature_shortage: '预测特征不足。',
  price_only_research: '仅价格研究，量额资格尚未满足。',
  support_resistance_overlay_blocked: '已有结构证据，当前叠加受限。',
  price_basis_mismatch: '价格口径不一致，相关叠加已限制。',
  volume_missing_or_unverified: '成交量缺失或单位未核验。',
  support_resistance_not_generated: '支撑压力快照尚未生成。',
  forecast_feature_shortage: '预测特征不足。',
  decision_quantity_unqualified: '决策使用的量化资格未满足。',
}

export function availabilityReason(reason: unknown): string {
  if (typeof reason !== 'string') return '原因未记录'
  return availabilityReasonLabels[reason] ?? '当前研究受限，具体原因尚未识别。'
}

export function availabilityStatus(status: unknown): string {
  const labels: Record<string, string> = { available: '可读', unavailable: '暂无数据', blocked: '已阻断', unknown: '状态未知', aligned: '口径一致', separate: '口径分离', active: '已启用', disabled: '未启用', degraded: '受限研究' }
  return typeof status === 'string' ? labels[status] ?? '状态未知' : '未提供状态'
}
