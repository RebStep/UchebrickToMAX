<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue';
import { sheetDock } from '../sheetDock';
const props = defineProps<{
  title: string;
  subtitle?: string;
  dockId?: string;
}>();
const emit = defineEmits<{
  close: [];
}>();
const MIN_W = 340;
const MAX_W = 760;
const desktop = sheetDock.desktop;
const read = (k: string) => {
  try {
    return localStorage.getItem(k);
  }
  catch {
    return null;
  }
};
const write = (k: string, v: string) => {
  try {
    localStorage.setItem(k, v);
  }
  catch { }
};
const clamp = (w: number) => Math.min(MAX_W, Math.max(MIN_W, w));
const panel = sheetDock.register(clamp(Number(read('uchebrik_panel_w')) || 420), props.dockId);
const width = computed(() => panel.width);
const collapsed = computed(() => panel.collapsed);
const right = computed(() => sheetDock.right(panel.id));
function fold() {
  if (panel.collapsed) {
    sheetDock.activate(panel.id);
  }
  else {
    panel.collapsed = true;
  }
}
let dragging = false;
function startDrag(e: PointerEvent) {
  if (collapsed.value) {
    return;
  }
  dragging = true;
  (e.target as HTMLElement).setPointerCapture(e.pointerId);
}
function drag(e: PointerEvent) {
  if (dragging) {
    panel.width = clamp(window.innerWidth - right.value - e.clientX);
  }
}
function endDrag() {
  if (!dragging) {
    return;
  }
  dragging = false;
  write('uchebrik_panel_w', String(width.value));
}
const onKey = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && (!desktop.value || !collapsed.value)) {
    emit('close');
  }
};
onMounted(() => window.addEventListener('keydown', onKey));
onBeforeUnmount(() => { window.removeEventListener('keydown', onKey); sheetDock.unregister(panel.id); });
</script>

<template>
  <div class="shade" :class="{ docked: desktop }" @pointerdown.self="!desktop && emit('close')">
    <section class="sheet" :class="{ folded: desktop && collapsed }" role="dialog" :aria-modal="!desktop" :aria-label="title"
             :style="desktop ? { width: (collapsed ? 58 : width) + 'px', right: right + 'px', '--folded-index': sheetDock.foldedIndex(panel.id), '--folded-count': sheetDock.foldedCount.value } : undefined">
      <template v-if="desktop">
        <div class="grip" title="Потяни, чтобы изменить ширину" @pointerdown="startDrag" @pointermove="drag" @pointerup="endDrag" @pointercancel="endDrag"></div>
        <button class="fold" :aria-label="collapsed ? 'Развернуть панель' : 'Свернуть панель'" :title="collapsed ? 'Развернуть' : 'Свернуть'" @click="fold">
          <svg viewBox="0 0 12 13" aria-hidden="true" :class="{ back: collapsed }"><path d="M2.5 1.5l6 5-6 5" /></svg>
        </button>
      </template>
      <button v-if="desktop && collapsed" class="vert" :title="title" @click="fold"><span>{{ title }}</span></button>
      <template v-else>
        <header class="head">
          <div class="titles"><h2>{{ title }}</h2><p v-if="subtitle">{{ subtitle }}</p></div>
          <button class="x" aria-label="Закрыть" @click="emit('close')"><svg viewBox="0 0 49 49" aria-hidden="true"><circle cx="24.5" cy="24.5" r="24.5" /><path d="M16 16L34 34M34 16L16 34" /></svg></button>
        </header>
        <div class="body"><slot /></div>
        <footer v-if="$slots.footer" class="foot"><slot name="footer" /></footer>
      </template>
    </section>
  </div>
</template>

