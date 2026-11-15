<script setup lang="ts">
import { num, pct, direction } from '../lib/format'
import type { Reading } from '../lib/types'
defineProps<{ readings: Reading[] }>()
</script>

<template>
  <div class="reading-grid">
    <article v-for="item in readings" :key="item.key" class="reading-card">
      <div class="reading-header">
        <strong>{{ item.label }}</strong>
        <span class="reading-key">{{ item.key }}</span>
      </div>
      <div class="reading-numbers">
        <span class="reading-val" :class="direction(item.change)">
          {{ num(item.value, item.key.startsWith('macd') ? 6 : 2) }}
        </span>
        <small class="reading-prev">
          上根 {{ num(item.previous, 2) }} · 变化 <span :class="direction(item.change)">{{ pct(item.change_ratio) }}</span>
        </small>
      </div>
      <p class="reading-desc">{{ item.explanation }}</p>
    </article>
  </div>
</template>

<style scoped>
.reading-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 12px;
}
.reading-card {
  border: 1px solid var(--border, #24292f);
  background: var(--surface, #111418);
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  transition: border-color 0.15s ease;
}
.reading-card:hover {
  border-color: var(--accent, #27c5d8);
}
.reading-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.reading-header strong {
  font-size: 13px;
  color: var(--text, #c9d1d9);
  font-weight: 600;
}
.reading-key {
  font-size: 11px;
  font-family: var(--font-mono, monospace);
  color: var(--muted, #8b949e);
  background: rgba(255, 255, 255, 0.05);
  padding: 1px 6px;
  border-radius: 4px;
}
.reading-numbers {
  display: flex;
  flex-direction: column;
  margin: 4px 0 8px;
}
.reading-val {
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}
.reading-prev {
  font-size: 11px;
  color: var(--muted, #8b949e);
  margin-top: 4px;
}
.reading-desc {
  font-size: 12px;
  line-height: 1.5;
  color: var(--muted, #8b949e);
  margin: 0;
  border-top: 1px dashed rgba(255, 255, 255, 0.08);
  padding-top: 6px;
}
</style>
