export interface Ymd {
  y: number;
  m: number;
  d: number;
}
export function maskDate(raw: string): string {
  const digits = raw.replace(/\D/g, '').slice(0, 8);
  let out = digits.slice(0, 2);
  if (digits.length > 2) {
    out += '.' + digits.slice(2, 4);
  }
  if (digits.length > 4) {
    out += '.' + digits.slice(4, 8);
  }
  return out;
}
export function maskTime(raw: string): string {
  const digits = raw.replace(/\D/g, '').slice(0, 4);
  const hourLen = digits.length > 0 && Number(digits[0]) > 2 ? 1 : 2;
  if (digits.length > hourLen) {
    return `${digits.slice(0, hourLen)}:${digits.slice(hourLen, hourLen + 2)}`;
  }
  return digits;
}
const pad = (n: number) => String(n).padStart(2, '0');
const valid = (y: number, m: number, d: number) => {
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
};
const dayNumber = (y: number, m: number, d: number) => Math.floor(Date.UTC(y, m - 1, d) / 86400000);
export const PAST_GRACE_DAYS = 60;
export function resolveDate(text: string, today: Ymd): string | null {
  const m = text.trim().match(/^(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?$/);
  if (!m) {
    return null;
  }
  const d = Number(m[1]);
  const mo = Number(m[2]);
  let y = m[3] ? Number(m[3]) : today.y;
  if (!m[3]) {
    if (!valid(y, mo, d)) {
      return null;
    }
    if (dayNumber(y, mo, d) < dayNumber(today.y, today.m, today.d) - PAST_GRACE_DAYS) {
      y += 1;
    }
  }
  if (valid(y, mo, d)) {
    return `${y}-${pad(mo)}-${pad(d)}`;
  }
  return null;
}
export function resolveTime(text: string): string | null {
  const m = text.trim().match(/^(\d{1,2}):?(\d{2})$/);
  if (!m || Number(m[1]) > 23 || Number(m[2]) > 59) {
    return null;
  }
  return `${pad(Number(m[1]))}:${m[2]}`;
}
export const isoToText = (iso: string) => {
  if (iso) {
    return iso.split('-').reverse().join('.');
  }
  return '';
};