<style scoped>
.shade {
    position: fixed;
    inset: 0;
    z-index: 30;
    background: var(--shade);
    display: flex;
    align-items: flex-end;
    justify-content: center;
    animation: ui-fade 0.2s ease both;
}
.sheet {
    animation: ui-rise 0.32s var(--ease-out) both;
    position: relative;
    width: 100%;
    max-width: 440px;
    max-height: 94dvh;
    display: flex;
    flex-direction: column;
    background: var(--board);
    border: 1px solid var(--bar-line);
    border-radius: 36px 36px 0 0;
    padding: 22px 16px calc(16px + var(--safe-bottom));
}
@media (min-width: 720px) {
    .shade:not(.docked) {
        align-items: center;
    }
    .shade:not(.docked) .sheet {
        border-radius: 36px;
    }
}
.head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 0 0 12px;
    position: relative;
    min-height: 49px;
}
.titles {
    flex: 1;
    text-align: center;
    padding-left: 49px;
}
h2 {
    margin: 6px 0 0;
    font-weight: 600;
    font-size: 20px;
}
.titles p {
    margin: 2px 0 0;
    font-size: 13px;
    color: var(--soft);
}
.x {
    width: 49px;
    height: 49px;
    flex: none;
}
.x svg {
    width: 49px;
    height: 49px;
    display: block;
}
.x circle {
    fill: var(--chip);
}
.x path {
    stroke: var(--soft);
    stroke-width: 3.2;
    stroke-linecap: round;
    fill: none;
}
.body {
    overflow-y: auto;
    scrollbar-width: none;
    flex: 1;
    padding-bottom: 8px;
}
.body::-webkit-scrollbar {
    display: none;
}
.foot {
    display: flex;
    gap: 8px;
    padding-top: 12px;
}

.shade.docked {
    background: transparent;
    pointer-events: none;
    animation: none;
}
.docked .sheet {
    pointer-events: auto;
    position: fixed;
    top: 12px;
    right: 12px;
    bottom: 12px;
    max-width: none;
    max-height: none;
    border-radius: 28px;
    padding: 22px 18px 18px 22px;
    box-shadow: var(--panel-shadow);
    animation: panel-in 0.32s var(--ease-out) both;
    transition:
        width 0.22s var(--ease-out),
        right 0.22s var(--ease-out);
}
.docked .titles {
    text-align: left;
    padding-left: 0;
}
.grip {
    position: absolute;
    left: -6px;
    top: 28px;
    bottom: 28px;
    width: 12px;
    cursor: ew-resize;
    z-index: 2;
}
.grip::after {
    content: "";
    position: absolute;
    left: 4px;
    top: 50%;
    width: 4px;
    height: 44px;
    margin-top: -22px;
    border-radius: 2px;
    background: var(--bar-line);
    transition: background 0.15s;
}
.grip:hover::after {
    background: var(--accent);
}
.fold {
    position: absolute;
    right: 74px;
    top: 28px;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    z-index: 3;
    color: var(--soft);
    transition:
        background 0.15s,
        color 0.15s;
}
.fold:hover {
    background: var(--chip);
    color: var(--ink);
}
.fold svg {
    width: 11px;
    height: 12px;
    fill: none;
    stroke: currentColor;
    stroke-width: 2.6;
    stroke-linecap: round;
    stroke-linejoin: round;
}
.fold svg.back {
    transform: scaleX(-1);
}
.docked .sheet.folded {
    --folded-height: min(208px, calc((100dvh - (var(--folded-count) + 1) * 12px) / var(--folded-count)));
    top: calc(12px + var(--folded-index) * (var(--folded-height) + 12px));
    padding: 0;
    align-items: center;
    overflow: hidden;
    bottom: auto;
    height: var(--folded-height);
}
.folded .fold {
    right: auto;
    left: 11px;
    top: 12px;
    background: var(--chip);
}
.vert {
    position: absolute;
    inset: 58px 0 12px;
    width: 100%;
    display: grid;
    place-items: center;
    overflow: hidden;
    font-weight: 600;
    font-size: 14px;
    color: var(--soft);
}
.vert span {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    line-height: 20px;
    max-height: 100%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
@keyframes panel-in {
    from {
        opacity: 0;
        translate: 40px 0;
    }
}
</style>
