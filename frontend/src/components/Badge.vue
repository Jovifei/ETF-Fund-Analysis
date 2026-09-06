<script setup lang="ts">
import { statusName } from '../lib/format'
defineProps<{ value?: string | null; label?: string }>()
</script><template><span class="badge" :class="{ 'badge-warning': ['mock', 'stale', 'failed', 'expired', 'unverified', 'incomplete', 'degraded'].includes(value ?? ''), 'badge-active': ['accepted', 'active', 'succeeded', 'fresh'].includes(value ?? '') }">{{ label ?? statusName(value) }}</span></template>
