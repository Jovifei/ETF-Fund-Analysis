<script setup lang="ts">
import { computed } from 'vue'
import { num, pct, record, stamp, grades } from '../lib/format'
import { decisionRows, historicalClose, explainStatus } from '../lib/decisionSummary'
const props=defineProps<{board:Record<string,unknown>|null;filter:string;horizon:number}>()
const emit=defineEmits<{controls:[value:{filter:string;horizon:number}]}>()
const rows=computed(()=>decisionRows(props.board,props.filter))
const groupNames=computed(()=>[...new Set([...grades,'数据异常',...rows.value.map(row=>String(row.grade??'未知分级'))])])
const groups=computed(()=>groupNames.value.map(grade=>({grade,rows:rows.value.filter(r=>String(r.grade??'未知分级')===grade)})).filter(g=>g.rows.length))
function forecast(row:Record<string,unknown>){return record(record(row.forecasts)[String(props.horizon)])}
function filterInput(event:Event){emit('controls',{filter:(event.target as HTMLInputElement).value.slice(0,128),horizon:props.horizon})}
function horizonInput(event:Event){emit('controls',{filter:props.filter,horizon:Number((event.target as HTMLSelectElement).value)})}
</script>
<template>
  <section class="mobile-decision-board" data-testid="mobile-decision-board" aria-label="ETF 决策快照窄屏摘要">
    <p class="small-note">与完整指标表使用同一快照；点标的查看完整指标。研究状态不是交易授权。</p>
    <div class="mobile-decision-controls">
      <label>筛选决策标的<input :value="filter" maxlength="128" aria-label="筛选决策标的" placeholder="代码、名称或分级" @input="filterInput"/></label>
      <label>研究期限<select :value="horizon" aria-label="研究期限" @change="horizonInput"><option v-for="h in [1,3,5,10,20]" :key="h" :value="h">{{h}} 个交易日</option></select></label>
    </div>
    <p class="small-note">快照 {{stamp(board?.generated_at)}} · {{rows.length}} 个标的 · {{board?.freshness??'missing'}}</p>
    <p v-if="!board" role="status">等待决策快照。</p><p v-else-if="!rows.length" role="status">没有匹配标的。</p>
    <section v-for="group in groups" :key="group.grade" class="mobile-decision-group">
      <h3>{{group.grade}} <small>{{group.rows.length}} 个</small></h3>
      <article v-for="row in group.rows" :key="String(row.ts_code)" class="mobile-decision-row" data-testid="mobile-decision-row">
        <RouterLink :to="`/etf/${row.ts_code}`" class="mobile-instrument"><strong>{{row.name}}</strong><span class="mono">{{row.ts_code}}</span><span>查看完整指标 →</span></RouterLink>
        <div class="mobile-price-pair"><div><small>历史收盘 · {{historicalClose(row).date??'日期未知'}}</small><strong>{{num(historicalClose(row).price,3)}}</strong></div><div><small>涨跌幅 · {{record(row.returns).as_of_date??'日期待核验'}}</small><strong>{{pct(record(row.returns).today)}}</strong></div></div>
        <p class="small-note">支撑带 {{num(record(record(row.entry_exit_ref).support_zone).low,3)}}–{{num(record(record(row.entry_exit_ref).support_zone).high,3)}} · 压力带 {{num(record(record(row.entry_exit_ref).resistance_zone).low,3)}}–{{num(record(record(row.entry_exit_ref).resistance_zone).high,3)}} · {{record(row.theme_relative_strength).label??'主题相对强弱不足'}}</p>
        <details class="mobile-metrics"><summary>指标与 {{horizon}} 日研究</summary><div class="mobile-price-pair">
          <div><small>MACD DIF / DEA</small><span>{{num(record(row.macd).dif,4)}} / {{num(record(row.macd).dea,4)}}</span></div>
          <div><small>KDJ J / RSI</small><span>{{num(record(row.kdj).j)}} / {{num(record(row.rsi).value)}}</span></div>
          <div><small>均线状态</small><span>{{record(row.ma).label??'未知'}}</span></div><div><small>量能状态</small><span>{{record(row.volume).label??'未知'}}</span></div>
        </div><p>研究收益 {{pct(forecast(row).expected_return)}} · {{forecast(row).calibration_status??'not_calibrated'}}<br/><small>基准 {{forecast(row).as_of_date??'未知'}}；未校准结果不作为操作指令。盘中观察不能冒充已校准 EOD 预测。</small></p></details>
        <p class="mobile-reason">{{explainStatus(row)}}</p>
        <small>源时间 {{stamp(record(row.quote).source_time)}} · {{record(row.quote).timestamp_verified===true?'源时间已核验':'源时间未核验'}}</small>
      </article>
    </section>
  </section>
  <details class="decision-reason-list">
    <summary>查看各标的数据状态与受阻原因（{{rows.length}}）</summary>
    <p class="small-note">保留服务端状态与原因；“数据异常”不是可以忽略的警告。</p>
    <p v-for="row in rows" :key="String(row.ts_code)"><RouterLink :to="`/etf/${row.ts_code}`">{{row.name}} · {{row.ts_code}}</RouterLink><span>{{explainStatus(row)}}</span></p>
  </details>
</template>
