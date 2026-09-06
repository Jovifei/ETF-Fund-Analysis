<script setup lang="ts">
import { statusName } from '../lib/format'
defineProps<{ value?: string | null; label?: string }>()
</script><template><span class="badge" :class="value">{{ label ?? statusName(value) }}</span></template>
