<script setup lang="ts">
import {onMounted,onBeforeUnmount,ref,watch} from 'vue'
import {api,errorText} from '../lib/api'
import {statusName,stamp} from '../lib/format'
import type {DataJob} from '../lib/types'
const props=defineProps<{id:string}>(),emit=defineEmits<{finished:[job:DataJob]}>(),job=ref<DataJob|null>(null),error=ref('')
let timer:ReturnType<typeof setTimeout>|undefined,revision=0,disposed=false
async function poll(id:string,token:number,count=0){try{const r=await api<{items:DataJob[]}>('/api/workspace/data-jobs');if(disposed||token!==revision)return;job.value=r.items.find(j=>j.job_id===id)??null;error.value='';if(job.value&&['succeeded','partial','failed','cancelled'].includes(job.value.status)){emit('finished',job.value);return}if(count<150)timer=setTimeout(()=>void poll(id,token,count+1),2000);else error.value='仍未结束，请在设置查看队列；超过等待时间不代表任务成功。'}catch(e){if(!disposed&&token===revision)error.value=errorText(e)}}
function start(){clearTimeout(timer);job.value=null;error.value='';void poll(props.id,++revision)}
onMounted(start);watch(()=>props.id,start);onBeforeUnmount(()=>{disposed=true;++revision;clearTimeout(timer)})
</script><template><div class="notice" role="status" data-testid="task-progress"><strong>{{statusName(job?.status??'queued')}}</strong> · {{job?.task??'任务'}} · {{job?.result?.current_step??''}}<small> {{id.slice(0,8)}} · {{stamp(job?.created_at)}}</small><div v-for="(s,i) in job?.result?.steps??[]" :key="i">{{s.task}}：{{statusName(s.status)}} {{s.reason??''}}</div><p v-if="job?.failure_reason||error" class="warning-notice">{{job?.failure_reason||error}}</p><RouterLink to="/settings">查看任务与数据源状态</RouterLink></div></template>
