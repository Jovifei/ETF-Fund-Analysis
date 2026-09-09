<script setup lang="ts">
import { ref } from 'vue'
import { api, errorText } from '../lib/api'
import { stamp } from '../lib/format'
import type { ResearchJob } from '../lib/types'
type Preview = { packet_hash: string; ts_code?: string; producer_version: string; model: string; upstream_status: string; source_as_of: string; artifacts: {name: string;sha256: string;bytes: number}[]; warnings: string[] }
const emit = defineEmits<{ imported: [job: ResearchJob] }>()
const packet = ref<unknown>(null), preview = ref<Preview | null>(null), consent = ref(false), busy = ref(false), error = ref('')
async function choose(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  input.value = ''; packet.value = preview.value = null; consent.value = false; error.value = ''
  if (!file || busy.value) return
  busy.value = true
  try {
    if (file.size > 1_000_000) throw new Error('文件超过 1 MB 上限')
    const value: unknown = JSON.parse(await file.text())
    preview.value = await api<Preview>('/api/workspace/external-research/preview', {method:'POST',body:value})
    packet.value = value
  } catch (e) { error.value = e instanceof SyntaxError ? '请选择 export_vibe.py 生成的 JSON 包。' : errorText(e) }
  finally { busy.value = false }
}
async function confirm() {
  if (!preview.value || !consent.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    const data = await api<{job: ResearchJob}>('/api/workspace/external-research/import', {method:'POST',body:{packet:packet.value,packet_hash:preview.value.packet_hash,confirm_public_data:true}})
    packet.value = preview.value = null; consent.value = false; emit('imported',data.job)
  } catch (e) { error.value = errorText(e) } finally { busy.value = false }
}
</script>
<template>
<details class="card section external-import"><summary class="card-header">导入 Vibe 原生研究产物 <small>独立归档 · 先预览再确认 · 不调用模型</small></summary>
<div class="card-body"><p>使用随包的 <code>bridge/export_vibe.py</code> 从已完成的 Vibe 运行目录导出五种允许文件。不是把整份 .local 上传，也不会修改现有任务的冻结证据。</p>
<label class="button"><input type="file" accept="application/json,.json" :disabled="busy" aria-label="选择外部研究包" @change="choose">选择 external-research.json</label>
<p v-if="error" class="form-error" role="alert">{{error}}</p>
<div v-if="preview" data-testid="external-preview"><dl class="details-list"><dt>标的 / 范围</dt><dd>{{preview.ts_code ?? '市场复盘'}}</dd><dt>上游状态</dt><dd>{{preview.upstream_status}}（上报信息，未认证）</dd><dt>证据时间</dt><dd>{{stamp(preview.source_as_of)}}</dd><dt>版本 / 模型</dt><dd>{{preview.producer_version}} / {{preview.model}}</dd></dl>
<ul><li v-for="file in preview.artifacts" :key="file.name">{{file.name}} · {{file.bytes}} bytes</li></ul>
<p v-for="warning in preview.warnings" :key="warning" class="muted">{{warning}}</p>
<label class="checkbox-label"><input v-model="consent" type="checkbox">我已检查文件，不含登录凭据、账户信息或个人持仓隐私，并同意仅作为未验证候选导入。</label>
<button class="button primary" :disabled="busy || !consent" @click="confirm">确认导入外部候选</button>
</div></div></details>
</template>
