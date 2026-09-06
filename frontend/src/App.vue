<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { LayoutDashboard, ChartCandlestick, Star, BriefcaseBusiness, Sparkles, BookOpen, Newspaper, Sigma, Settings, LogOut, PanelLeft, Menu, X, ChevronRight, UserRound, CircleHelp, Clock3 } from 'lucide-vue-next'
import GlobalSearch from './components/GlobalSearch.vue'
import Login from './components/Login.vue'
import { useSession } from './stores/session'
import { api, errorText } from './lib/api'
import type { Status } from './lib/types'
import { olderThan } from './lib/format'
const session = useSession(), route = useRoute(), sidebar = ref('expanded'), mobileOpen = ref(false), status = ref<Status | null>(null), notice = ref(''), reduced = ref(false)
const groups = [
  { title: '日常研究', items: [{ path: '/', label: '市场总览', icon: LayoutDashboard }, { path: '/analysis', label: 'ETF 分析', icon: ChartCandlestick }, { path: '/watchlist', label: '我的自选', icon: Star }, { path: '/holdings', label: '我的持仓', icon: BriefcaseBusiness }] },
  { title: '证据与分析', items: [{ path: '/ai', label: 'AI 研究', icon: Sparkles }, { path: '/review', label: '每日复盘', icon: BookOpen }, { path: '/research/news', label: '新闻线索', icon: Newspaper }, { path: '/factors', label: '因子研究', icon: Sigma }, { path: '/history', label: '研究档案', icon: Clock3 }] },
]
function selected(path: string) { return path === '/' ? ['/', '/boards', '/decision/1430'].includes(route.path) : path === '/analysis' ? route.path === path || route.path.startsWith('/etf/') : route.path === path }
function toggleSidebar() { sidebar.value = sidebar.value === 'expanded' ? 'compact' : sidebar.value === 'compact' ? 'hidden' : 'expanded'; try { localStorage.setItem('etf-workspace-sidebar', sidebar.value) } catch {} }
async function readStatus() { if (!session.authenticated) return; try { status.value = await api<Status>('/api/workspace/status') } catch { status.value = null } }
async function logout() { try { await session.logout(); mobileOpen.value = false; status.value = null } catch (e) { notice.value = errorText(e) } }
function applyPreferences(event: Event) {
  const value = (event as CustomEvent).detail as { sidebar?: string; reduce_motion?: boolean }
  if (value.sidebar && ['expanded', 'compact', 'hidden'].includes(value.sidebar)) sidebar.value = value.sidebar
  reduced.value = value.reduce_motion === true
}
function expire() { session.clear(); status.value = null; mobileOpen.value = false }
function escape(event: KeyboardEvent) { if (event.key === 'Escape') mobileOpen.value = false }
watch(() => route.fullPath, () => { mobileOpen.value = false; notice.value = '' })
watch(() => session.authenticated, value => { if (value) void readStatus() })
let timer: ReturnType<typeof setInterval> | undefined
onMounted(async () => { try { const saved = localStorage.getItem('etf-workspace-sidebar'); if (saved && ['expanded', 'compact', 'hidden'].includes(saved)) sidebar.value = saved } catch {} window.addEventListener('workspace-preferences', applyPreferences); window.addEventListener('session-expired', expire); window.addEventListener('keydown', escape); await session.load(); await readStatus(); timer = setInterval(() => { if (!document.hidden) void readStatus() }, 60000) })
onBeforeUnmount(() => { clearInterval(timer); window.removeEventListener('workspace-preferences', applyPreferences); window.removeEventListener('session-expired', expire); window.removeEventListener('keydown', escape) })
</script>
<template>
<div v-if="!session.ready" class="boot-state" role="status">正在连接私有研究工作站…</div>
<Login v-else-if="!session.authenticated"/>
<div v-else class="workspace" :class="[`sidebar-${sidebar}`, { 'mobile-open': mobileOpen, 'reduce-motion': reduced }]" :key="session.generation">
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <button v-if="mobileOpen" class="sidebar-backdrop" aria-label="关闭导航" @click="mobileOpen = false"/>
  <aside class="sidebar" aria-label="主要导航">
    <RouterLink to="/" class="brand"><span class="brand-mark">E</span><span class="brand-name">ETF<span>Research</span><small>你的低频研究工作站</small></span></RouterLink>
    <button class="icon-button mobile-close" aria-label="关闭导航" @click="mobileOpen = false"><X :size="20"/></button>
    <nav class="nav-scroll"><div v-for="group in groups" :key="group.title" class="nav-group"><p class="nav-label">{{ group.title }}</p><RouterLink v-for="item in group.items" :key="item.path" :to="item.path" class="nav-item" :class="{ active: selected(item.path) }" :title="item.label" :aria-current="selected(item.path) ? 'page' : undefined"><component :is="item.icon" :size="19"/><span>{{ item.label }}</span><ChevronRight v-if="selected(item.path)" class="nav-chevron" :size="13"/></RouterLink></div><div class="sidebar-note"><span class="signal-dot"/>不连接券商 · 不自动下单</div></nav>
    <div class="sidebar-bottom"><RouterLink to="/settings" class="connection-mini"><span class="signal-dot" :class="{ warning: !status || olderThan(status.worker?.last_seen_at, 90) }"/><span>{{ status?.market_provider === 'mock' ? '演示数据模式' : '数据与 AI 连接' }}</span><ChevronRight :size="14"/></RouterLink><RouterLink to="/profile" class="account-card" title="个人中心"><div class="avatar">{{ (session.identifier ?? '本').slice(0, 1).toUpperCase() }}</div><div class="account-text"><strong>{{ session.identifier ?? '本地单用户' }}</strong><small>{{ session.role === 'admin' ? '管理员' : session.role ? '个人研究空间' : '无认证演示 / 请勿公网开放' }}</small></div></RouterLink><div class="account-actions"><RouterLink to="/settings" title="设置"><Settings :size="17"/><span>设置</span></RouterLink><button @click="logout" title="退出登录"><LogOut :size="16"/><span>退出</span></button></div></div>
  </aside>
  <div class="main-shell"><header class="topbar"><button class="icon-button desktop-menu" aria-label="切换侧栏形态" @click="toggleSidebar"><PanelLeft :size="20"/></button><button class="icon-button mobile-menu" aria-label="打开导航" @click="mobileOpen = true"><Menu :size="22"/></button><GlobalSearch/><div class="topbar-status"><span class="signal-dot"/>研究模式<span class="header-divider"/><RouterLink to="/profile" class="icon-button" aria-label="个人中心"><UserRound :size="18"/></RouterLink></div></header>
  <main id="main-content" class="main-content" tabindex="-1"><div v-if="status?.market_provider === 'mock'" class="notice warning-notice"><CircleHelp :size="16"/><span>当前为演示数据，所有页面仅用于功能验收，不可作为真实市场判断。</span></div><div v-if="notice" class="notice" role="alert">{{ notice }}</div><RouterView :key="route.path"/></main>
  <footer class="workspace-footer"><span>ETF Research · {{ status?.workspace_version ?? 'workspace' }}</span><span>Asia/Shanghai · 研究非投资指令 · 历史 14:30 回测尚未取得资格</span></footer></div>
</div>
</template>
