<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '../lib/query'
import { withGeneration } from '../lib/generation'
import UsMarketsResearchCard, { type UsMarketsReadView } from './UsMarketsResearchCard.vue'
const overview = useQuery<{generation?: string|number; research_source?: string}>('/api/workspace/overview?limit=1')
const path = computed(() => {
  const v = overview.data.value
  if (!v || (v.research_source === 'local_bundle' && v.generation == null)) return null
  return withGeneration('/api/workspace/us-markets-research', v.generation)
})
const research = useQuery<UsMarketsReadView>(() => path.value)
async function reload() { await overview.reload(); await research.reload() }
</script>
<template><div data-testid="us-markets-research-section"><button class="button" @click="reload">重新读取美股研究</button><p v-if="overview.error.value" class="notice">{{overview.error.value}}</p><UsMarketsResearchCard :view="research.data.value" :error="research.error.value"/></div></template>
