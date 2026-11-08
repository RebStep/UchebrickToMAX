<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import { state } from '../store';
import { dayDiff, local, dateLong, MONTHS_NOM } from '../format';
import { subjectColors } from '../subjects';
import type { Olympiad } from '../types';
import okIcon from '../assets/icons/check-green.svg';
const emit = defineEmits<{
  add: [];
  open: [Olympiad];
  register: [Olympiad];
}>();
const now = new Date();
const filter = ref<string | null>(null);
const subjectList = computed(() => [...new Set(state.olympiads.map((o) => o.subject).filter((s): s is string => !!s))]);
const shown = computed(() => state.olympiads.filter((o) => !filter.value || o.subject === filter.value));
const registration = computed(() => {
  return shown.value.filter((o) => o.reg_deadline && dayDiff(o.reg_deadline, now) >= 0).sort((a, b) => a.reg_deadline!.localeCompare(b.reg_deadline!));
});
function regLine(o: Olympiad) {
  const left = dayDiff(o.reg_deadline!, now);
  if (o.reg_opens && dayDiff(o.reg_opens, now) > 0) {
    return { text: `с ${dateLong(local(o.reg_opens))}`, urgent: false };
  }
  const word = left === 0 ? 'сегодня последний день' : `осталось ${left} ${left === 1 ? 'день' : left < 5 ? 'дня' : 'дней'}`;
  return { text: `до ${dateLong(local(o.reg_deadline!))} · ${word}`, urgent: left <= 7 };
}
const start = new Date(Date.UTC(local(now).y, local(now).m - 1, 1));
const MONTHS_SHOWN = 5;
const end = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + MONTHS_SHOWN, 1));
const span = end.getTime() - start.getTime();
const monthLabels = Array.from({ length: MONTHS_SHOWN }, (_, i) => {
  const d = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + i, 1));
  return { name: MONTHS_NOM[d.getUTCMonth()].slice(0, 3).toUpperCase(), left: ((d.getTime() - start.getTime()) / span) * 100 };
});
const todayLeft = ((Date.UTC(local(now).y, local(now).m - 1, local(now).d) - start.getTime()) / span) * 100;
const fmt = (iso: string) => { const l = local(iso); return `${l.d}.${String(l.m).padStart(2, '0')}`; };
const rows = computed(() => {
  return shown.value
    .filter((o) => o.tours.some((t) => t.starts_at || t.deadline))
    .map((o) => {
      return {
        o,
        color: subjectColors(o.subject).dot,
        bars: placeLabels(o.tours.filter((t) => t.starts_at || t.deadline).map((t) => {
          const a = new Date(t.starts_at ?? t.deadline!).getTime();
          const b = new Date(t.deadline ?? t.starts_at!).getTime();
          const left = Math.max(0, ((a - start.getTime()) / span) * 100);
          const width = Math.max(0, Math.min(100, ((b - start.getTime()) / span) * 100) - left);
          return { key: t.id, t, left, width, point: a === b, from: fmt(t.starts_at ?? t.deadline!), to: fmt(t.deadline ?? t.starts_at!) };
        })),
      };
    });
});
const trackW = ref(600);
let ro: ResizeObserver | undefined;
const watchTrack = (el: unknown) => {
  if (!(el instanceof HTMLElement) || ro) {
    return;
  }
  ro = new ResizeObserver(([e]) => { trackW.value = e.contentRect.width; });
  ro.observe(el);
};
onBeforeUnmount(() => ro?.disconnect());
const textPx = (s: string) => s.length * 6.6 + 4;
type Bar = {
  key: number;
  t: Olympiad['tours'][number];
  left: number;
  width: number;
  point: boolean;
  from: string;
  to: string;
};
type Label = {
  text: string;
  style: Record<string, string>;
  over?: boolean;
};
function placeLabels(list: Bar[]) {
  const W = trackW.value;
  const px = (pct: number) => (pct / 100) * W;
  const gap = 6;
  const sorted = [...list].sort((x, y) => x.left - y.left);
  let busyTill = 0;
  return sorted.map((b, i) => {
    const startPx = px(b.left);
    const endPx = px(b.left + b.width) + (b.point ? 13 : 0);
    const nextStart = i + 1 < sorted.length ? px(sorted[i + 1].left) - gap : W;
    const fitsRight = (text: string) => endPx + gap + textPx(text) <= nextStart;
    const fitsLeft = (text: string) => startPx - gap - textPx(text) >= busyTill;
    const right = (text: string, over = false): Label => ({ text, style: { left: `${endPx + gap}px` }, ...(over ? { over } : {}) });
    const left = (text: string): Label => ({ text, style: { right: `${W - startPx + gap}px` } });
    const done = (labels: Label[], inside = false) => {
      const r = labels.find((l) => 'left' in l.style);
      busyTill = r ? endPx + gap + textPx(r.text) : endPx;
      return { ...b, inside, labels };
    };
    if (b.point) {
      if (fitsRight(b.to)) {
        return done([right(b.to)]);
      }
      if (fitsLeft(b.to)) {
        return done([left(b.to)]);
      }
      return done([right(b.to, true)]);
    }
    if (endPx - startPx >= textPx(b.from) + textPx(b.to) + 22) {
      return done([], true);
    }
    if (fitsLeft(b.from) && fitsRight(b.to)) {
      return done([left(b.from), right(b.to)]);
    }
    const full = `${b.from}–${b.to}`;
    const short = `до ${b.to}`;
    if (fitsRight(full)) {
      return done([right(full)]);
    }
    if (fitsLeft(full)) {
      return done([left(full)]);
    }
    if (fitsRight(short)) {
      return done([right(short)]);
    }
    if (fitsLeft(short)) {
      return done([left(short)]);
    }
    return done([right(short, true)]);
  });
}
const undated = computed(() => shown.value.filter((o) => !o.tours.some((t) => t.starts_at || t.deadline)));
</script>

