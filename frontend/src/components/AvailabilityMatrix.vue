<script setup lang="ts">
import { computed } from 'vue'
import { availabilityLabels, availabilityModuleOrder, availabilityReason } from '../lib/availability'

type ModuleState = { status?: string; reason_code?: string | null }

const props = defineProps<{ availability?: Record<string, ModuleState> }>()

const rows = computed(() => availabilityModuleOrder.map((key) => ({
  key,
  label: availabilityLabels[key],
  value: props.availability?.[key],
})))
</script>

<template>
  <section class="card" data-testid="availability-matrix">
    <div class="card-header">
      <h2>研究可用性</h2>
    </div>
    <div class="card-body">
      <div v-for="row in rows" :key="row.key" class="availability-row">
        <strong>{{ row.label }}</strong>
        <span>{{ row.value?.status ?? '未提供状态' }}</span>
        <small v-if="row.value?.reason_code">{{ availabilityReason(row.value.reason_code) }}</small>
      </div>
    </div>
  </section>
</template>
