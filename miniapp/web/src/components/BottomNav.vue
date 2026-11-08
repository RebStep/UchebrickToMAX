<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { Tab } from '../store';
import mapIcon from '../assets/icons/nav-map.svg?raw';
import calIcon from '../assets/icons/nav-calendar.svg?raw';
import trophyIcon from '../assets/icons/nav-trophy.svg?raw';
import gearIcon from '../assets/icons/nav-settings.svg?raw';
const tint = (svg: string) => {
  return svg.replace(/(stroke|fill)="(?!none)[^"]*"/g, '$1="currentColor"')
    .replace('preserveAspectRatio="none"', 'preserveAspectRatio="xMidYMid meet"');
};
const props = defineProps<{
  tab: Tab;
  vertical?: boolean;
  compact?: boolean;
}>();
const emit = defineEmits<{
  select: [Tab];
}>();
const items: {
  id: Tab;
  label: string;
  icon: string;
}[] = [
    { id: 'map', label: 'Карта', icon: tint(mapIcon) },
    { id: 'calendar', label: 'Календарь', icon: tint(calIcon) },
    { id: 'olympiads', label: 'Олимпиады', icon: tint(trophyIcon) },
    { id: 'settings', label: 'Настройки', icon: tint(gearIcon) },
  ];
const nav = ref<HTMLElement>();
const blob = ref<HTMLElement>();
const lens = ref(false);
const hover = ref<Tab | null>(null);
let shown = false;
let at = { x: 0, y: 0 };
const quiet = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
function spring(stiffness = 260, damping = 24) {
  const w0 = Math.sqrt(stiffness);
  const zeta = damping / (2 * Math.sqrt(stiffness));
  const wd = w0 * Math.sqrt(1 - zeta * zeta);
  const T = Math.min(1.1, 7 / (zeta * w0));
  const pts = Array.from({ length: 41 }, (_, i) => {
    const t = (i / 40) * T;
    const x = 1 - Math.exp(-zeta * w0 * t) * (Math.cos(wd * t) + (zeta * w0 / wd) * Math.sin(wd * t));
    return Math.round(x * 1000) / 1000;
  });
  pts[40] = 1;
  return { easing: `linear(${pts.join(', ')})`, duration: Math.round(T * 1000) };
}
const SPRING = spring();
function rectOf(tab: Tab) {
  const btn = nav.value?.querySelector<HTMLElement>(`[data-tab="${tab}"]`);
  if (btn) {
    return { x: btn.offsetLeft, y: btn.offsetTop, w: btn.offsetWidth, h: btn.offsetHeight, r: getComputedStyle(btn).borderRadius };
  }
  return null;
}
function moveTo(x: number, y: number, from: {
  x: number;
  y: number;
} | null) {
  const el = blob.value;
  if (!el) {
    return;
  }
  el.style.translate = `${x}px ${y}px`;
  at = { x, y };
  if (!from || quiet() || (from.x === x && from.y === y)) {
    return;
  }
  const keyframes = [{ translate: `${from.x}px ${from.y}px` }, { translate: `${x}px ${y}px` }];
  try {
    el.animate(keyframes, SPRING);
  }
  catch {
    el.animate(keyframes, { duration: 380, easing: 'cubic-bezier(0.3, 1.3, 0.5, 1)' });
  }
  const stretch = props.vertical ? ['1.06 1.16', '1.06 1.16'] : ['1.16 1.08', '1.16 1.08'];
  el.animate([{ scale: '1 1' }, { scale: stretch[0], offset: 0.3 }, { scale: stretch[1], offset: 0.55 }, { scale: '1 1' }], { duration: SPRING.duration * 0.75, easing: 'ease-out' });
  lens.value = true;
  window.setTimeout(() => {
    if (!dragging) {
      lens.value = false;
    }
  }, SPRING.duration * 0.5);
}
function place(animate: boolean) {
  const el = blob.value;
  const t = rectOf(props.tab);
  if (!el || !t) {
    return;
  }
  Object.assign(el.style, { width: `${t.w}px`, height: `${t.h}px`, borderRadius: t.r });
  moveTo(t.x, t.y, animate && shown ? at : null);
  shown = true;
}
let dragging = false;
let press: {
  id: number;
  x: number;
  dx: number;
} | null = null;
let swallowClick = false;
function onDown(e: PointerEvent) {
  if (props.vertical || e.button !== 0) {
    return;
  }
  press = { id: e.pointerId, x: e.clientX, dx: 0 };
}
function onMove(e: PointerEvent) {
  if (!press || e.pointerId !== press.id || !nav.value || !blob.value) {
    return;
  }
  if (!dragging) {
    if (Math.abs(e.clientX - press.x) < 8) {
      return;
    }
    dragging = true;
    lens.value = true;
    nav.value.setPointerCapture(e.pointerId);
    blob.value.getAnimations().forEach((a) => a.cancel());
    blob.value.animate([{ scale: '1 1' }, { scale: '1.12 1.12' }], { duration: 180, easing: 'ease-out', fill: 'forwards' });
  }
  const box = nav.value.getBoundingClientRect();
  const w = blob.value.offsetWidth;
  const pad = 5;
  const x = Math.max(pad, Math.min(box.width - pad - w - 2, e.clientX - box.left - w / 2));
  blob.value.style.translate = `${x}px ${at.y}px`;
  at = { x, y: at.y };
  hover.value = nearest(x + w / 2);
}
function onUp(e: PointerEvent) {
  if (!press || e.pointerId !== press.id) {
    return;
  }
  press = null;
  if (!dragging) {
    return;
  }
  dragging = false;
  swallowClick = true;
  window.setTimeout(() => { swallowClick = false; }, 0);
  const tab = hover.value ?? props.tab;
  hover.value = null;
  blob.value?.getAnimations().forEach((a) => a.cancel());
  blob.value?.animate([{ scale: '1.12 1.12' }, { scale: '0.97 0.97', offset: 0.6 }, { scale: '1 1' }], { duration: 320, easing: 'ease-out' });
  lens.value = false;
  if (tab !== props.tab) {
    emit('select', tab);
  }
  else {
    place(true);
  }
}
function nearest(cx: number): Tab {
  let best = items[0].id;
  let dist = Infinity;
  for (const i of items) {
    const r = rectOf(i.id);
    if (r && Math.abs(r.x + r.w / 2 - cx) < dist) {
      dist = Math.abs(r.x + r.w / 2 - cx);
      best = i.id;
    }
  }
  return best;
}
function choose(id: Tab) {
  if (swallowClick) {
    return;
  }
  emit('select', id);
}
watch(() => props.tab, () => nextTick(() => place(true)));
watch(() => [props.vertical, props.compact], () => nextTick(() => place(false)));
let ro: ResizeObserver | undefined;
onMounted(() => {
  place(false);
  ro = new ResizeObserver(() => {
    if (!dragging) {
      place(false);
    }
  });
  if (nav.value) {
    ro.observe(nav.value);
  }
});
onBeforeUnmount(() => ro?.disconnect());
</script>

