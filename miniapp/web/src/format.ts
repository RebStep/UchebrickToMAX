export const TZ = 'Europe/Samara';
const WEEKDAYS_SHORT = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const WEEKDAYS_LONG = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'];
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
export const MONTHS_NOM = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
export interface Local {
  y: number;
  m: number;
  d: number;
  hh: number;
  mm: number;
  wd: number;
}
export function local(iso: string | Date, tz = TZ): Local {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: tz, year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', weekday: 'short', hourCycle: 'h23' })
    .formatToParts(typeof iso === 'string' ? new Date(iso) : iso)
    .map((p) => [p.type, p.value]));
  return {
    y: Number(parts.year), m: Number(parts.month), d: Number(parts.day), hh: Number(parts.hour), mm: Number(parts.minute),
    wd: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(parts.weekday),
  };
}
export const dayKey = (l: Local) => `${l.y}-${String(l.m).padStart(2, '0')}-${String(l.d).padStart(2, '0')}`;
export const pad = (n: number) => String(n).padStart(2, '0');
export const timeText = (iso: string) => { const l = local(iso); return `${pad(l.hh)}:${pad(l.mm)}`; };
export function toIso(date: string, time: string) {
  if (!date) {
    return null;
  }
  const [y, m, d] = date.split('-').map(Number);
  const [hh, mm] = time.split(':').map(Number);
  const guess = Date.UTC(y, m - 1, d, hh, mm);
  const shown = local(new Date(guess));
  return new Date(2 * guess - Date.UTC(shown.y, shown.m - 1, shown.d, shown.hh, shown.mm)).toISOString();
}
export const dateLong = (l: Local) => `${l.d} ${MONTHS[l.m - 1]}`;
export const weekdayShort = (wd: number) => WEEKDAYS_SHORT[wd];
export const weekdayLong = (wd: number) => WEEKDAYS_LONG[wd];
export const monthShort = (m: number) => MONTHS_SHORT[m - 1];
export function dayDiff(iso: string, now: Date): number {
  const a = local(iso);
  const b = local(now);
  return Math.round((Date.UTC(a.y, a.m - 1, a.d) - Date.UTC(b.y, b.m - 1, b.d)) / 86400000);
}
export type DueTone = 'today' | 'normal' | 'overdue' | 'done';
export function dueLabel(iso: string | null, done: boolean, now = new Date()): {
  text: string;
  tone: DueTone;
} {
  if (!iso) {
    return { text: 'без срока', tone: done ? 'done' : 'normal' };
  }
  const diff = dayDiff(iso, now);
  const l = local(iso);
  const short = `${weekdayShort(l.wd).replace(/^./, (c) => c.toUpperCase())}, ${l.d} ${monthShort(l.m)}`.replace('мая', 'мая');
  if (done) {
    return { text: short, tone: 'done' };
  }
  if (diff < 0 || (diff === 0 && new Date(iso) < now)) {
    return { text: diff === -1 ? 'Вчера' : diff === 0 ? 'Просрочено' : short, tone: 'overdue' };
  }
  if (diff === 0) {
    return { text: 'Сегодня', tone: 'today' };
  }
  if (diff === 1) {
    return { text: 'Завтра', tone: 'normal' };
  }
  return { text: short, tone: 'normal' };
}
