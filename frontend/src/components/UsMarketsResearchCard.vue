<script setup lang="ts">
import { computed } from 'vue'
import { num, pct, direction, record, numeric } from '../lib/format'

export type UsMarketsReadView = {
  availability?: string; available?: boolean; reason?: string | null; research?: Record<string, unknown> | null
  source_age_days?: number | null; source_stale?: boolean | null; is_stale?: boolean; generation?: string | number | null
}
const props = defineProps<{ view: UsMarketsReadView | null | undefined; error?: string }>()

const REASONS: Record<string, string> = {
  us_markets_research_not_published: '该批次尚未发布美股研究区块；不用其他批次或实时行情顶替。',
  local_bundle_unavailable: '尚无可读取的展示包。',
  local_display_generation_unavailable: '指定批次不可用；未自动切换批次。',
  us_markets_research_file_missing: '研究快照文件不存在。',
  us_markets_research_file_unreadable: '研究快照文件无法读取。',
  us_markets_research_file_too_large: '研究快照文件超出大小上限。',
  us_markets_research_contract_invalid: '研究快照未通过格式校验，已拒绝显示。',
}
const DOW: Record<string, string> = { uptrend: '上升', downtrend: '下降', sideways: '震荡', correction_in_uptrend: '上升中回调', rally_in_downtrend: '下降中反弹', unknown: '未知' }
const BUCKET: Record<string, string> = { low: '低', mid: '中', high: '高', extreme: '极高', unknown: '未知' }
const WYCKOFF: Record<string, string> = { accumulation: '吸筹', distribution: '派发', markup: '上涨', markdown: '下跌', range: '区间', not_computed: '未计算', unknown: '未知' }

const part = computed(() => record(props.view?.research))
const series = computed(() => (Array.isArray(part.value.series) ? part.value.series : []).map(record))
const groups = computed(() => (Array.isArray(part.value.groups) ? part.value.groups : []).map(record)
  .sort((a, b) => (numeric(a.order) ?? 0) - (numeric(b.order) ?? 0)))
const grouped = computed(() => groups.value.map(g => ({ id: String(g.group_id), label: String(g.label), rows: series.value.filter(s => s.group_id === g.group_id) }))
  .filter(g => g.rows.length))
const provisional = computed(() => (Array.isArray(part.value.provisional_closes) ? part.value.provisional_closes : []).map(record))
const failed = computed(() => (Array.isArray(part.value.failed_tickers) ? part.value.failed_tickers : []).map(String))
const source = computed(() => record(part.value.source))
const note = computed(() => {
  if (props.error) return `美股研究区块读取失败：${props.error}`
  if (!props.view) return ''
  if (props.view.reason) return REASONS[props.view.reason] ?? `暂无美股研究区块（${props.view.reason}）。`
  if (props.view.availability === 'unavailable') return '研究区块本次没有可用序列；不填零。'
  return ''
})
const sourceStale = computed(() => props.view?.source_stale === true)

const ret = (s: Record<string, unknown>, key: string) => numeric(record(s.returns)[key])
const dd = (s: Record<string, unknown>) => numeric(record(s.drawdown).current)
const rsExcess = (s: Record<string, unknown>, bench: string, key = '3m') => numeric(record(record(record(s.rs)[bench]).excess)[key])
function spark(s: Record<string, unknown>): string {
  const points = (Array.isArray(s.spark) ? s.spark : []).map(p => (Array.isArray(p) ? Number(p[1]) : NaN)).filter(Number.isFinite)
  if (points.length < 2) return ''
  const lo = Math.min(...points), hi = Math.max(...points), span = hi - lo || 1
  return points.map((v, i) => `${((i / (points.length - 1)) * 100).toFixed(1)},${(22 - ((v - lo) / span) * 20).toFixed(1)}`).join(' ')
}
const members = (s: Record<string, unknown>) => (Array.isArray(s.members) ? s.members : []).map(record)
</script>

