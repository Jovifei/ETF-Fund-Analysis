<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import ResearchPanel from '../components/ResearchPanel.vue'
const route = useRoute(), daily = computed(() => route.path === '/review'), archive = computed(() => route.path === '/history'), code = computed(() => typeof route.query.code === 'string' ? route.query.code : undefined)
</script><template><div class="page-heading"><div><span class="eyebrow">EVIDENCE BEFORE OPINION</span><h1>{{ daily ? '每日复盘' : archive ? '研究档案' : 'AI 研究' }}</h1><p>{{ daily ? '盘后快照的复盘与反证，不回写盘中历史。' : archive ? '把当时的依据、后来的结果和人工审核留在同一处。' : '固定证据 → 隔离研究 → 候选校验 → 人工审核。' }}</p></div><RouterLink to="/settings" class="button">AI 与数据连接</RouterLink></div><ResearchPanel :code="code" :kind="daily ? 'daily' : 'etf'" :archive="archive"/></template>
