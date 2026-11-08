import { lightTheme } from './store';
const KNOWN: Record<string, {
  text: string;
  bg: string;
  dot: string;
}> = {
  'математика': { text: '#79b3fd', bg: '#25354c', dot: '#2f8cff' },
  'алгебра': { text: '#79b3fd', bg: '#25354c', dot: '#2f8cff' },
  'геометрия': { text: '#79b3fd', bg: '#25354c', dot: '#2f8cff' },
  'физика': { text: '#fdc47d', bg: '#493a2a', dot: '#ffb454' },
  'русский язык': { text: '#fd99bc', bg: '#492e3a', dot: '#ff7aa8' },
  'русский': { text: '#fd99bc', bg: '#492e3a', dot: '#ff7aa8' },
  'литература': { text: '#fd99bc', bg: '#492e3a', dot: '#ff7aa8' },
  'английский язык': { text: '#85d9a5', bg: '#293f34', dot: '#5fd08a' },
  'история': { text: '#85d9a5', bg: '#293f34', dot: '#5fd08a' },
  'олимпиада': { text: '#bc91fd', bg: '#372c4c', dot: '#a970ff' },
};
const FALLBACK = [
  { text: '#7fd6d6', bg: '#243f40', dot: '#4cc3c3' },
  { text: '#e3b86a', bg: '#47391f', dot: '#d9a441' },
  { text: '#c9a0ff', bg: '#352a4a', dot: '#a970ff' },
  { text: '#9bd16f', bg: '#34401f', dot: '#80c34d' },
];
const NONE = { text: '#c7c7cc', bg: '#2a2a30', dot: '#8e8e93' };
function hash(s: string) {
  let h = 0;
  for (const ch of s) {
    h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  }
  return h;
}
function darken(hex: string, k = 0.42) {
  const n = parseInt(hex.slice(1), 16);
  const c = [n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.round(v * (1 - k)));
  return `#${c.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}
export function subjectColors(subject: string | null) {
  const key = subject?.trim().toLowerCase() ?? '';
  const c = !subject ? NONE : KNOWN[key] ?? FALLBACK[hash(key) % FALLBACK.length];
  if (lightTheme.value) {
    return { text: darken(c.dot), bg: `${c.dot}29`, dot: c.dot };
  }
  return c;
}
