export const MODES = [
  { id: 'system', label: 'Системная' }, { id: 'light', label: 'Светлая' }, { id: 'dark', label: 'Тёмная' },
] as const;
export type Theme = typeof MODES[number]['id'];
export const THEMES = [
  { id: 'plain-dark', label: 'Обычная тёмная', description: 'Графит без цветного оттенка', color: '#0b0b0d', incoming: '#303036', outgoing: '#2f8cff' },
  { id: 'plain-light', label: 'Обычная белая', description: 'Светлый фон без оттенка', color: '#f2f2f7', incoming: '#e0e0e6', outgoing: '#2f8cff' },
  { id: 'cosmos', label: 'Космос', description: 'Фиолетовый градиент', color: '#101015', incoming: '#30313f', outgoing: 'linear-gradient(110deg, #6566d9, #8b4cb1)' },
  { id: 'confident', label: 'Уверенная', description: 'Спокойный бирюзовый', color: '#101415', incoming: '#1c2c2b', outgoing: 'linear-gradient(110deg, #4d9bac, #388f94)' },
  { id: 'elegant', label: 'Изящная', description: 'Розовый и коралловый', color: '#171317', incoming: '#352735', outgoing: 'linear-gradient(110deg, #ba467f, #dd6464)' },
  { id: 'forest', label: 'Летний лес', description: 'Спокойный зелёный', color: '#10150f', incoming: '#1a2b24', outgoing: 'linear-gradient(110deg, #174f36, #20653f)' },
  { id: 'neon', label: 'Неон', description: 'Фиолетовый, розовый, коралл', color: '#111015', incoming: '#30313b', outgoing: 'linear-gradient(110deg, #543bdc, #a42dbd 58%, #dc6860)' },
  { id: 'lavender', label: 'Лаванда', description: 'Мягкий лавандовый градиент', color: '#171122', incoming: '#30243e', outgoing: 'linear-gradient(115deg, #7c20d9, #471aff)' },
] as const;
export type Palette = typeof THEMES[number]['id'];
export function normalizeLook(value: {
  mapBg?: unknown;
  theme?: unknown;
  palette?: unknown;
} | null) {
  const v = value ?? {};
  const legacy: Record<string, Palette> = { aurora: 'neon', nebula: 'cosmos', comet: 'confident', lavender: 'lavender' };
  const oldPalette = typeof v.theme === 'string' && Object.hasOwn(legacy, v.theme) ? legacy[v.theme] : undefined;
  const theme: Theme = MODES.some((m) => m.id === v.theme) ? v.theme as Theme : v.theme === 'lavender' ? 'light' : 'dark';
  const palette: Palette = THEMES.some((p) => p.id === v.palette) ? v.palette as Palette : oldPalette ?? (theme === 'light' ? 'plain-light' : 'plain-dark');
  const mapBg = v.mapBg === 'grid' || v.mapBg === 'plain' ? v.mapBg : 'dots';
  return { theme, palette, mapBg } as const;
}