<template>
  <section class="oly">
    <header class="head"><h1>Олимпиады</h1><button class="add" aria-label="Добавить олимпиаду" title="Добавить олимпиаду" @click="emit('add')"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg></button></header>
    <div class="chips">
      <button class="chip" :class="{ on: !filter }" @click="filter = null">Все</button>
      <button v-for="s in subjectList" :key="s" class="chip" :class="{ on: filter === s }" @click="filter = filter === s ? null : s">{{ s }}</button>
    </div>
    <div class="scroll">
      <h4 v-if="registration.length">Регистрация</h4>
      <button v-for="o in registration" :key="o.id" class="reg" :class="{ urgent: regLine(o).urgent && !o.registered }" @click="emit('open', o)">
        <span class="txt"><b>{{ o.name }}</b><small :class="{ red: regLine(o).urgent }">{{ regLine(o).text }}</small></span>
        <span class="check" :class="{ on: o.registered }" @click.stop="emit('register', o)"><img :src="okIcon" alt="" /></span>
      </button>

      <template v-if="rows.length">
        <h4>Идут сейчас</h4>
        <div class="gantt">
          <div class="axis"><span v-for="m in monthLabels" :key="m.name" :style="{ left: m.left + '%' }">{{ m.name }}</span></div>
          <div class="lines" aria-hidden="true">
            <i v-for="m in monthLabels.slice(1)" :key="m.name" class="month" :style="{ left: m.left + '%' }"></i>
            <i class="today" :style="{ left: todayLeft + '%' }" title="Сегодня"></i>
          </div>
          <div v-for="r in rows" :key="r.o.id" class="line" @click="emit('open', r.o)">
            <span class="name" :class="{ dim: r.bars.every((b) => b.t.done) }">{{ r.o.name }}</span>
            <div :ref="watchTrack" class="track">
              <template v-for="b in r.bars" :key="b.key">
                <span v-if="b.point" class="dot" :style="{ left: b.left + '%', background: r.color }"></span>
                <span v-else class="bar" :class="{ done: b.t.done }" :style="{ left: b.left + '%', width: b.width + '%', background: r.color }">
                  <template v-if="b.inside"><em>{{ b.from }}</em><em>{{ b.to }}</em></template>
                </span>
                <span v-for="(l, j) in b.labels" :key="j" class="pt" :class="{ over: l.over }" :style="l.style">{{ l.text }}</span>
              </template>
            </div>
          </div>
        </div>
      </template>

      <button v-for="o in undated" :key="o.id" class="undated" @click="emit('open', o)"><b>{{ o.name }}</b><small>Нажми, чтобы указать даты</small></button>
    </div>
  </section>
</template>

