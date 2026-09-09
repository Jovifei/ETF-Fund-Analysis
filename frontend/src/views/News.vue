<script setup lang="ts">
import { computed, ref } from 'vue'
import { Newspaper, RefreshCw, ExternalLink } from 'lucide-vue-next'
import { useQuery } from '../lib/query'
import { record, stamp } from '../lib/format'
import PageState from '../components/PageState.vue'
import Badge from '../components/Badge.vue'
const q = useQuery<Record<string, unknown>[]>('/api/news?limit=100'), filter = ref('')
const rows = computed(() => (q.data.value ?? []).filter(row => !filter.value || `${row.title} ${row.summary}`.includes(filter.value)))
function safeUrl(value: unknown) { try { const u = new URL(String(value)); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? u.href : undefined } catch { return undefined } }
</script><template><div class="page-heading"><div><span class="eyebrow">NEWS & CATALYSTS</span><h1>新闻线索</h1><p>新闻事实、规则分类与模型推断分开保留；抓取时间不能代替首次公开时间。</p></div><button class="button" @click="q.reload"><RefreshCw :size="14"/>重新读取</button></div><div class="card"><div class="toolbar"><label>筛选已加载线索<input v-model="filter" placeholder="主题或关键词" aria-label="筛选新闻"></label><small>只读取已保存记录 · 最多 100 条</small></div><PageState :loading="q.loading.value" :error="q.error.value" :empty="!rows.length" title="暂无匹配的新闻记录" description="在设置中更新数据，或清除筛选。没有抓到的数据不会由 AI 补造。" @retry="q.reload"><article v-for="item in rows" :key="String(item.id)" class="news-card"><div class="actions"><Newspaper :size="15"/><small>{{ item.source }} · {{ stamp(String(item.published_at ?? '')) }}</small><Badge :value="String(record(item.analysis).status ?? 'unknown')" :label="String(record(item.analysis).source ?? '规则分类 / 未标注模型')"/></div><h3>{{ item.title }}</h3><p>{{ item.summary }}</p><p v-if="Array.isArray(item.risk_flags)">{{ item.risk_flags.join('；') }}</p><a v-if="safeUrl(item.url)" :href="safeUrl(item.url)" target="_blank" rel="noopener noreferrer">查看原始来源 <ExternalLink :size="11"/></a></article></PageState></div></template>
