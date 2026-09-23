<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ShieldCheck, Eye, EyeOff, Compass, Moon, Sun, ArrowLeft, Mail, Smartphone, MessageCircle } from 'lucide-vue-next'
import { useSession } from '../stores/session'
import { api, errorText } from '../lib/api'
import { useQuery } from '../lib/query'
const session = useSession(), route = useRoute(), identifier = ref(''), password = ref(''), confirmation = ref(''), email = ref(''), invite = ref(''), show = ref(false), busy = ref(false), error = ref('')
const light = ref(false)
const registration = computed(() => route.path === '/register')
watch(registration, () => { password.value='';confirmation.value='';invite.value='';show.value=false;error.value='' })
const capabilities = useQuery<{registration_enabled:boolean;invite_required:boolean}>('/api/auth/capabilities')
async function submit() {
  if (busy.value) return
  error.value=''
  if (registration.value && password.value !== confirmation.value) { error.value='两次密码不一致';return }
  busy.value=true
  try {
    if (registration.value) {
      await api('/api/auth/register',{method:'POST',body:{identifier:identifier.value.trim(),password:password.value,email:email.value.trim()||null,invite_code:invite.value.trim()}})
      await session.load()
    } else await session.login(identifier.value,password.value)
  } catch(e) { error.value=errorText(e) }
  finally { password.value='';confirmation.value='';invite.value='';busy.value=false }
}
</script>
<template>
 <div class="login-screen auth-scene" :data-auth-theme="light?'light':'dark'">
  <div class="auth-atmosphere" aria-hidden="true"></div>
  <section class="login-card auth-card" :aria-busy="busy">
   <div class="auth-top"><button type="button" class="auth-quiet" aria-label="切换登录页明暗主题" @click="light=!light"><Sun v-if="light" :size="18"/><Moon v-else :size="18"/>{{light?'浅色':'深色'}}</button><RouterLink class="auth-quiet" to="/"><ArrowLeft :size="16"/>返回工作站</RouterLink></div>
   <div class="auth-wordmark"><Compass :size="27"/><span>ETF <b>Research</b></span></div>
   <h1>{{registration?'创建账户':'账户登录'}}</h1><p class="auth-intro">{{registration?'建立你的私有研究空间':'继续查看你的市场研究工作台'}}</p>
   <p class="auth-context">现有账户使用密码登录；新账户沿用管理员邀请注册。</p>
   <nav class="section-tabs auth-tabs" aria-label="账户入口"><RouterLink :to="{path:'/login',query:route.query}" :class="{active:!registration}" :aria-current="!registration?'page':undefined">账户登录</RouterLink><RouterLink :to="{path:'/register',query:route.query}" :class="{active:registration}" :aria-current="registration?'page':undefined">创建账户</RouterLink></nav>
   <p v-if="session.feedback" class="auth-feedback" role="status">{{session.feedback}}</p>
   <p v-if="capabilities.error.value" class="auth-feedback" role="alert">无法读取注册状态，请重试。<button class="text-button" @click="capabilities.reload">重试</button></p>
   <div v-if="registration&&capabilities.data.value&&!capabilities.data.value.registration_enabled" class="auth-feedback">当前未开放邀请注册。请管理员在“个人中心 → 用户管理”创建成员账户；此页面不能创建管理员。</div>
   <form v-else @submit.prevent="submit">
    <label>账户<input v-model="identifier" autocomplete="username" maxlength="128" required placeholder="输入用户名或已登记邮箱" :disabled="busy"></label>
    <label v-if="registration">邮箱（可选）<input v-model="email" type="email" autocomplete="email" maxlength="320" :disabled="busy"><small>登记邮箱不代表已验证所有权。</small></label>
    <label>密码<div class="password-field"><input v-model="password" aria-label="密码" :type="show?'text':'password'" :autocomplete="registration?'new-password':'current-password'" :minlength="registration?6:undefined" maxlength="1024" required :disabled="busy" placeholder="输入账户密码"><button type="button" class="auth-eye" :aria-label="show?'隐藏密码':'显示密码'" :aria-pressed="show" @click="show=!show"><EyeOff v-if="show" :size="19"/><Eye v-else :size="19"/></button></div></label>
    <label v-if="registration">确认密码<input v-model="confirmation" type="password" autocomplete="new-password" maxlength="1024" required :disabled="busy"></label>
    <label v-if="registration">邀请码<input v-model="invite" type="password" autocomplete="off" maxlength="128" required :disabled="busy"></label>
    <p v-if="error" class="auth-feedback auth-error" role="alert">{{error}}</p>
    <button class="button primary full auth-submit" :disabled="busy||(registration&&!capabilities.data.value?.registration_enabled)">{{busy?'正在验证账户…':registration?'创建账户并进入总览':'登录并进入总览'}}</button>
   </form>
   <div class="auth-other"><span>其他验证方式</span><div><button disabled title="邮件验证码渠道未接入"><Mail :size="17"/>邮箱验证码</button><button disabled title="短信验证码渠道未接入"><Smartphone :size="17"/>手机验证码</button><button disabled title="微信授权渠道未接入"><MessageCircle :size="17"/>微信</button></div><small>尚未接通验证服务，不会发送验证码或创建虚假绑定。</small></div>
   <p class="privacy-note"><ShieldCheck :size="16"/><span>密码仅用于登录，不写入浏览器存储。模型密钥在登录后的独立配置页管理。</span></p>
  </section>
  <p class="login-foot">ETF Research · 不连接券商 · 不自动下单</p>
 </div>
