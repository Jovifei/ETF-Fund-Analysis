<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import ResearchPanel from '../components/ResearchPanel.vue'
import ManualReview from '../components/ManualReview.vue'
import AISetupGuide from '../components/AISetupGuide.vue'
const route = useRoute(), daily = computed(() => route.path === '/review'), archive = computed(() => route.path === '/history'), code = computed(() => typeof route.query.code === 'string' ? route.query.code : undefined)
</script><template><div class="page-heading"><div><span class="eyebrow">EVIDENCE BEFORE OPINION</span><h1>{{ daily ? '每日复盘' : archive ? '研究档案' : 'AI 研究' }}</h1><p>{{ daily ? '盘后快照的复盘与反证，不回写盘中历史。' : archive ? '把当时的依据、后来的结果和人工审核留在同一处。' : '固定证据 → 隔离研究 → 候选校验 → 人工审核。' }}</p></div><RouterLink to="/settings" class="button">AI 与数据连接</RouterLink></div><div v-if="archive" class="notice"><span>这里保存你过去创建或导入的研究报告、输入证据与审核状态。点击任务查看报告；它不自动读取电脑文件，也不需要另建MCP。开始新研究请到“AI研究”，模型配置只在“设置与连接”维护。</span></div><ManualReview v-if="daily"/><AISetupGuide v-if="!archive"/><ResearchPanel :code="code" :kind="daily ? 'daily' : 'etf'" :archive="archive"/></template>
