<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useFavorites } from '../stores/favorites'
import { errorText } from '../lib/api'
const props = defineProps<{ code: string }>(), favorites = useFavorites(), error = ref('')
onMounted(() => { favorites.ensure().catch(e => { error.value = errorText(e) }) })
async function toggle() { error.value = ''; try { await favorites.toggle(props.code) } catch (e) { error.value = errorText(e) } }
</script>
<template><span><button type="button" class="button small" :aria-label="(favorites.entries[code]?'取消收藏 ':'收藏 ')+code" :aria-pressed="!!favorites.entries[code]" :disabled="!!favorites.busy[code]" @click.stop="toggle" @keydown.enter.stop>{{favorites.entries[code]?'★ 已收藏':'☆ 收藏'}}</button><small v-if="error" role="alert">{{error}}</small></span></template>