<template>
  <nav ref="nav" :class="{ nav: !vertical, vertical, compact: vertical && compact }" aria-label="Основная навигация"
       @pointerdown="onDown" @pointermove="onMove" @pointerup="onUp" @pointercancel="onUp">
    <span ref="blob" class="blob" :class="{ lens }" aria-hidden="true"></span>
    <button v-for="i in items" :key="i.id" :data-tab="i.id" :class="{ on: hover ? hover === i.id : tab === i.id }" :aria-label="i.label" :aria-current="tab === i.id ? 'page' : undefined" :title="vertical && compact ? i.label : undefined" @click="choose(i.id)">
      <span class="ico" aria-hidden="true" v-html="i.icon"></span>
      <span v-if="!vertical || !compact" class="lbl">{{ i.label }}</span>
    </button>
  </nav>
</template>

<style scoped>
.nav,
.vertical {
    position: relative;
}
.blob {
    position: absolute;
    left: 0;
    top: 0;
    z-index: 0;
    pointer-events: none;
    background: var(--glass-selected);
    box-shadow:
        inset 0 1px 1px rgba(255, 255, 255, 0.24),
        inset 0 -1px 1px rgba(255, 255, 255, 0.06);
    transform-origin: center;
    will-change: translate, scale;
    transition:
        background 0.25s,
        box-shadow 0.25s,
        backdrop-filter 0.25s;
}
.blob.lens {
    background: linear-gradient(
        160deg,
        rgba(255, 255, 255, 0.22),
        rgba(255, 255, 255, 0.04) 55%,
        rgba(112, 180, 255, 0.1)
    );
    box-shadow:
        inset 0 1px 1.5px rgba(255, 255, 255, 0.55),
        inset 0 -1px 1px rgba(255, 255, 255, 0.18),
        inset 0 0 0 0.5px rgba(255, 255, 255, 0.28),
        0 6px 18px rgba(0, 0, 0, 0.22);
    backdrop-filter: brightness(1.15) saturate(1.6);
    -webkit-backdrop-filter: brightness(1.15) saturate(1.6);
}
button {
    position: relative;
    z-index: 1;
}
.nav {
    touch-action: pan-y;
    user-select: none;
    -webkit-user-select: none;
    height: 62px;
    border-radius: 999px;
    background: var(--glass-background);
    border: 1px solid var(--bar-line);
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    padding: 5px;
    gap: 0;
}
button {
    border-radius: 25px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    color: var(--soft);
    transition:
        background 0.15s,
        transform 0.15s;
}
button:active {
    transform: scale(0.96);
}
button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
}
button.on {
    color: var(--accent);
    transition: color 0.25s 0.1s;
}
button.on .ico {
    animation: ui-bounce 0.36s var(--spring);
}
.ico {
    width: 20px;
    height: 19px;
    display: grid;
    place-items: center;
    flex: none;
}
.ico :deep(path),
.ico :deep(circle),
.ico :deep(rect) {
    stroke-width: 2.2;
    vector-effect: non-scaling-stroke;
}
.ico :deep(svg) {
    width: 100%;
    height: 100%;
    display: block;
}
.lbl {
    font-weight: 600;
    font-size: 11px;
    line-height: 13px;
}
.vertical {
    display: grid;
    grid-template-columns: 1fr;
    gap: 4px;
}
.vertical button {
    flex-direction: row;
    justify-content: flex-start;
    gap: 12px;
    height: 48px;
    padding: 0 14px;
    border-radius: 24px;
}
.vertical button:not(.on):hover {
    background: var(--glass-hover);
    color: var(--ink);
}
.compact button {
    width: 48px;
    padding: 0;
    justify-self: center;
    justify-content: center;
    border-radius: 50%;
}
.vertical .ico {
    width: 20px;
    height: 19px;
}
.vertical .lbl {
    font-size: 14px;
}
</style>
