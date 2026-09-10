<script setup lang="ts">
import {ref} from 'vue'
import {useQuery} from '../lib/query'
import {api, errorText} from '../lib/api'
import {stamp, statusName} from '../lib/format'
import type {DataJob} from '../lib/types'
import TaskProgress from './TaskProgress.vue'
type Panel = {key:string;label:string;rows:number;latest_source:string|null;latest_fetch_in_scope?:string|null;oldest_instrument_latest?:string|null;covered_instruments?:number;tracked_instruments?:number;last_success_at?:string|null;status:string;retry_task:string;last_attempt?:{status:string;failed:boolean;started_at:string;finished_at:string|null}|null}
type Health = {as_of:string;catalog_count:number;tracked_count:number;worker_last_seen_at:string|null;balanced_refresh_enabled:boolean;note:string;panels:Panel[]}
const q=useQuery<Health>('/api/workspace/data-health'), active=ref(''), error=ref(''),pending=ref(false)
async function refreshTask(panel:Panel){
  if(pending.value)return
  if(!window.confirm(`提交“${panel.label}”更新任务？可能请求真实数据源，但不调用模型、不改持仓。`))return
  pending.value=true;error.value=''
  try{const r=await api<{job:DataJob}>('/api/workspace/data-jobs',{method:'POST',body:{task:panel.retry_task,request_key:crypto.randomUUID()}});active.value=r.job.job_id}
  catch(e){error.value=errorText(e)}finally{pending.value=false}
}
function sourceLabel(value:string|null|undefined){
  if(value?.length===10)return value
  if(value && !/Z$|[+-]\d\d:\d\d$/.test(value))return value+'（旧时间无时区，待核实）'
  return stamp(value)
}
defineExpose({reload:q.refresh})
</script>
<template>
  <details class="card section data-health" data-testid="data-health">
    <summary class="card-header"><div><h2>数据更新与缺口</h2><small>查看每类数据的源日期、采集记录和失败状态，不把心跳当作成功。</small></div></summary>
    <div class="card-body">
      <div class="toolbar"><button class="button small" @click="q.reload">重新读取状态（不抓取）</button><small>目录 {{q.data.value?.catalog_count??'—'}} · 研究池 {{q.data.value?.tracked_count??'—'}}</small></div>
      <p v-if="q.error.value||error" class="notice warning-notice" role="alert">{{error||q.error.value}}</p>
      <p v-if="q.loading.value" role="status">正在读取已存统计…</p>
      <p v-if="q.data.value"><strong>{{q.data.value.balanced_refresh_enabled?'已选半小时平衡策略':'半小时平衡策略未启用'}}</strong>。是否实际运行仍需核对 scheduler；worker 心跳 {{stamp(q.data.value.worker_last_seen_at)}}。</p>
      <TaskProgress v-if="active" :id="active" @finished="q.reload"/>
      <div class="table-scroll"><table><thead><tr><th>数据</th><th>最新源日期／时间</th><th>覆盖与缺口</th><th>范围内最近采集／计算</th><th>最近任务 / 最近成功</th><th>操作</th></tr></thead>
        <tbody><tr v-for="p in q.data.value?.panels??[]" :key="p.key">
          <td>{{p.label}}<small>{{p.rows}} 条已存记录</small></td>
          <td>{{sourceLabel(p.latest_source)}}<small v-if="p.oldest_instrument_latest">最旧标的的最新日期 {{sourceLabel(p.oldest_instrument_latest)}}</small></td>
          <td>{{p.rows?'已有记录，资格需独立检查':'尚无数据'}}<small v-if="p.covered_instruments!=null">{{p.covered_instruments}} / {{p.tracked_instruments}} 只研究池标的有记录</small></td>
          <td>{{sourceLabel(p.latest_fetch_in_scope)}}</td>
          <td><span :class="{'warning-notice':p.last_attempt?.failed}">{{p.last_attempt?statusName(p.last_attempt.status):'无任务记录'}}</span><small>成功 {{stamp(p.last_success_at)}}</small></td>
          <td><button class="button small" :disabled="pending" @click="refreshTask(p)">{{p.retry_task==='recompute'?'重算缓存':'提交补采'}}</button></td>
        </tr></tbody></table></div>
      <p class="small-note">{{q.data.value?.note}}<RouterLink to="/settings">查看数据源与详细任务</RouterLink></p>
    </div>
  </details>
</template>
<style scoped>
.data-health summary{cursor:pointer}.data-health th,.data-health td{min-width:128px;vertical-align:top}
.data-health small{display:block;line-height:1.5;margin-top:5px}.data-health h2{font-size:18px}
</style>