<style scoped>
.oly {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    padding: calc(12px + var(--safe-top)) 16px 0;
    background: var(--screen);
}
.head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}
h1 {
    margin: 0;
    font-weight: 600;
    font-size: 30px;
}
.add {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    flex: none;
    display: grid;
    place-items: center;
    background: var(--action-fill, var(--accent));
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 0.18);
    box-shadow:
        inset 0 1px 1px rgba(255, 255, 255, 0.22),
        var(--glass-shadow);
    transition:
        transform 0.2s var(--ease-out),
        filter 0.2s;
}
.add svg {
    width: 24px;
    height: 24px;
    fill: none;
    stroke: currentColor;
    stroke-width: 2.5;
    stroke-linecap: round;
}
.add:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
}
.add:active {
    transform: scale(0.94);
}
@media (hover: hover) {
    .add:hover {
        filter: brightness(1.1);
    }
}
.chips {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    scrollbar-width: none;
    margin-top: 14px;
}
.chip {
    flex: none;
    height: 25px;
    padding: 0 13px;
    border-radius: 17px;
    background: var(--chip);
    font-weight: 500;
    font-size: 13.5px;
    color: var(--ink);
}
.chip.on {
    background: var(--accent);
    color: #fff;
}
.scroll {
    flex: 1;
    overflow-y: auto;
    scrollbar-width: none;
    padding-bottom: 100px;
}
.scroll::-webkit-scrollbar {
    display: none;
}
h4 {
    margin: 14px 0 8px;
    font-weight: 500;
    font-size: 12px;
    color: var(--soft);
}
.reg {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    text-align: left;
    padding: 12px 14px;
    margin-bottom: 8px;
    border-radius: 18px;
    background: var(--card);
    border: 1.5px solid transparent;
}
.reg.urgent {
    border-color: var(--danger);
}
.txt {
    display: grid;
    gap: 3px;
    min-width: 0;
}
.txt b {
    font-weight: 600;
    font-size: 15px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.txt small {
    font-size: 11.5px;
    color: var(--soft);
}
.txt small.red {
    color: var(--danger);
    font-weight: 600;
}
.check {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: var(--chip);
    display: grid;
    place-items: center;
    flex: none;
}
.check img {
    width: 13px;
    height: 14px;
    opacity: 0.35;
}
.check.on img {
    opacity: 1;
    filter: hue-rotate(0deg);
}
.check.on {
    background: color-mix(in srgb, var(--ok) 20%, var(--card));
}

.check.on img {
    filter: invert(61%) sepia(58%) saturate(500%) hue-rotate(80deg);
}
.gantt {
    position: relative;
    padding-top: 22px;
}
.axis {
    position: absolute;
    left: 130px;
    right: 0;
    top: 0;
    height: 20px;
    font-weight: 600;
    font-size: 10.5px;
    color: var(--soft);
    border-bottom: 1px solid var(--card-line);
}
.axis span {
    position: absolute;
    top: 2px;
    padding-left: 5px;
}
.lines {
    position: absolute;
    left: 130px;
    right: 0;
    top: 0;
    bottom: 0;
    pointer-events: none;
}
.lines i {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 1px;
}
.lines .month {
    background: var(--card-line);
}
.lines .today {
    top: 20px;
    width: 2px;
    margin-left: -1px;
    background: var(--accent);
    border-radius: 1px;
}
.lines .today::before {
    content: "";
    position: absolute;
    top: -4px;
    left: -3px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent);
}
.line {
    display: flex;
    align-items: center;
    height: 25px;
    border-bottom: 1px solid var(--card);
    cursor: pointer;
}
.name {
    width: 130px;
    flex: none;
    font-weight: 600;
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding-right: 8px;
}
.name.dim {
    color: var(--soft);
}
.track {
    position: relative;
    flex: 1;
    height: 100%;
}
.bar {
    position: absolute;
    top: 3px;
    height: 19px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 7px;
    font-weight: 600;
    font-size: 10.5px;
    color: #fff;
    overflow: hidden;
    white-space: nowrap;
}
.bar em {
    font-style: normal;
}
.bar.done {
    opacity: 0.45;
}
.dot {
    position: absolute;
    top: 6px;
    width: 13px;
    height: 13px;
    border-radius: 50%;
}
.pt {
    position: absolute;
    top: 5px;
    font-weight: 600;
    font-size: 11px;
    white-space: nowrap;
}
.pt.over {
    z-index: 1;
    padding: 0 4px;
    margin-left: -4px;
    border-radius: 6px;
    background: var(--screen);
}
.undated {
    width: 100%;
    text-align: left;
    margin-top: 20px;
    padding: 14px;
    border-radius: 18px;
    background: var(--card);
    display: grid;
    gap: 4px;
}
.undated b {
    font-size: 14px;
}
.undated small {
    color: var(--soft);
    font-size: 12px;
}
@media (min-width: 1024px) {
    .oly {
        padding: 28px max(32px, calc((100% - var(--nav-space, 264px) - 1000px) / 2)) 0
            calc(var(--nav-space, 264px) + max(32px, calc((100% - var(--nav-space, 264px) - 1000px) / 2)));
    }
    .scroll {
        padding-bottom: 40px;
    }
}
</style>

<style>
:root[data-theme="light"] .reg .check:not(.on) img {
    filter: brightness(0);
    opacity: 0.28;
}
</style>
