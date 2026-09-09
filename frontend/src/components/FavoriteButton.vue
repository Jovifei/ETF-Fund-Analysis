<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useFavorites } from '../stores/favorites'
import { errorText } from '../lib/api'
const props = defineProps<{ code: string }>(), favorites = useFavorites(), error = ref('')
onMounted(() => { favorites.ensure().catch(e => { error.value = errorText(e) }) })
async function toggle() { error.value = ''; try { await favorites.toggle(props.code) } catch (e) { error.value = errorText(e) } }
</script>
<template><span><button type="button" class="button small favorite-star" :title="favorites.entries[code]?'取消收藏':'加入我的自选'" :aria-label="(favorites.entries[code]?'取消收藏 ':'收藏 ')+code" :aria-pressed="!!favorites.entries[code]" :disabled="!!favorites.busy[code]" @click.stop="toggle" @keydown.enter.stop>{{favorites.entries[code]?'★':'☆'}}</button><small v-if="error" role="alert">{{error}}</small></span></template>

<style scoped>.favorite-star{padding:2px 5px!important;min-width:30px;min-height:30px;font-size:19px;line-height:1;border:0;background:transparent}.favorite-star[aria-pressed=true]{color:var(--accent,#27c5d8)}</style>
