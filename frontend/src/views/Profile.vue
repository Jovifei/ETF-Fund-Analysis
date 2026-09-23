<script setup lang="ts">
import {computed,ref,watch,onBeforeUnmount} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {UserRound,ShieldCheck,SlidersHorizontal,Sparkles,ChevronRight,Mail,Smartphone,MessageCircle,ArrowLeft} from 'lucide-vue-next'
import {api,errorText} from '../lib/api'
import {useQuery} from '../lib/query'
import {useSession} from '../stores/session'
import {stamp} from '../lib/format'
import PageState from '../components/PageState.vue'
import UserManagement from '../components/UserManagement.vue'
import AIProfileManager from '../components/AIProfileManager.vue'
import AISetupGuide from '../components/AISetupGuide.vue'
interface Account {identifier:string;display_name:string;role:string;plan:string;created_at:string;last_login_at:string|null;email:{masked:string|null;state:string};capabilities:{change_password:boolean;close_access:boolean;email_verification:boolean;sms_verification:boolean;wechat_oauth:boolean;permanent_erasure:boolean}}
interface Preferences {daily_review:boolean;sidebar:'expanded'|'compact'|'hidden';reduce_motion:boolean}
const session=useSession(),route=useRoute(),router=useRouter()
const tabs=[{id:'profile',label:'个人资料',icon:UserRound},{id:'security',label:'登录与安全',icon:ShieldCheck},{id:'preferences',label:'偏好设置',icon:SlidersHorizontal},{id:'ai',label:'我的 AI',icon:Sparkles}]
const tab=computed(()=>tabs.some(t=>t.id===route.query.section)?String(route.query.section):'profile')
const q=useQuery<Account>(()=>session.identifier?'/api/workspace/account':null)
const pref=useQuery<Preferences>(()=>session.identifier&&tab.value==='preferences'?'/api/workspace/preferences':null)
const nickname=ref(''),oldPassword=ref(''),newPassword=ref(''),confirmPassword=ref(''),closePassword=ref(''),confirmation=ref(''),acknowledge=ref(false),busy=ref(false),message=ref(''),error=ref('')
const form=ref<Preferences>({daily_review:false,sidebar:'expanded',reduce_motion:false})
watch(q.data,value=>{if(value)nickname.value=value.display_name})
watch(pref.data,value=>{if(value)form.value={...value}})
function clearSecrets(){oldPassword.value='';newPassword.value='';confirmPassword.value='';closePassword.value='';confirmation.value='';acknowledge.value=false}
watch(tab,()=>{clearSecrets();message.value='';error.value=''})
onBeforeUnmount(clearSecrets)
async function select(id:string){if(!busy.value)await router.replace({path:'/profile',query:{section:id}})}
async function act(work:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';message.value='';try{await work()}catch(e){error.value=errorText(e)}finally{busy.value=false}}
async function saveName(){await act(async()=>{q.data.value=await api<Account>('/api/workspace/account/profile',{method:'PATCH',body:{display_name:nickname.value}});message.value='个人资料已保存；登录账户未改变。'})}
async function changePassword(){
 if(newPassword.value!==confirmPassword.value){error.value='两次新密码不一致';return}
 await act(async()=>{try{await api('/api/workspace/account/password',{method:'PUT',body:{current_password:oldPassword.value,new_password:newPassword.value}});session.clear();session.feedback='密码已修改，所有浏览器会话已退出。请使用新密码登录。'}finally{oldPassword.value='';newPassword.value='';confirmPassword.value=''}})
}
async function closeAccount(){await act(async()=>{try{await api('/api/workspace/account/closure',{method:'POST',body:{current_password:closePassword.value,confirmation:confirmation.value,acknowledge_retention:acknowledge.value}});session.clear();session.feedback='账户登录访问已注销，研究记录仍保留。需要恢复或清理数据时请联系管理员。'}finally{clearSecrets()}})}
async function savePreferences(){await act(async()=>{form.value=await api<Preferences>('/api/workspace/preferences',{method:'PUT',body:form.value});window.dispatchEvent(new CustomEvent('workspace-preferences',{detail:form.value}));message.value='偏好已保存。'})}
</script>
<template>
 <section class="personal-center" aria-labelledby="personal-title">
  <header class="personal-header"><div><p class="eyebrow">YOUR PRIVATE WORKSPACE</p><h1 id="personal-title">个人中心</h1></div><RouterLink to="/" class="button"><ArrowLeft :size="16"/>返回市场</RouterLink></header>
  <div v-if="!session.identifier" class="notice" role="status">当前为无认证演示模式，不存在已验证的个人账户。账户操作需使用数据库账户登录。<RouterLink to="/settings">查看设置与连接</RouterLink></div>
  <div v-else class="personal-layout">
   <nav class="personal-nav" aria-label="个人中心分类"><p>账户与工作区</p><button v-for="item in tabs" :key="item.id" :class="{active:tab===item.id}" :aria-current="tab===item.id?'page':undefined" :disabled="busy" @click="select(item.id)"><component :is="item.icon" :size="19"/><span>{{item.label}}</span><ChevronRight :size="14"/></button><RouterLink to="/history">研究档案与下载</RouterLink><RouterLink to="/settings">数据与设备连接</RouterLink><small>ETF Research<br>资料、权限与行情资格互相独立</small></nav>
   <div class="personal-content" :aria-busy="busy">
    <p v-if="message" class="notice" role="status">{{message}}</p><p v-if="error" class="form-error" role="alert">{{error}}</p>
    <PageState :loading="q.loading.value" :error="q.error.value" :empty="!q.data.value" @retry="q.reload">
     <template v-if="q.data.value">
      <section v-if="tab==='profile'" aria-labelledby="profile-title"><h2 id="profile-title">个人资料</h2><p class="muted">管理显示名称与账户信息；绑定状态以服务端验证为准。</p>
       <div class="profile-identity"><div class="profile-avatar" aria-hidden="true">{{Array.from(q.data.value.display_name)[0]}}</div><div><h3>{{q.data.value.display_name}}</h3><p>{{q.data.value.role==='admin'?'管理员':'成员'}} · {{q.data.value.plan==='plus'?'Plus':'普通账户'}}</p></div></div>
       <dl class="profile-facts"><div><dt>登录账户</dt><dd>{{q.data.value.identifier}}</dd></div><div><dt>加入日期</dt><dd>{{stamp(q.data.value.created_at)}}</dd></div><div><dt>邮箱</dt><dd>{{q.data.value.email.masked??'未绑定'}} <span class="unverified">{{q.data.value.email.state==='recorded_unverified'?'已登记 · 未验证':'未验证'}}</span></dd></div><div><dt>手机号 / 微信</dt><dd>验证渠道未接入</dd></div></dl>
       <form class="profile-name" @submit.prevent="saveName"><label for="profile-name">显示名称</label><p class="muted">只更改昵称，不更改登录账户、角色或会员权益。</p><div><input id="profile-name" v-model="nickname" maxlength="48" required autocomplete="nickname" :disabled="busy"><button class="button primary" :disabled="busy">保存修改</button></div></form>
       <UserManagement v-if="session.role==='admin'"/>
      </section>
      <section v-else-if="tab==='security'" aria-labelledby="security-title"><h2 id="security-title">登录与安全</h2><p class="muted">敏感操作需要当前密码。浏览器不会保存你的密码。</p>
       <details class="security-item" data-testid="account-password"><summary><strong>登录密码</strong><span>设置与更新</span></summary><form @submit.prevent="changePassword"><p class="notice">修改成功后，全部浏览器会话立即失效；需要使用新密码重新登录。</p><label>当前密码<input v-model="oldPassword" type="password" autocomplete="current-password" maxlength="1024" required :disabled="busy"></label><label>新密码<input v-model="newPassword" type="password" autocomplete="new-password" minlength="15" maxlength="1024" required :disabled="busy"></label><small>至少 15 个字符，支持空格与密码管理器粘贴。</small><label>确认新密码<input v-model="confirmPassword" type="password" autocomplete="new-password" minlength="15" maxlength="1024" required :disabled="busy"></label><button class="button primary" :disabled="busy">确认修改密码并退出会话</button></form></details>
       <div class="contact-item"><Mail :size="20"/><div><strong>安全邮箱</strong><p>{{q.data.value.email.masked??'未绑定'}} · {{q.data.value.email.masked?'已登记不等于所有权已验证':'尚未验证'}}</p><small>需接入邮件验证与旧邮箱通知，才能绑定或更换。</small></div><button class="button" disabled :title="'邮件验证服务未接入'">{{q.data.value.email.masked?'更换邮箱':'绑定邮箱'}}</button></div>
       <div class="contact-item"><Smartphone :size="20"/><div><strong>手机号码</strong><p>短信验证服务未接入</p><small>接入后再开放绑定、更换及验证码登录，不使用测试验证码代替。</small></div><button class="button" disabled title="短信验证服务未接入">绑定 / 更换手机号</button></div>
       <div class="contact-item"><MessageCircle :size="20"/><div><strong>微信账号</strong><p>微信授权服务未接入</p><small>需微信官方授权回调；填写微信号不等于绑定。</small></div><button class="button" disabled title="微信授权服务未接入">绑定微信</button></div>
       <details class="security-item danger-zone" data-testid="account-closure"><summary><strong>注销账户登录访问</strong><span>需再次确认</span></summary><form @submit.prevent="closeAccount"><p class="notice warning-notice">此操作禁用当前账户，退出全部会话并撤销研究设备。持仓、自选、研究报告和备份不会被删除。永久数据删除尚未实现，需另行确认处理；最后一个管理员不能注销。</p><label>验证当前密码<input v-model="closePassword" type="password" autocomplete="current-password" maxlength="1024" required :disabled="busy"></label><label>输入“注销当前账户”<input v-model="confirmation" autocomplete="off" maxlength="16" required :disabled="busy"></label><label class="checkbox-label"><input v-model="acknowledge" type="checkbox" :disabled="busy">我理解这会禁用登录，但不会永久删除研究数据。</label><button class="button danger" :disabled="busy||confirmation!=='注销当前账户'||!acknowledge">确认注销登录访问</button></form></details>
      </section>
      <section v-else-if="tab==='preferences'"><h2>偏好设置</h2><p class="muted">界面偏好不会修改研究算法或数据资格。</p><PageState :loading="pref.loading.value" :error="pref.error.value" @retry="pref.reload"><form class="preference-form" @submit.prevent="savePreferences"><label>侧栏形态<select v-model="form.sidebar"><option value="expanded">展开</option><option value="compact">紧凑</option><option value="hidden">隐藏</option></select></label><label class="checkbox-label"><input v-model="form.reduce_motion" type="checkbox">减少页面切换动效</label><label class="checkbox-label"><input v-model="form.daily_review" type="checkbox">允许在盘后条件满足时创建复盘任务</label><p class="small-note">模型执行仍需独立的配置、设备和费用授权。</p><button class="button primary" :disabled="busy||!pref.data.value">保存偏好</button></form></PageState></section>
      <section v-else><h2>我的 AI</h2><p class="muted">沿用现有模型配置与本地 Bridge。浏览此页不会调用模型。</p><AISetupGuide/><AIProfileManager/><RouterLink class="button" to="/settings">管理本地研究设备</RouterLink></section>
     </template>
    </PageState>
   </div>
  </div>
 </section>
</template>
<style scoped>
.personal-center{border:1px solid var(--border);border-radius:16px;background:linear-gradient(135deg,#0c121e,#10151d);overflow:clip;min-width:0}.personal-header{display:flex;justify-content:space-between;gap:20px;align-items:center;padding:26px 30px;border-bottom:1px solid var(--border)}.personal-header h1{font-size:24px;margin:0}.personal-header .eyebrow{margin-bottom:8px}.personal-layout{display:grid;grid-template-columns:220px minmax(0,1fr);min-height:660px}.personal-nav{padding:24px 16px;background:#080c14;border-right:1px solid var(--border);display:flex;flex-direction:column;gap:7px}.personal-nav p,.personal-nav small{font-size:12px;color:var(--muted);padding:8px 12px}.personal-nav small{margin-top:auto;line-height:1.9}.personal-nav button,.personal-nav>a{border:1px solid transparent;border-radius:7px;background:none;text-align:left;display:flex;align-items:center;gap:12px;padding:14px 12px;color:var(--muted);font-size:14px;min-width:0;min-height:46px}.personal-nav button svg:last-child{margin-left:auto}.personal-nav button.active{background:#142430;border-color:#294454;color:#76c3f4}.personal-content{padding:clamp(20px,3vw,44px);min-width:0}.personal-content h2{font-size:26px;margin-bottom:12px}.profile-identity{display:flex;gap:20px;align-items:center;margin:30px 0}.profile-identity h3{font-size:25px;margin:0 0 8px;overflow-wrap:anywhere}.profile-identity p{margin:0;color:var(--accent)}.profile-avatar{width:70px;height:70px;flex:none;display:grid;place-items:center;border:1px solid #314758;background:#182a3b;border-radius:20px;font-size:30px;color:#76c3f4}.profile-facts{display:grid;grid-template-columns:1fr 1fr;margin-bottom:30px}.profile-facts>div{padding:22px 0;border-block:1px solid var(--border);min-width:0}.profile-facts dt{color:var(--muted);font-size:12px;margin-bottom:10px}.profile-facts dd{margin:0;overflow-wrap:anywhere}.unverified{display:inline-block;color:var(--warn);font-size:11px;margin:6px}.profile-name{margin-bottom:30px}.profile-name>label{font-weight:600}.profile-name>p{font-size:12px;margin:8px 0 18px}.profile-name>div{display:flex;gap:14px;flex-wrap:wrap}.profile-name input{flex:1;min-width:min(100%,180px);min-height:48px}.profile-name .button{min-height:48px}.security-item,.contact-item{border-top:1px solid var(--border);padding:22px 0}.security-item summary{display:flex;justify-content:space-between;align-items:center;gap:16px;cursor:pointer;min-height:44px}.security-item summary span{color:var(--muted);font-size:12px}.security-item summary::after{content:'⌄';color:var(--muted)}.security-item[open] summary::after{content:'⌃'}.security-item summary strong{flex:1}.security-item form{max-width:660px;padding-top:18px}.security-item form>label:not(.checkbox-label),.preference-form>label:not(.checkbox-label){display:grid;gap:9px;margin:18px 0}.security-item input,.preference-form select{min-height:46px}.security-item .checkbox-label{margin:20px 0}.security-item .checkbox-label input{min-height:0}.contact-item{display:flex;gap:14px;align-items:flex-start}.contact-item>div{flex:1;min-width:0}.contact-item p{color:var(--muted);font-size:13px;margin:10px 0 5px}.contact-item small{line-height:1.8}.contact-item button{white-space:normal;max-width:150px}.danger-zone{border-bottom:1px solid var(--border)}.danger-zone summary strong{color:var(--bull)}.preference-form{max-width:640px}.preference-form .checkbox-label{margin:20px 0}
@media(max-width:800px){.personal-layout{grid-template-columns:1fr}.personal-nav{border-right:0;border-bottom:1px solid var(--border);display:grid;grid-template-columns:repeat(2,minmax(0,1fr));padding:12px;gap:6px}.personal-nav>p,.personal-nav small{display:none}.personal-nav button{padding:12px 9px;font-size:13px}.personal-nav>a{font-size:12px}.personal-header{padding:20px}.personal-content{padding:20px 16px}.profile-facts{grid-template-columns:1fr}.contact-item{flex-wrap:wrap}.contact-item button{margin-left:34px;max-width:100%}.profile-identity h3{font-size:21px}.personal-header{flex-wrap:wrap}}
</style>
