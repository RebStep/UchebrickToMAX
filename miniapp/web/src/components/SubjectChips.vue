<script setup lang="ts">
import { KIND_GROUPS } from '../store'
import { subjectColors } from '../subjects'

defineProps<{ subjects: string[]; active: string | null }>()
defineEmits<{ select: [string | null] }>()
</script>

<template>
  <div class="chips">
    <button class="chip all" :class="{ on: active === null }" @click="$emit('select', null)">Всё</button>
    <button v-for="s in subjects" :key="s" class="chip" :class="{ on: active === s }" @click="$emit('select', active === s ? null : s)">
      <i :style="{ background: KIND_GROUPS.has(s) && s !== 'Олимпиада' ? 'var(--soft)' : subjectColors(s).dot }"></i>{{ s }}
    </button>
  </div>
</template>

<style scoped>
.chips {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    scrollbar-width: none;
    padding: 0 24px;
}
.chips::-webkit-scrollbar {
    display: none;
}
.chip {
    flex: none;
    height: 25px;
    border-radius: 999px;
    background: var(--glass-background);
    color: var(--ink);
    font-weight: 500;
    font-size: 13.5px;
    padding: 0 12px;
    display: inline-flex;
    align-items: center;
    gap: 7px;
}
.chip i {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    display: block;
}
.chip.all {
    padding: 0 13px;
}
.chip.on {
    background: var(--accent);
    color: #fff;
}
.chip.on i {
    background: #fff !important;
}
</style>
