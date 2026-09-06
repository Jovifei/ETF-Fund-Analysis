<script setup lang="ts">
import { AlertTriangle, LoaderCircle, Database } from 'lucide-vue-next'
defineProps<{ loading?: boolean; error?: string; empty?: boolean; title?: string; description?: string }>()
defineEmits<{ retry: [] }>()
</script>
<template>
  <div v-if="loading" class="state" role="status" aria-live="polite"><LoaderCircle class="spin" :size="26"/><h3>正在读取研究数据</h3><p>只读取已保存的快照，不在页面等待外部采集。</p></div>
  <div v-else-if="error" class="state error" role="alert"><AlertTriangle :size="28"/><h3>暂时无法载入</h3><p>{{ error }}</p><button class="button" @click="$emit('retry')">重新读取</button></div>
  <div v-else-if="empty" class="state"><Database :size="28"/><h3>{{ title ?? '还没有可用数据' }}</h3><p>{{ description ?? '请先完成数据同步。缺失的数据不会被演示行情替代。' }}</p><slot name="action"/></div>
  <slot v-else/>
</template>
