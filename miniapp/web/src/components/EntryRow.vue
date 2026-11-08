<script setup lang="ts">
import type { Entry } from '../calendar'
defineProps<{ entry: Entry }>()
defineEmits<{ open: [] }>()
</script>

<template>
  <button class="entry" :class="entry.tone" @click="$emit('open')">
    <span class="row"><b class="time">{{ entry.time }}</b><span class="label">{{ entry.label }}</span></span>
    <span class="title">{{ entry.title }}</span>
  </button>
</template>

<style scoped>
.entry {
    width: 100%;
    text-align: left;
    display: grid;
    gap: 7px;
    padding: 12px 14px;
    border-radius: 18px;
    background: var(--card);
    border: 1px solid transparent;
}
.row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
}
.time {
    font-weight: 600;
    font-size: 14px;
    color: var(--ink);
}
.label {
    font-weight: 500;
    font-size: 13px;
    color: var(--soft);
    text-align: right;
}
.title {
    font-weight: 500;
    font-size: 14px;
    line-height: 17px;
    color: var(--ink);
    overflow-wrap: anywhere;
}
.olympiad .label {
    color: #bc91fd;
    font-weight: 600;
}
.done .label {
    color: var(--ok);
    font-weight: 600;
}
.done .time,
.done .title {
    color: var(--soft);
}
.overdue {
    border-color: var(--danger);
}
.overdue .label {
    color: var(--danger);
    font-weight: 600;
}
.reg .label {
    color: var(--soft);
    font-weight: 600;
}
</style>