</template>
<style scoped>
.auth-scene{--auth-bg:#0b0d10;--auth-card:#17181b;--auth-raised:#222327;--auth-line:#35363b;--auth-text:#f3f4f6;--auth-muted:#a7a9b0;position:relative;isolation:isolate;background:var(--auth-bg);padding:32px 16px;color:var(--auth-text)}.auth-scene[data-auth-theme=light]{--auth-bg:#f0f3f7;--auth-card:#fff;--auth-raised:#f2f4f7;--auth-line:#d0d6df;--auth-text:#17202c;--auth-muted:#5c6572}.auth-atmosphere{position:absolute;inset:0;z-index:-1;overflow:hidden;background:radial-gradient(ellipse at 15% 10%,#16556b24,transparent 50%),radial-gradient(ellipse at 90% 85%,#202e6926,transparent 48%)}.auth-card{width:min(100%,500px);max-width:500px;max-height:none;overflow:visible;padding:30px 36px 32px;margin:8px 0 24px;border:1px solid var(--auth-line);border-radius:22px;background:var(--auth-card);box-shadow:0 24px 70px #0002;animation:auth-enter .25s ease-out}.auth-top{display:flex;justify-content:flex-end;gap:24px;margin-bottom:30px}.auth-quiet{display:inline-flex;align-items:center;gap:8px;background:none;border:0;color:var(--auth-muted);padding:7px 0;font-size:13px;min-height:38px}.auth-wordmark{display:flex;align-items:center;gap:10px;margin-bottom:26px;color:var(--auth-text);font-size:18px;font-weight:650}.auth-wordmark svg{color:#6bbde6}.auth-wordmark b{font-weight:400;color:var(--auth-muted)}.auth-card h1{font-size:clamp(27px,5vw,34px);margin:0 0 12px;letter-spacing:-1px}.auth-intro{color:var(--auth-muted);font-size:15px;margin-bottom:26px}.auth-context{color:var(--auth-muted);background:var(--auth-raised);border:1px solid var(--auth-line);border-radius:10px;padding:12px 14px;font-size:12px;margin-bottom:22px}.auth-tabs{display:grid;grid-template-columns:1fr 1fr;gap:4px;padding:4px;border:0;border-radius:10px;background:var(--auth-raised);margin:0 0 26px}.auth-tabs a{padding:12px;text-align:center;border:0;border-radius:7px;font-size:14px;color:var(--auth-muted)}.auth-tabs a.active{background:var(--auth-card);color:var(--auth-text)}.auth-card form{margin:0}.auth-card label{display:block;color:var(--auth-muted);font-size:13px;margin:17px 0}.auth-card input{margin:9px 0 0;background:var(--auth-raised);border-color:var(--auth-line);color:var(--auth-text);border-radius:10px;padding:14px 15px;min-height:50px;width:100%;font-size:16px}.auth-card label>small{display:block;font-size:11px;margin-top:7px;color:var(--auth-muted)}.password-field{display:flex;align-items:center;position:relative}.password-field input{padding-right:52px}.auth-eye{position:absolute;right:4px;top:14px;width:42px;height:42px;border:0;border-radius:8px;background:none;color:var(--auth-muted);display:grid;place-items:center}.auth-card .auth-submit{margin-top:14px;min-height:52px;font-size:15px;border-radius:11px;background:var(--auth-text);color:var(--auth-card);border:0}.auth-feedback{padding:12px 14px;border:1px solid var(--auth-line);border-radius:8px;color:var(--auth-text);font-size:13px;line-height:1.8}.auth-error{color:#ef8a92}.auth-other{margin-top:26px;padding-top:20px;border-top:1px solid var(--auth-line)}.auth-other>span{display:block;color:var(--auth-muted);font-size:12px;margin-bottom:12px}.auth-other>div{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}.auth-other button{border:1px solid var(--auth-line);border-radius:7px;background:var(--auth-raised);color:var(--auth-muted);display:flex;align-items:center;justify-content:center;gap:6px;font-size:11px;padding:10px 4px;min-height:42px;opacity:1}.auth-other>small{display:block;color:var(--auth-muted);font-size:11px;margin-top:12px;line-height:1.8}.privacy-note{font-size:11px;color:var(--auth-muted);align-items:flex-start;line-height:1.8;gap:8px}.privacy-note svg{flex:none;margin-top:3px}.login-foot{color:var(--auth-muted)}@keyframes auth-enter{from{opacity:.2;transform:translateY(6px)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){.auth-card{animation:none}}@media(max-width:430px){.auth-scene{padding:16px 12px}.auth-card{padding:22px 20px;border-radius:18px}.auth-top{gap:16px;margin-bottom:22px}.auth-other>div{grid-template-columns:1fr}.auth-other button{min-height:44px}}
</style>
