<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import EntryRow from '../components/EntryRow.vue';
import { buildEntries, groupByDay, type Entry } from '../calendar';
import { dayKey, dateLong, dayDiff, local, MONTHS_NOM, pad, weekdayLong, weekdayShort } from '../format';
import { activeTasks, state } from '../store';
import type { Olympiad, Task } from '../types';
import chevron from '../assets/icons/chevron-left.svg';
const emit = defineEmits<{
  open: [Task];
  openOlympiad: [Olympiad];
}>();
type Mode = 'list' | 'month' | 'week';
const mode = ref<Mode>('month');
const now = new Date();
const today = local(now);
const cursor = ref({ y: today.y, m: today.m });
const selected = ref(dayKey(today));
const wide = ref(window.innerWidth >= 720);
const onResize = () => { wide.value = window.innerWidth >= 720; };
onMounted(() => window.addEventListener('resize', onResize));
onBeforeUnmount(() => window.removeEventListener('resize', onResize));
const entries = computed(() => buildEntries(activeTasks.value, now, state.olympiads));
const byDay = computed(() => new Map(groupByDay(entries.value)));
const listDays = computed(() => groupByDay(entries.value));
function titleOfDay(key: string) {
  const [y, m, d] = key.split('-').map(Number);
  const iso = new Date(Date.UTC(y, m - 1, d, 12)).toISOString();
  const l = local(iso);
  const diff = dayDiff(iso, now);
  const rel = diff === 0 ? 'Сегодня' : diff === 1 ? 'Завтра' : diff === -1 ? 'Вчера' : null;
  return { rel, text: `${weekdayLong(l.wd)}, ${dateLong(l)}`, weekday: weekdayLong(l.wd) };
}
const monthTitle = computed(() => {
  if (mode.value === 'week') {
    const days = weekDays.value.map((d) => d.key.split('-').map(Number));
    const [y1, m1] = days[0];
    const [y2, m2] = days[6];
    if (m1 === m2) {
      return `${MONTHS_NOM[m1 - 1]} ${y1}`;
    }
    if (y1 === y2) {
      return `${MONTHS_NOM[m1 - 1]} – ${MONTHS_NOM[m2 - 1]} ${y2}`;
    }
    return `${MONTHS_NOM[m1 - 1]} ${y1} – ${MONTHS_NOM[m2 - 1]} ${y2}`;
  }
  return `${MONTHS_NOM[cursor.value.m - 1]} ${cursor.value.y}`;
});
const todayTitle = computed(() => {
  const t = titleOfDay(dayKey(today));
  return `${t.weekday[0].toUpperCase()}${t.weekday.slice(1)}, ${t.text.split(', ')[1]}`;
});
const cells = computed(() => {
  const { y, m } = cursor.value;
  const first = new Date(Date.UTC(y, m - 1, 1));
  const offset = (first.getUTCDay() + 6) % 7;
  const start = new Date(Date.UTC(y, m - 1, 1 - offset));
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start.getTime() + i * 86400000);
    const key = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
    return { key, day: d.getUTCDate(), inMonth: d.getUTCMonth() + 1 === m, entries: byDay.value.get(key) ?? [] };
  });
});
const selectedTitle = computed(() => {
  const t = titleOfDay(selected.value);
  return `${t.weekday[0].toUpperCase()}${t.weekday.slice(1)}, ${t.text.split(', ')[1]}`;
});
const weekDays = computed(() => {
  const [y, m, d] = selected.value.split('-').map(Number);
  const base = new Date(Date.UTC(y, m - 1, d));
  const monday = new Date(base.getTime() - ((base.getUTCDay() + 6) % 7) * 86400000);
  return Array.from({ length: 7 }, (_, i) => {
    const dt = new Date(monday.getTime() + i * 86400000);
    const key = `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`;
    return { key, day: dt.getUTCDate(), wd: (dt.getUTCDay()), entries: byDay.value.get(key) ?? [] };
  });
});
function shift(n: number) {
  if (mode.value === 'week') {
    const [y, m, d] = selected.value.split('-').map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d + 7 * n));
    selected.value = `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`;
    cursor.value = { y: dt.getUTCFullYear(), m: dt.getUTCMonth() + 1 };
    return;
  }
  const dt = new Date(Date.UTC(cursor.value.y, cursor.value.m - 1 + n, 1));
  cursor.value = { y: dt.getUTCFullYear(), m: dt.getUTCMonth() + 1 };
}
function goToday() {
  cursor.value = { y: today.y, m: today.m };
  selected.value = dayKey(today);
}
const modes = computed<{
  id: Mode;
  label: string;
}[]>(() => {
  return [
    { id: 'month', label: 'Месяц' },
    ...(wide.value ? [{ id: 'week' as Mode, label: 'Неделя' }] : []),
    { id: 'list', label: 'Список' },
  ];
});
const todayKey = dayKey(today);
function open(e: Entry) {
  if (e.task) {
    emit('open', e.task);
  }
  else if (e.olympiad) {
    emit('openOlympiad', e.olympiad);
  }
}
</script>

