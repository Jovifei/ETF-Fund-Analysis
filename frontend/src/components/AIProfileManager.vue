<script setup lang="ts">
import {computed,onBeforeUnmount,ref,watch} from 'vue'
import {X} from 'lucide-vue-next'
import {api,errorText} from '../lib/api'
import {useQuery} from '../lib/query'
import {useSession} from '../stores/session'
import TaskProgress from './TaskProgress.vue'
import Badge from './Badge.vue'
interface Profile {id:string;name:string;base_url:string;model:string;max_tokens:number;token_parameter?:string;revision:number;has_key:boolean;last_test?:{status:string;at:string}}
interface Profiles {items:Profile[];default_id:string|null;available:boolean;blocked_reason:string|null;allowed_origins:string[]}
const props=defineProps<{researchId?:string}>(),emit=defineEmits<{executed:[]}>(),session=useSession()
const q=useQuery<Profiles>(()=>session.identifier?'/api/workspace/ai/profiles':null)
const chosen=ref(''),editing=ref(''),name=ref('我的研究模型'),base=ref('https://api.openai.com/v1'),model=ref(''),key=ref(''),maxTokens=ref(1800),tokenParameter=ref('auto'),revision=ref<number|undefined>(),error=ref(''),message=ref(''),busy=ref(false),consent=ref(false),jobId=ref(''),showForm=ref(false)
const available=computed(()=>!!q.data.value?.available)
const presets=[
  {label:'DeepSeek',name:'DeepSeek 研判',base:'https://api.deepseek.com/v1',model:'deepseek-chat',max_tokens:2048},
  {label:'OpenAI',name:'OpenAI GPT-4o-mini',base:'https://api.openai.com/v1',model:'gpt-4o-mini',max_tokens:1800},
  {label:'Kimi',name:'Kimi (Moonshot)',base:'https://api.moonshot.cn/v1',model:'moonshot-v1-8k',max_tokens:2048},
]
function applyPreset(p:typeof presets[0]){name.value=p.name;base.value=p.base;model.value=p.model;maxTokens.value=p.max_tokens}
watch(q.data,r=>{if(!chosen.value&&r?.items.length)chosen.value=r.default_id??r.items[0]!.id})
function explain(raw:string|undefined|null){const messages:Record<string,string>={ai_api_disabled:'管理员尚未启用模型 API 通道。行情和本地 Codex 不受影响。',ai_key_store_not_configured:'尚未配置私有密钥文件，请按下方部署步骤初始化。',ai_key_store_unavailable:'私有密钥文件无法读取，需检查运行用户与文件权限。',ai_endpoint_not_in_admin_allowlist:'此模型地址不在管理员批准的服务域名列表。',ai_daily_budget_exceeded:'本账户今日调用预算用完，请勿反复重试。'};return raw?messages[raw]??raw:''}
async function act(fn:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';message.value='';try{await fn()}catch(e){error.value=explain(errorText(e))}finally{busy.value=false}}
function edit(p?:Profile){editing.value=p?.id??'';revision.value=p?.revision;name.value=p?.name??'我的研究模型';base.value=p?.base_url??'https://api.openai.com/v1';model.value=p?.model??'';maxTokens.value=p?.max_tokens??1800;tokenParameter.value=p?.token_parameter??'auto';key.value='';showForm.value=true}
async function save(){await act(async()=>{try{const r=await api<Profile>('/api/workspace/ai/profiles'+(editing.value?'/'+editing.value:''),{method:editing.value?'PUT':'POST',body:{name:name.value,base_url:base.value,model:model.value,max_tokens:maxTokens.value,token_parameter:tokenParameter.value,...(key.value?{api_key:key.value}:{}),...(revision.value?{expected_revision:revision.value}:{})}});chosen.value=r.id;showForm.value=false;message.value='已加密保存，尚未调用模型。';await q.reload()}finally{key.value=''}})}
async function makeDefault(){await act(async()=>{await api('/api/workspace/ai/profiles/'+chosen.value+'/default',{method:'POST'});await q.reload();message.value='已设为本人 ETF 分析与每日复盘的共用默认配置。'})}
async function remove(p:Profile){if(!confirm('删除此模型配置？已有报告保留，待执行任务将因配置失效而停止。'))return;await act(async()=>{await api('/api/workspace/ai/profiles/'+p.id,{method:'DELETE'});if(chosen.value===p.id)chosen.value='';await q.reload()})}
async function execute(test:boolean){if(!consent.value||!chosen.value)return;await act(async()=>{const r=await api<{job:{job_id:string}}>('/api/workspace/ai/profiles/'+chosen.value+(test?'/test':'/run'),{method:'POST',body:{confirm_cost:true,request_key:crypto.randomUUID(),...(!test?{research_id:props.researchId}:{})}});jobId.value=r.job.job_id;consent.value=false;message.value='任务已排队，只有工作器实际调用时才可能计费。失败不自动重试。';emit('executed')})}
onBeforeUnmount(()=>{key.value=''})
</script>
<template><section class="card section" data-testid="ai-profile-manager"><div class="card-header"><h2>{{researchId?'用已保存的模型分析这份证据':'模型 API 连接'}}</h2><button class="text-button" @click="q.reload">刷新配置</button></div><div class="card-body"><p>填写服务地址、API Key 和模型名，一次配置可在 ETF 分析与每日复盘复用。<strong>保存配置、打开页面都不调用模型。</strong></p>
<p v-if="!session.identifier" class="notice">请先用数据库账户登录，离线无认证演示不能保存私人凭据或调用模型。</p><p v-if="q.error.value||error" role="alert" class="form-error">{{error||q.error.value}}</p><p v-if="message" role="status" class="notice">{{message}}</p><p v-if="q.data.value&&!available" class="notice warning-notice">{{explain(q.data.value.blocked_reason)}}</p>
<template v-if="session.identifier"><div class="actions"><label class="field">本人已保存配置<select v-model="chosen" aria-label="选择共用AI配置"><option value="">请选择配置</option><option v-for="p in q.data.value?.items??[]" :key="p.id" :value="p.id">{{p.name}} · {{p.model}}{{p.id===q.data.value?.default_id?'（默认）':''}}</option></select></label><button class="button primary" :disabled="!available" @click="edit()">+ 新增模型配置</button><button class="button" :disabled="!chosen||busy" @click="makeDefault">设为共用默认</button></div>

<div v-if="showForm" class="slide-drawer-backdrop" @click="showForm=false;key=''"/>
<div v-if="showForm" class="slide-drawer" role="dialog" aria-modal="true" aria-label="模型配置抽屉">
  <div class="slide-drawer-header"><h3>{{editing?'编辑模型配置':'新增模型配置'}}</h3><button type="button" class="icon-button" aria-label="关闭抽屉" @click="showForm=false;key=''"><X :size="18"/></button></div>
  <form class="slide-drawer-body" @submit.prevent="save">
    <div class="preset-row"><span class="preset-label">快捷预设：</span><button v-for="p in presets" :key="p.label" type="button" class="preset-btn" @click="applyPreset(p)">{{p.label}}</button></div>
    <div class="field"><label>配置名称</label><input v-model="name" required maxlength="64" placeholder="例如：DeepSeek 研判模型"></div>
    <div class="field"><label>服务 Base URL</label><input v-model="base" aria-label="模型服务地址" type="url" required maxlength="240" placeholder="https://api.deepseek.com/v1"></div>
    <div class="field"><label>模型名称</label><input v-model="model" aria-label="模型名称" required maxlength="96" placeholder="例如 deepseek-chat 或 gpt-4o-mini"></div>
    <div class="field"><label>API Key</label><input v-model="key" aria-label="模型 API Key" type="password" autocomplete="new-password" :required="!editing" maxlength="4096" placeholder="输入 API Key"><small>{{editing?'留空保留原Key；修改不回显原值':'只用于此配置，不是Codex登录文件或网站密码'}}</small></div>
    <div class="field"><label>Token参数格式</label><select v-model="tokenParameter"><option value="auto">按服务商自动选择</option><option value="max_completion_tokens">max_completion_tokens（新版OpenAI）</option><option value="max_tokens">max_tokens（标准兼容服务）</option></select><small>不兼容时修改配置后再人工重试，不自动重复计费。</small></div>
    <div class="field"><label>最大输出 Token</label><input v-model.number="maxTokens" type="number" min="128" max="4000"></div>
    <p class="small-note">服务域名需管理员批准：{{q.data.value?.allowed_origins.join('、')}}。不要把 /chat/completions 拼入 Base URL。</p>
    <div class="slide-drawer-footer"><button class="button primary" :disabled="busy">加密保存配置</button><button type="button" class="button" @click="showForm=false;key=''">取消</button></div>
  </form>
</div>

<div class="section" v-if="q.data.value?.items?.length">
  <div v-for="p in q.data.value?.items??[]" :key="p.id" class="profile-card-item" :class="{'is-default':p.id===q.data.value?.default_id}">
    <div class="profile-info">
      <strong>{{p.name}} <Badge v-if="p.id===q.data.value?.default_id" value="active" label="默认"/><Badge :value="p.last_test?.status==='succeeded'?'active':'pending'" :label="p.last_test?.status==='succeeded'?'已通过测试':'未测试'"/></strong>
      <small>{{p.base_url}} · {{p.model}} · Key {{p.has_key?'已加密保存':'未保存'}}</small>
    </div>
    <div class="actions">
      <button class="button small" @click="edit(p)">编辑</button>
      <button class="button small danger" :disabled="busy" @click="remove(p)">删除</button>
    </div>
  </div>
</div>

<div class="switch-row" @click="consent=!consent">
  <div class="switch-track" :class="{on:consent}" role="switch" :aria-checked="consent"><div class="switch-thumb"/></div>
  <span class="switch-label">我确认这次请求可能产生服务商费用；连接测试最多输出256 Token，研究按所选配置限额。</span>
</div>
<div class="actions">
  <button class="button" :disabled="!available||!chosen||!consent||busy" :title="!available?(q.data.value?explain(q.data.value.blocked_reason):'管理员尚未启用通道'):!chosen?'请先在上方下拉框选择一个已保存的配置':!consent?'请先开启费用确认开关':busy?'执行中…':'测试与大模型连通性'" @click="execute(true)">测试连接（可能计费）</button>
  <button v-if="researchId" class="button primary" :disabled="!available||!chosen||!consent||busy" :title="!available?(q.data.value?explain(q.data.value.blocked_reason):'管理员尚未启用通道'):!chosen?'请先在上方下拉框选择一个已保存的配置':!consent?'请先开启费用确认开关':''" @click="execute(false)">使用此配置开始研究</button>
  <small>免费账户每日最多5次 API 请求，Plus/管理员30次；失败也占预算，防止反复消耗。</small>
</div>
<TaskProgress v-if="jobId" :id="jobId" @finished="q.reload();emit('executed')"/>
<details class="details-block"><summary>管理员首次启用 API 的部署步骤</summary><ol><li>在运行该服务的机器上，创建仓库外的私有主密钥：<code>python scripts/create_ai_secret_store.py --path E:\ETF_Private\ai\master.key</code>（Linux使用私有绝对目录，例如 /var/lib/etf-private/ai/master.key）。不要覆盖已存在的密钥。</li><li>在私人环境中设置 <code>WORKSPACE_AI_KEY_FILE</code> 指向该文件，<code>WORKSPACE_AI_API_ENABLED=true</code>；API和worker须读到同一密钥文件。Windows文件只允许原DPAPI用户解密，不能直接搬到Linux。</li><li>额外服务域名由管理员通过 <code>WORKSPACE_AI_ALLOWED_ORIGINS</code> 配置，只允许明确批准的HTTPS公网域名。</li><li>重启API与worker，再回来新增配置、勾选费用确认、测试一次。不要把密钥写入Git或浏览器存储。</li></ol></details></template>
<p class="small-note">结果是待审核研究解释，不自动买卖、不改指标和预测资格。当前支持 OpenAI-compatible Chat Completions，不宣称兼容所有厂商专用协议。</p></div></section></template>
