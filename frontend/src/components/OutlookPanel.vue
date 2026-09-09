<script setup lang="ts">
import {computed,ref} from 'vue'
import {useQuery} from '../lib/query'
import {api,errorText} from '../lib/api'
import {useSession} from '../stores/session'
import ForecastCards from './ForecastCards.vue'
import TaskProgress from './TaskProgress.vue'
import type {Forecast,DataJob} from '../lib/types'
const props=defineProps<{code?:string;forecasts?:Record<string,Forecast>}>(),session=useSession(),job=ref(''),error=ref(''),busy=ref(false)
const q=useQuery<{items:Record<string,{forecasts:Record<string,Forecast>;reason?:string;source_as_of?:string}>}>(()=>'/api/workspace/research-outlook'+(props.code?'?code='+encodeURIComponent(props.code):''))
const values=computed(()=>({...q.data.value?.items[props.code??'']?.forecasts,...props.forecasts}))
async function compute(){if(busy.value)return;busy.value=true;error.value='';try{const r=await api<{job:DataJob}>('/api/workspace/data-jobs',{method:'POST',body:{task:'research_outlook',codes:props.code?[props.code]:[],request_key:crypto.randomUUID()}});job.value=r.job.job_id}catch(e){error.value=errorText(e)}finally{busy.value=false}}
</script><template><section><div class="toolbar"><button v-if="session.role==='admin'||!session.identifier" class="button small" :disabled="busy" @click="compute">计算日 / 周 / 月研究</button><span class="small-note">仅用已存日K，最多30只；不足250根不计算。结果在总览与详情共用，不调用AI、不改交易动作。</span></div><p v-if="error||q.error.value" role="alert">{{error||q.error.value}}</p><TaskProgress v-if="job" :id="job" @finished="q.reload()"/><ForecastCards :forecasts="values"/><p v-if="code&&q.data.value?.items[code]?.reason" class="notice">{{q.data.value.items[code].reason}}</p></section></template>
