<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { api, errorText } from '../lib/api'
const day=ref(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai'}).format(new Date()))
const thesis=ref(''),outcome=ref(''),proposal=ref(''),revision=ref(0),saving=ref(false),loading=ref(false),message=ref(''),savedAt=ref('')
type Note={revision:number;thesis:string;outcome:string;proposal:string;saved_at:string}
let sequence=0
async function load(){ const n=++sequence;loading.value=true;message.value='';thesis.value='';outcome.value='';proposal.value='';revision.value=0;savedAt.value=''
 try{const r=await api<{note:Note|null}>('/api/workspace/review-notes/'+day.value);if(n!==sequence)return; const note=r.note;if(note){thesis.value=note.thesis;outcome.value=note.outcome;proposal.value=note.proposal;revision.value=note.revision;savedAt.value=note.saved_at}}
 catch(e){if(n===sequence)message.value=errorText(e)}finally{if(n===sequence)loading.value=false}}
async function save(){if(saving.value||loading.value)return;saving.value=true;const n=sequence
 try{const r=await api<{note:Note}>('/api/workspace/review-notes/'+day.value,{method:'PUT',body:{revision:revision.value,thesis:thesis.value,outcome:outcome.value,proposal:proposal.value}});if(n!==sequence)return;revision.value=r.note.revision;savedAt.value=r.note.saved_at;message.value='人工复盘已保存。未调用模型、未修改策略。'}catch(e){if(n===sequence)message.value=errorText(e)+'；若版本冲突，请先重新读取。'}finally{saving.value=false}}
watch(day,load,{immediate:true});onBeforeUnmount(()=>{sequence++})
</script>
<template><section class="card section" data-testid="manual-review"><div class="card-header"><h2>我的人工复盘</h2><input type="date" v-model="day" aria-label="复盘日期" :disabled="saving||loading"/></div><form class="card-body" @submit.prevent="save"><p class="small-note">记录当时判断 → 补充真实结果 → 写待验证的调整假设。保存只属于当前账户；历史日期不代表当时已经掌握今天的证据。</p><label class="form-field">当时判断与依据<textarea v-model="thesis" aria-label="当时判断与依据" required maxlength="6000" rows="4" :disabled="loading||saving"/></label><label class="form-field">后来结果与偏差<textarea v-model="outcome" aria-label="后来结果与偏差" maxlength="4000" rows="3" :disabled="loading||saving"/></label><label class="form-field">下次待验证假设<textarea v-model="proposal" aria-label="下次待验证假设" maxlength="4000" rows="3" :disabled="loading||saving"/></label><div class="toolbar"><button class="button primary" :disabled="saving||loading||!thesis.trim()">{{saving?'保存中…':'保存人工复盘'}}</button><button type="button" class="button" @click="load" :disabled="saving||loading">重新读取复盘</button><small>修订 {{revision}} · {{savedAt||'未保存'}}</small></div><p role="status">{{message}}</p></form></section></template>
<style scoped>.form-field{display:grid;gap:8px;margin:16px 0}textarea{width:100%;box-sizing:border-box;resize:vertical;font:inherit;color:inherit;background:var(--bg,#11151d);border:1px solid var(--border,#303844);border-radius:8px;padding:12px}</style>
