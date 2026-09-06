<script setup lang="ts">
import { ref } from 'vue'
import { ShieldCheck, ArrowRight, LoaderCircle } from 'lucide-vue-next'
import { useSession } from '../stores/session'
import { errorText } from '../lib/api'
const session = useSession(), identifier = ref(''), password = ref(''), busy = ref(false), error = ref('')
async function submit() { busy.value = true; error.value = ''; try { await session.login(identifier.value, password.value) } catch (e) { error.value = errorText(e) } finally { password.value = ''; busy.value = false } }
</script>
<template><div class="login-screen"><div class="login-brand"><span class="brand-mark">E</span> ETF Research</div><div class="login-card"><span class="eyebrow">PRIVATE RESEARCH WORKSPACE</span><h1>把判断，交还给你。</h1><p class="muted">确定性指标 · 可追溯证据 · 主观低频决策</p><form @submit.prevent="submit"><label>账户<input v-model="identifier" autocomplete="username" required placeholder="用户名或邮箱" :disabled="busy"></label><label>密码<input v-model="password" type="password" autocomplete="current-password" required :disabled="busy" placeholder="输入账户密码"></label><p v-if="error" class="error-text" role="alert">{{ error }}</p><button class="button primary full" :disabled="busy"><LoaderCircle v-if="busy" class="spin" :size="16"/>进入工作站<ArrowRight :size="16"/></button></form><p class="privacy-note"><ShieldCheck :size="16"/>私有账户会话。模型密钥不在这里填写。</p></div><p class="login-foot">研究不等于交易指令 · 不连接券商 · 不自动下单</p></div></template>
