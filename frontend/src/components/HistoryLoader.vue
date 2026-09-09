<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import { useFavorites } from '../stores/favorites'
import { api, errorText } from '../lib/api'
import type { DataJob } from '../lib/types'
const favorites=useFavorites()
const props = defineProps<{code:string}>(), emit=defineEmits<{updated:[]}>(), busy=ref(false), message=ref('')
let timer: ReturnType<typeof setTimeout>|undefined, disposed=false
async function poll(id:string, count=0) {
  try {
    const result=await api<{items:DataJob[]}>('/api/workspace/data-jobs?limit=50')
    if(disposed)return
    const job=result.items.find(row=>row.job_id===id)
    message.value='历史准备：'+(job?.status??'待工作器领取')+(job?.failure_reason?' · '+job.failure_reason:'')
    if(job&&['succeeded','partial','failed','cancelled'].includes(job.status)){busy.value=false;void favorites.reload().catch(()=>{});emit('updated');return}
    if(count<60) timer=setTimeout(()=>void poll(id,count+1),3000)
    else {busy.value=false;message.value+='；稍后在设置查看任务，已有 K 线仍可使用。'}
  }catch(e){ if(!disposed){busy.value=false;message.value=errorText(e)} }
}
async function prepare(){
 if(busy.value)return;busy.value=true;message.value=''
 try{const result=await api<{job:DataJob}>('/api/workspace/onboard',{method:'POST',body:{task:'onboard',codes:[props.code],lookback_days:1200,request_key:crypto.randomUUID()}});if(!disposed)void poll(result.job.job_id)}
 catch(e){if(!disposed){busy.value=false;message.value=errorText(e)}}
}
onBeforeUnmount(()=>{disposed=true;clearTimeout(timer)})
</script>
<template><div class="toolbar"><button class="button small" :disabled="busy" @click="prepare">{{busy?'正在准备历史…':'补齐历史并加入研究池'}}</button><small>明确点击才下载并更新该基金；同时加入自选，不自动调用 AI。已有历史无需重新下载即可看图。</small><span role="status">{{message}}</span></div></template>
