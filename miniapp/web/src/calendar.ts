import { dayKey, local, timeText, dateLong } from './format';
import { subjectColors } from './subjects';
import type { Olympiad, Task } from './types';
export type EntryTone = 'plain' | 'olympiad' | 'done' | 'overdue' | 'reg';
export interface Entry {
  key: string;
  at: string;
  day: string;
  time: string;
  title: string;
  label: string;
  tone: EntryTone;
  color: string;
  task?: Task;
  olympiad?: Olympiad;
}
function timeRange(at: string, duration?: number | null) {
  if (!duration) {
    return timeText(at);
  }
  return `${timeText(at)}–${timeText(new Date(new Date(at).getTime() + duration * 60000).toISOString())}`;
}
export function buildEntries(tasks: Task[], now = new Date(), olympiads: Olympiad[] = []): Entry[] {
  const out: Entry[] = [];
  for (const t of tasks) {
    if (t.due_at) {
      const olymp = t.kind === 'olympiad' || t.kind === 'event';
      const overdue = t.status === 'active' && !olymp && new Date(t.due_at) < now;
      const tone: EntryTone = t.status === 'done' ? 'done' : overdue ? 'overdue' : olymp && t.kind === 'olympiad' ? 'olympiad' : 'plain';
      const label = tone === 'done' ? 'Сделано' : tone === 'overdue' ? 'Просрочено' : t.kind === 'olympiad' ? 'Олимпиада' : t.subject ?? 'Дело';
      out.push({
        key: `d${t.id}`, at: t.due_at, day: dayKey(local(t.due_at)),
        time: timeRange(t.due_at, t.kind === 'event' ? t.duration_min : null), title: t.title, label, tone,
        color: subjectColors(t.kind === 'olympiad' ? 'олимпиада' : t.subject).dot, task: t,
      });
    }
    if (t.reg_deadline && t.status === 'active' && !t.registered) {
      out.push({
        key: `r${t.id}`, at: t.reg_deadline, day: dayKey(local(t.reg_deadline)), time: timeText(t.reg_deadline),
        title: `Регистрация до ${dateLong(local(t.reg_deadline))}: ${t.title}`, label: 'Регистрация', tone: 'reg', color: '#8e8e93', task: t,
      });
    }
    if (t.kind === 'homework' && t.status === 'active' && t.planned_at && (!t.due_at || t.planned_at < t.due_at)) {
      const at = t.planned_at;
      out.push({
        key: `p${t.id}`, at, day: dayKey(local(at)), time: timeText(at),
        title: t.title, label: 'Начать задание', tone: 'plain', color: subjectColors(t.subject).dot, task: t
      });
    }
  }
  for (const o of olympiads) {
    const color = subjectColors(o.subject).dot;
    for (const tour of o.tours) {
      const at = tour.deadline ?? tour.starts_at;
      if (!at || tour.done) {
        continue;
      }
      const event = tour.deadline === tour.starts_at;
      out.push({
        key: `o${o.id}t${tour.id}`, at, day: dayKey(local(at)), time: event ? timeRange(at, tour.duration_min) : 'Весь день',
        title: `${o.name} · ${tour.title}`, label: 'Олимпиада', tone: 'olympiad', color, olympiad: o
      });
    }
    if (o.registered) {
      continue;
    }
    for (const [label, at] of [['Открывается регистрация', o.reg_opens], ['Последний день регистрации', o.reg_deadline]] as const) {
      if (!at) {
        continue;
      }
      out.push({
        key: `o${o.id}-${label}`, at, day: dayKey(local(at)), time: timeText(at),
        title: o.name, label, tone: 'reg', color, olympiad: o
      });
    }
  }
  return out.sort((a, b) => a.at.localeCompare(b.at));
}
export function groupByDay(entries: Entry[]) {
  const map = new Map<string, Entry[]>();
  for (const e of entries) {
    if (!map.has(e.day)) {
      map.set(e.day, []);
    }
    map.get(e.day)!.push(e);
  }
  return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
}
