<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ShieldCheck, Eye, EyeOff } from 'lucide-vue-next'
import { useSession } from '../stores/session'
import { api, errorText } from '../lib/api'
import { useQuery } from '../lib/query'
const session = useSession(), route = useRoute(), identifier = ref(''), password = ref(''), confirmation = ref(''), email = ref(''), invite = ref(''), show = ref(false), busy = ref(false), error = ref('')
const registration = computed(() => route.path === '/register')
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
<template><div class="login-screen"><div class="login-brand"><span class="brand-mark">E</span> ETF Research</div><div class="login-card">
  <span class="eyebrow">PRIVATE RESEARCH WORKSPACE</span><h1>{{ registration?'创建账户':'账户登录' }}</h1><p class="muted">登录后进入市场总览，原版 ETF 决策快照就在首页。</p>
  <nav class="section-tabs" aria-label="账户入口"><RouterLink :to="{path:'/login',query:route.query}" :class="{active:!registration}">账户登录</RouterLink><RouterLink :to="{path:'/register',query:route.query}" :class="{active:registration}">创建账户</RouterLink></nav>
  <p v-if="capabilities.error.value" role="alert">无法读取注册状态，请重试。<button class="text-button" @click="capabilities.reload">重试</button></p>
  <div v-if="registration && capabilities.data.value && !capabilities.data.value.registration_enabled" class="notice">本系统采用私有账户。当前未开放邀请注册，请管理员在“个人中心 → 用户管理”创建成员账户。首次安装请在部署终端初始化管理员；不能通过普通注册获得管理员权限。</div>
  <form v-else @submit.prevent="submit"><label>账户<input v-model="identifier" autocomplete="username" maxlength="128" required placeholder="用户名或邮箱" :disabled="busy"></label>
    <label v-if="registration">邮箱（可选）<input v-model="email" type="email" autocomplete="email" maxlength="320" :disabled="busy"></label>
    <label>密码<div class="password-field"><input v-model="password" :type="show?'text':'password'" :autocomplete="registration?'new-password':'current-password'" :minlength="registration?6:undefined" maxlength="1024" required :disabled="busy" placeholder="输入账户密码"><button type="button" class="icon-button" :aria-label="show?'隐藏密码':'显示密码'" :aria-pressed="show" @click="show=!show"><EyeOff v-if="show" :size="18"/><Eye v-else :size="18"/></button></div></label>
    <label v-if="registration">确认密码<input v-model="confirmation" type="password" autocomplete="new-password" maxlength="1024" required :disabled="busy"></label>
    <label v-if="registration">邀请码<input v-model="invite" type="password" autocomplete="off" maxlength="128" required :disabled="busy"></label>
    <p v-if="error" class="error-text" role="alert">{{ error }}</p><button class="button primary full" :disabled="busy || (registration && !capabilities.data.value?.registration_enabled)">{{ busy?'正在验证…':registration?'创建账户并进入总览':'登录并进入总览' }}</button></form>
  <p class="privacy-note"><ShieldCheck :size="16"/>密码默认隐藏，不保存在浏览器存储；这里不填写模型密钥。</p>
</div><p class="login-foot">不连接券商 · 不自动下单</p></div></template>
<style scoped>.password-field{display:flex;align-items:center;gap:6px}.password-field input{min-width:0;flex:1}.section-tabs{margin:16px 0}.login-card{max-height:90vh;overflow:auto}.login-screen{min-height:100dvh}</style>
