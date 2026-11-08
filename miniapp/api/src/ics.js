export function escapeText(value) {
  return String(value)
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\r|\n/g, '\\n');
}
export function fold(line) {
  const bytes = (s) => Buffer.byteLength(s, 'utf8');
  if (bytes(line) <= 75) {
    return line;
  }
  const parts = [];
  let current = '';
  for (const ch of line) {
    const limit = parts.length === 0 ? 75 : 74;
    if (bytes(current + ch) > limit) {
      parts.push(current);
      current = ch;
    }
    else {
      current += ch;
    }
  }
  parts.push(current);
  return parts.join('\r\n ');
}
const pad = (n) => String(n).padStart(2, '0');
const utcStamp = (d) => {
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`;
};
function localParts(date, tz) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .formatToParts(date)
    .map((p) => [p.type, p.value]));
  return { y: +parts.year, m: +parts.month, d: +parts.day, hh: +parts.hour, mm: +parts.minute };
}
const dateValue = (y, m, d) => {
  const dt = new Date(Date.UTC(y, m - 1, d));
  return `${dt.getUTCFullYear()}${pad(dt.getUTCMonth() + 1)}${pad(dt.getUTCDate())}`;
};
export function buildCalendar(tasks, { now = new Date(), host = 'uchebrick', olympiads = [] } = {}) {
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Uchebrik//MAX//RU',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    `X-WR-CALNAME:${escapeText('Учебрик')}`,
    'REFRESH-INTERVAL;VALUE=DURATION:PT1H',
    'X-PUBLISHED-TTL:PT1H',
  ];
  const olympiadEvents = olympiads.flatMap((o) => {
    return o.tours.flatMap((tour, i) => {
      const at = tour.deadline ?? tour.starts_at;
      if (!at || tour.done) {
        return [];
      }
      const event = tour.starts_at === tour.deadline;
      return [{
        id: `olympiad-${o.id}-${i}`, title: `${o.name} · ${tour.title}`, subject: o.subject,
        due_at: at, tz: o.tz, kind: event ? 'event' : 'olympiad', duration_min: tour.duration_min,
        location: o.location, note: [o.note, ...(o.links ?? [])].filter(Boolean).join('\n'),
      }];
    });
  });
  for (const t of [...tasks, ...olympiadEvents]) {
    if (!t.due_at) {
      continue;
    }
    const due = new Date(t.due_at);
    const tz = t.tz || 'Europe/Samara';
    const local = localParts(due, tz);
    const summary = t.subject ? `${t.subject}: ${t.title}` : t.title;
    lines.push('BEGIN:VEVENT', `UID:task-${t.id}@${host}`, `DTSTAMP:${utcStamp(now)}`);
    if (local.hh === 23 && local.mm === 59 && t.kind !== 'event') {
      lines.push(`DTSTART;VALUE=DATE:${dateValue(local.y, local.m, local.d)}`, `DTEND;VALUE=DATE:${dateValue(local.y, local.m, local.d + 1)}`);
    }
    else {
      lines.push(`DTSTART:${utcStamp(due)}`, `DURATION:PT${t.kind === 'event' && t.duration_min ? t.duration_min : 30}M`);
    }
    lines.push(`SUMMARY:${escapeText(summary)}`);
    if (t.location) {
      lines.push(`LOCATION:${escapeText(t.location)}`);
    }
    if (t.note) {
      lines.push(`DESCRIPTION:${escapeText(t.note)}`);
    }
    lines.push('END:VEVENT');
  }
  lines.push('END:VCALENDAR');
  return lines.map(fold).join('\r\n') + '\r\n';
}