<template>
  <section class="card section us-markets-card" data-testid="us-markets-research-card" aria-labelledby="us-markets-heading">
    <div class="card-header">
      <div>
        <h2 id="us-markets-heading">美股 CPO · 存储 · 指数（研究）</h2>
        <p>美股光模块/CPO 篮子、存储篮子与纳斯达克、标普 500 的收益、回撤、波动与相对强度。篮子是自定义等权研究口径，不是官方指数。</p>
      </div>
      <div><RouterLink class="text-button" to="/research/us-markets">打开独立美股研究页 →</RouterLink><span class="small-note" data-testid="us-markets-flags">research_only · 不可操作 · 未校准 · 不进入评分/分级/邮件</span></div>
    </div>
    <div class="card-body">
      <p v-if="note" class="notice" role="status" data-testid="us-markets-note">{{ note }}</p>
      <p v-if="sourceStale && view?.research" class="notice warning-notice" data-testid="us-markets-stale">
        研究数据截至 {{ part.as_of }}，距今 {{ view?.source_age_days ?? '未知' }} 天；不是最新美股收盘。
      </p>
      <p v-if="provisional.length" class="notice warning-notice" data-testid="us-markets-provisional">
        含暂代收盘价：{{ provisional.map(p => `${p.ticker} ${p.date}`).join('、') }}（旧快照数据，不具备确认资格；请重新生成无暂代值的研究包）。
      </p>
      <p v-if="failed.length" class="notice warning-notice" data-testid="us-markets-failed">以下代码本次未取得行情，未用其他数据代替：{{ failed.join('、') }}。</p>
      <p v-if="part.membership_warning" class="notice warning-notice" data-testid="us-membership-warning">{{ part.membership_warning }}</p>
      <p v-if="Array.isArray(part.excluded_provisional_observations) && part.excluded_provisional_observations.length" class="notice warning-notice" data-testid="us-excluded-provisional">暂代报价已排除，不参与收益/ATR；各序列截止日可能不同。</p>
      <div v-for="group in grouped" :key="group.id" class="us-group" :data-testid="`us-group-${group.id}`">
        <h3>{{ group.label }}</h3>
        <div class="table-scroll">
          <table class="us-table">
            <thead><tr><th>序列</th><th>最新</th><th>1周</th><th>1月</th><th>3月</th><th>今年</th><th>1年</th><th>回撤</th><th>ATR%</th><th>道氏代理</th><th>威科夫代理</th><th>3月超额·标普</th><th>3月超额·纳指</th><th>近一年</th></tr></thead>
            <tbody>
              <template v-for="s in group.rows" :key="String(s.series_id)">
                <tr :data-testid="`us-row-${s.series_id}`">
                  <td><strong>{{ s.label }}</strong><small class="muted"> · {{ s.as_of }}</small><small v-if="s.kind === 'basket'" class="muted"> 等权篮子</small>
                    <small v-for="(rs, role) in record(s.rs)" :key="role" class="muted" :title="`${role}: ${record(rs).first_overlap} ~ ${record(rs).last_overlap}; prices=${record(rs).n_price_pairs}; daily=${record(rs).n_daily_return_pairs}; missing=${record(rs).n_missing_sessions}`"> · {{role}} 样本 {{record(rs).n_daily_return_pairs}}</small><small v-if="s.first_gap_date" class="muted"> · {{s.first_gap_date}} 起缺口，指标未跨缺口拼接</small><small v-if="s.provisional_last_close" class="muted"> · 旧快照含暂代值，不具备确认资格</small></td>
                  <template v-if="s.available !== false">
                    <td class="numeric">{{ num(s.level) }}</td>
                    <td v-for="k in ['1w', '1m', '3m', 'ytd', '1y']" :key="k" class="numeric" :class="direction(ret(s, k))">{{ pct(ret(s, k)) }}</td>
                    <td class="numeric" :class="direction(dd(s))">{{ pct(dd(s)) }}</td>
                    <td class="numeric">{{ pct(numeric(s.atr_pct)) }} · {{ BUCKET[String(s.atr_risk_bucket)] ?? '未知' }}</td>
                    <td>{{ DOW[String(s.dow_phase)] ?? '未知' }}</td>
                    <td>{{ WYCKOFF[String(s.wyckoff_phase)] ?? '未知' }}</td>
                    <td class="numeric" :class="direction(rsExcess(s, 'vs_spx'))">{{ pct(rsExcess(s, 'vs_spx')) }}</td>
                    <td class="numeric" :class="direction(rsExcess(s, 'vs_ndx'))">{{ pct(rsExcess(s, 'vs_ndx')) }}</td>
                    <td><svg v-if="spark(s)" class="us-spark" viewBox="0 0 100 24" preserveAspectRatio="none" role="img" :aria-label="`${s.label} 近一年走势`"><polyline :points="spark(s)" fill="none" stroke="currentColor" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg></td>
                  </template>
                  <td v-else colspan="13" class="muted">暂无数据：{{ s.reason }}</td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
        <details v-for="s in group.rows.filter(r => r.kind === 'basket' && r.available !== false)" :key="`d-${s.series_id}`" class="us-details" :data-testid="`us-details-${s.series_id}`">
          <summary>{{ s.label }} · 成分与口径</summary>
          <p class="muted">{{ s.rationale }}</p>
          <p class="muted">{{s.synthetic_ohlc_warning}}</p>
          <p v-for="(rs, role) in record(s.rs)" :key="role" class="muted">{{role}}：共同窗口 {{record(rs).first_overlap}} ～ {{record(rs).last_overlap}}；价格对 {{record(rs).n_price_pairs}}，相邻日收益对 {{record(rs).n_daily_return_pairs}}，缺失交易日 {{record(rs).n_missing_sessions}}。</p>
          <p v-if="s.coverage_note" class="muted">{{ s.coverage_note }}</p>
          <div class="table-scroll"><table><thead><tr><th>代码</th><th>名称</th><th>1周</th><th>1月</th><th>3月</th><th>今年</th><th>起点</th></tr></thead><tbody>
            <tr v-for="m in members(s)" :key="String(m.ticker)"><td>{{ m.ticker }}</td><td>{{ m.name }}</td>
              <template v-if="m.available !== false"><td v-for="k in ['1w', '1m', '3m', 'ytd']" :key="k" class="numeric" :class="direction(numeric(record(m.returns)[k]))">{{ pct(numeric(record(m.returns)[k])) }}</td><td>{{ m.first_date }}</td></template>
              <td v-else colspan="5" class="muted">本次未取得行情</td></tr>
          </tbody></table></div>
        </details>
      </div>
      <p v-if="!grouped.length && !note" class="muted">尚无美股研究数据，缺失项不填零。</p>
      <p v-if="part.common_samples" class="muted">全部当前成分共同日收益窗口：{{ record(record(part.common_samples).all_current_members_adjacent_return_overlap).first }} ～ {{ record(record(part.common_samples).all_current_members_adjacent_return_overlap).last }}，{{record(record(part.common_samples).all_current_members_adjacent_return_overlap).n_sessions}} 个观察交易日（非 PIT 验证）。</p>
      <div v-if="view?.research" class="table-footer" data-testid="us-markets-source">
        <span>截至美股交易日 {{ part.as_of ?? '未知' }} · 数据源 {{ source.label ?? '未知' }}。{{ source.note }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.us-markets-card { margin-top: 16px; }
.us-group { margin-top: 12px; }
.us-group h3 { font-size: 13px; margin: 8px 0; color: var(--text, #c9d1d9); }
.us-table td, .us-table th { padding: 6px 8px; }
.us-spark { width: 90px; height: 24px; color: var(--accent, #27c5d8); }
.us-details { margin-top: 8px; }
.us-details summary { cursor: pointer; font-size: 12px; color: var(--muted, #8b949e); }
</style>
