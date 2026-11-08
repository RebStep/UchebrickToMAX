<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { expireUndo, state, UNDO_MS } from '../store';
const emit = defineEmits<{
  undo: [];
}>();
const now = ref(Date.now());
let frame = 0;
function tick() {
  now.value = Date.now();
  expireUndo();
  if (state.undo) {
    frame = requestAnimationFrame(tick);
  }
}
watch(() => state.undo, (u) => {
  cancelAnimationFrame(frame); if (u) {
    tick();
  }
}, { immediate: true });
onBeforeUnmount(() => cancelAnimationFrame(frame));
const left = computed(() => {
  if (state.undo) {
    return Math.max(0, state.undo.until - now.value);
  }
  return 0;
});
const seconds = computed(() => Math.ceil(left.value / 1000));
const dash = computed(() => `${(left.value / UNDO_MS) * 62.83} 62.83`);
</script>

<template>
  <div v-if="state.undo" class="undo" role="status">
    <span class="timer" aria-hidden="true">
      <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" class="track" /><circle cx="12" cy="12" r="10" class="arc" :stroke-dasharray="dash" /></svg>
      <b>{{ seconds }}</b>
    </span>
    <span class="txt"><b>{{ state.undo.title }}</b><small>{{ state.undo.detail }}</small></span>
    <button class="back" @click="emit('undo')">Вернуть</button>
  </div>
</template>

<style scoped>
.undo {
    position: fixed;
    left: 50%;
    top: calc(64px + var(--safe-top));
    transform: translateX(-50%);
    z-index: 50;
    width: min(360px, calc(100vw - 32px));
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 8px 8px 12px;
    border-radius: 24px;
    background: var(--bar);
    border: 1px solid var(--bar-line);
    box-shadow: var(--glass-shadow);
}
.timer {
    position: relative;
    width: 30px;
    height: 30px;
    flex: none;
    display: grid;
    place-items: center;
}
.timer svg {
    position: absolute;
    inset: 0;
    width: 30px;
    height: 30px;
    transform: rotate(-90deg);
}
.track,
.arc {
    fill: none;
    stroke-width: 2.2;
}
.track {
    stroke: var(--chip);
}
.arc {
    stroke: var(--ok);
    stroke-linecap: round;
}
.timer b {
    font-size: 12px;
    font-weight: 600;
}
.txt {
    flex: 1;
    min-width: 0;
    display: grid;
}
.txt b {
    font-size: 13.5px;
    color: var(--ok);
}
.txt small {
    font-size: 12px;
    color: var(--soft);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.back {
    height: 38px;
    padding: 0 16px;
    border-radius: 19px;
    background: var(--accent);
    color: #fff;
    font-weight: 600;
    font-size: 13.5px;
    flex: none;
}
@media (min-width: 1024px) {
    .undo {
        left: calc(50% + var(--nav-space, 264px) / 2);
        top: auto;
        bottom: 90px;
    }
}
</style>
