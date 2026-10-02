<script setup lang="ts">
import { computed } from 'vue'
import type { DetailAvailability } from '../lib/types'
import { availabilityLabels, availabilityModuleOrder, availabilityReason, availabilityStatus } from '../lib/availability'

type ModuleState = { status?: string; reason_code?: string | null }

const props = defineProps<{ availability?: DetailAvailability }>()

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
        <span>{{ availabilityStatus(row.value?.status) }}</span>
        <small v-if="row.value?.reason_code">{{ availabilityReason(row.value.reason_code) }}</small>
        <small v-for="(state, horizon) in row.value?.by_horizon" :key="horizon">{{ horizon }} 日：{{ availabilityStatus(state.status) }} · {{ availabilityReason(state.reason_code) }}</small>
      </div>
    </div>
  </section>
</template>