<template>
  <section class="cal">
    <header v-if="mode === 'list'" class="head">
      <h2 class="today-title">{{ todayTitle }}</h2>
    </header>
    <header v-else class="head">
      <button class="round" aria-label="Назад" @click="shift(-1)"><img :src="chevron" alt="" class="flip" /></button>
      <h2>{{ monthTitle }}</h2>
      <button class="round" aria-label="Вперёд" @click="shift(1)"><img :src="chevron" alt="" /></button>
      <button class="gotoday" @click="goToday">Сегодня</button>
    </header>

    <div class="seg">
      <button v-for="m in modes" :key="m.id" :class="{ on: mode === m.id }" @click="mode = m.id">{{ m.label }}</button>
    </div>

    <div v-if="mode === 'list'" class="scroll">
      <p v-if="!listDays.length" class="empty">Дел с датами пока нет.</p>
      <template v-for="[key, list] in listDays" :key="key">
        <h3 class="day"><span :class="{ rel: titleOfDay(key).rel }">{{ titleOfDay(key).rel ?? titleOfDay(key).weekday }}</span><small>{{ titleOfDay(key).rel ? titleOfDay(key).text : dateLong(local(`${key}T12:00:00Z`)) }}</small></h3>
        <div class="list"><EntryRow v-for="e in list" :key="e.key" :entry="e" @open="open(e)" /></div>
      </template>
    </div>

    <div v-else-if="mode === 'month'" class="scroll month">
      <div class="month-cal">
      <div class="dow"><span v-for="n in [1, 2, 3, 4, 5, 6, 0]" :key="n">{{ weekdayShort(n).toUpperCase() }}</span></div>
      <div class="grid">
        <button v-for="c in cells" :key="c.key" class="cell" :class="{ dim: !c.inMonth, today: c.key === todayKey, sel: c.key === selected }" @click="selected = c.key">
          <span class="num">{{ c.day }}</span>
          <span class="dots"><i v-for="e in c.entries.slice(0, 3)" :key="e.key" :class="{ sq: e.tone === 'olympiad' }" :style="{ background: e.color }"></i></span>
        </button>
      </div>
      </div>
      <div class="month-day">
        <h3 class="sel-title">{{ selectedTitle }}</h3>
        <div class="list">
          <EntryRow v-for="e in byDay.get(selected) ?? []" :key="e.key" :entry="e" @open="open(e)" />
          <p v-if="!(byDay.get(selected) ?? []).length" class="empty">В этот день ничего нет.</p>
        </div>
      </div>
    </div>

    <div v-else class="scroll week">
      <div v-for="d in weekDays" :key="d.key" class="col" :class="{ today: d.key === todayKey }">
        <span class="wd">{{ weekdayShort(d.wd).toUpperCase() }}</span>
        <b class="wn">{{ d.day }}</b>
        <div v-for="e in d.entries" :key="e.key" class="wentry" @click="open(e)">
          <time :style="{ color: e.color }">{{ e.time }}</time>
          <span>{{ e.task?.subject ? `${e.task.subject}: ` : '' }}{{ e.title }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.cal {
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
    gap: 10px;
}
.round {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: var(--chip);
    display: grid;
    place-items: center;
    flex: none;
}
.round img {
    width: 8px;
    height: 10px;
}
.flip {
    transform: scaleX(-1);
}
h2 {
    flex: 1;
    margin: 0;
    text-align: center;
    font-weight: 600;
    font-size: 19px;
}
.head {
    min-height: 34px;
}
.today-title {
    text-align: left;
}
.gotoday {
    height: 34px;
    width: 100px;
    border-radius: 17px;
    background: var(--chip);
    font-weight: 500;
    font-size: 13.5px;
    flex: none;
}
.seg {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 1fr;
    gap: 6px;
    margin: 14px 0 6px;
}
.seg button {
    height: 36px;
    border-radius: 18px;
    background: var(--card);
    color: var(--soft);
    font-weight: 500;
    font-size: 13px;
}
.seg button.on {
    background: var(--accent);
    color: #fff;
    font-weight: 600;
}
.scroll {
    flex: 1;
    overflow-y: auto;
    padding: 4px 0 100px;
    scrollbar-width: none;
}
.scroll::-webkit-scrollbar {
    display: none;
}
.day {
    margin: 20px 0 10px;
    display: flex;
    align-items: baseline;
    gap: 8px;
    font-weight: 600;
    font-size: 21px;
    text-transform: capitalize;
}
.day .rel {
    color: var(--accent);
}
.day small {
    font-weight: 400;
    font-size: 13px;
    color: var(--soft);
    text-transform: none;
}
.list {
    display: grid;
    gap: 8px;
}
.empty {
    color: var(--soft);
    text-align: center;
    margin: 24px 0;
}
.dow {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    margin: 12px 0 6px;
    text-align: center;
    font-weight: 600;
    font-size: 10.5px;
    color: var(--soft);
}
.grid {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 4px;
}
.cell {
    aspect-ratio: 1;
    min-height: 0;
    border-radius: 13px;
    background: var(--card);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    border: 1.5px solid transparent;
}
.cell.dim {
    opacity: 0.45;
}
.cell.sel {
    border-color: var(--accent);
}
.cell .num {
    font-weight: 600;
    font-size: 14px;
}
.cell.today .num {
    color: var(--accent);
}
.dots {
    height: 6px;
    display: flex;
    gap: 3px;
    align-items: center;
}
.dots i {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    display: block;
}
.dots i.sq {
    border-radius: 1.5px;
}
.sel-title {
    margin: 20px 0 10px;
    font-weight: 600;
    font-size: 20px;
}
@media (min-width: 900px) {
    .month {
        display: grid;
        grid-template-columns: minmax(0, 520px) minmax(0, 1fr);
        gap: 28px;
        align-items: start;
    }
    .month-day .sel-title {
        margin-top: 12px;
    }
}
.week {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 8px;
    align-content: start;
    padding-top: 12px;
}
.col {
    min-width: 0;
    min-height: 330px;
    border-radius: 22px;
    background: var(--card);
    border: 1px solid var(--card-line);
    padding: 13px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.col.today {
    border-color: var(--accent);
}
.wd {
    font-weight: 600;
    font-size: 11.5px;
    color: var(--soft);
}
.wn {
    font-size: 21px;
    margin-bottom: 4px;
}
.col.today .wd,
.col.today .wn {
    color: var(--accent);
}
.wentry {
    display: grid;
    gap: 2px;
    margin-bottom: 8px;
    font-size: 12px;
    line-height: 15px;
    cursor: pointer;
    overflow-wrap: anywhere;
    min-width: 0;
}
.wentry time {
    font-weight: 600;
    font-size: 11.5px;
}
@media (min-width: 1024px) {
    .cal {
        padding: 28px max(32px, calc((100% - var(--nav-space, 264px) - 1000px) / 2)) 0
            calc(var(--nav-space, 264px) + max(32px, calc((100% - var(--nav-space, 264px) - 1000px) / 2)));
    }
    .scroll {
        padding-bottom: 40px;
    }
}
</style>
