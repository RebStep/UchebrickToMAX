import { computed, reactive, ref } from 'vue';
import { getLooseFiles, getNotes, getOlympiads, getTasks, login, type ApiFile, type ApiNote, type ApiOlympiad, type ApiTask } from './api';
import { mockOlympiads, mockTasks } from './mock';
import type { FileItem, Olympiad, Task } from './types';
import { THEMES, normalizeLook, type Theme, type Palette } from './themes';
import { createUndoQueue, type UndoEntry } from './undoQueue';
export type { Theme, Palette } from './themes';
export type Tab = 'map' | 'calendar' | 'olympiads' | 'settings';
export const state = reactive({
  tab: 'map' as Tab,
  tasks: [] as Task[],
  olympiads: [] as Olympiad[],
  filter: null as string | null,
  loading: true,
  error: '',
  toast: '',
  undo: null as UndoEntry | null,
  loose: [] as FileItem[],
});
export const UNDO_MS = 6000;
const undoQueue = createUndoQueue({
  duration: UNDO_MS,
  changed: (entry) => { state.undo = entry; },
  failed: () => toast('Не получилось вернуть, попробуйте ещё раз'),
});
export const offerUndo = undoQueue.add;
export const expireUndo = undoQueue.expire;
export const flushUndo = undoQueue.flush;
export async function runUndo() {
  try {
    await undoQueue.undo();
  }
  catch {
    toast('Не получилось вернуть, попробуйте ещё раз');
  }
}
const pendingRemovals = new Map<symbol, () => void>();
let removalVersion = 0;
const committedRemovals = new Map<symbol, {
  hide: () => void;
  version: number;
}>();
const applyRemovals = () => {
  committedRemovals.forEach(({ hide }) => hide());
  pendingRemovals.forEach((hide) => hide());
};
export function stageRemoval(action: {
  title: string;
  detail: string;
  hide: () => void;
  restore: () => void;
  commit: () => void | Promise<unknown>;
  missingIsSuccess?: boolean;
}) {
  const key = Symbol();
  pendingRemovals.set(key, action.hide);
  action.hide();
  const restore = () => {
    pendingRemovals.delete(key);
    action.restore();
    applyRemovals();
  };
  offerUndo({
    title: action.title, detail: action.detail,
    revert: () => { restore(); toast('Восстановлено'); },
    commit: async () => {
      try {
        await action.commit();
      }
      catch (e) {
        if (!(action.missingIsSuccess !== false && e instanceof Error && e.message === 'HTTP 404')) {
          restore();
          toast('Не удалилось — объект восстановлен');
          return;
        }
      }
      committedRemovals.set(key, { hide: action.hide, version: ++removalVersion });
      pendingRemovals.delete(key);
    },
  });
}
function readNavigation() {
  try {
    return localStorage.getItem('uchebrik_nav_collapsed') === '1';
  }
  catch {
    return false;
  }
}
export const navCollapsed = ref(readNavigation());
export const navigationInset = computed(() => {
  if (navCollapsed.value) {
    return 104;
  }
  return 264;
});
export function toggleNavigation() {
  navCollapsed.value = !navCollapsed.value;
  try {
    localStorage.setItem('uchebrik_nav_collapsed', navCollapsed.value ? '1' : '0');
  }
  catch { }
}
export type MapBg = 'dots' | 'grid' | 'plain';
const LOOK_KEY = 'uchebrik_look';
function readLook(): {
  mapBg: MapBg;
  theme: Theme;
  palette: Palette;
} {
  try {
    return normalizeLook(JSON.parse(localStorage.getItem(LOOK_KEY) ?? '{}'));
  }
  catch {
    return normalizeLook(null);
  }
}
export const look = reactive(readLook());
export const lightTheme = ref(false);
const systemLight = window.matchMedia('(prefers-color-scheme: light)');
export function applyLook() {
  const light = look.theme === 'light' || (look.theme === 'system' && systemLight.matches);
  const classic = look.palette === 'plain-dark' || look.palette === 'plain-light';
  if (classic) {
    look.palette = light ? 'plain-light' : 'plain-dark';
  }
  const theme = THEMES.find((t) => t.id === look.palette) ?? THEMES[0];
  document.documentElement.dataset.theme = light ? 'light' : 'dark';
  if (classic) {
    delete document.documentElement.dataset.palette;
  }
  else {
    document.documentElement.dataset.palette = theme.id;
  }
  lightTheme.value = light;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', light ? (classic ? '#f2f2f7' : theme.id === 'lavender' ? '#f4f0ff' : '#f3f5f5') : theme.color);
  try {
    localStorage.setItem(LOOK_KEY, JSON.stringify(look));
  }
  catch { }
}
systemLight.addEventListener('change', applyLook);
applyLook();
let toastTimer = 0;
export function toast(text: string) {
  state.toast = text;
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => state.toast = '', 2200);
}
export const activeTasks = computed(() => state.tasks.filter((t) => t.status !== 'done'));
import { groupOf } from './groups';
export { groupOf, KIND_GROUPS } from './groups';
export const subjects = computed(() => {
  const seen: string[] = [];
  for (const t of activeTasks.value) {
    const s = groupOf(t);
    if (!seen.includes(s)) {
      seen.push(s);
    }
  }
  return seen;
});
export const visibleTasks = computed(() => activeTasks.value.filter((t) => !state.filter || groupOf(t) === state.filter));
const LINK_ID_OFFSET = 1000000;
export function fromApi(r: ApiTask, files: FileItem[] = [], notes: ApiNote[] = []): Task {
  const links: FileItem[] = (r.links ?? []).map((l) => {
    const prev = files.find((f) => f.type === 'link' && (f.url === l.url || f.id === LINK_ID_OFFSET + l.id));
    return {
      id: LINK_ID_OFFSET + l.id, task_id: r.id, type: 'link', name: l.url.replace(/^https?:\/\//, ''), url: l.url,
      x: l.x ?? prev?.x ?? null, y: l.y ?? prev?.y ?? null,
    };
  });
  const attachments: FileItem[] = (r.attachments ?? []).map((a) => {
    const prev = files.find((f) => f.id === FILE_ID_OFFSET + a.id);
    return {
      id: FILE_ID_OFFSET + a.id, task_id: r.id, type: a.kind, name: a.name, hint: a.kind === 'doc' ? 'открыть' : undefined,
      x: a.x ?? prev?.x ?? null, y: a.y ?? prev?.y ?? null
    };
  });
  const serverIds = new Set(attachments.map((a) => a.id));
  const local = files.filter((f) => f.type !== 'link' && !serverIds.has(f.id) && !(r.attachments && f.id >= FILE_ID_OFFSET))
    .filter((f) => f.id < NOTE_ID_OFFSET && !(f.type === 'note' && notes.length));
  return {
    id: r.id, title: r.title, subject: r.subject, kind: r.kind ?? 'homework', due_at: r.due_at, location: r.location ?? null,
    note: r.note ?? null, reg_deadline: r.reg_deadline ?? null, duration_min: r.duration_min ?? null, registered: r.registered,
    planned_at: r.work_schedule && r.work_schedule !== 'classic' ? r.next_remind_at ?? null : null,
    status: r.status, x: r.x ?? null, y: r.y ?? null, created_at: r.created_at ?? null,
    files: [...links, ...attachments, ...notes.map(noteFromApi), ...local.map((f) => ({ ...f, task_id: r.id }))],
  };
}
const FILE_ID_OFFSET = 2000000;
const NOTE_ID_OFFSET = 3000000;
export const serverLinkId = (f: FileItem) => {
  if (f.id >= LINK_ID_OFFSET && f.id < FILE_ID_OFFSET) {
    return f.id - LINK_ID_OFFSET;
  }
  return null;
};
export const serverFileId = (f: FileItem) => {
  if (f.id >= FILE_ID_OFFSET && f.id < NOTE_ID_OFFSET) {
    return f.id - FILE_ID_OFFSET;
  }
  return null;
};
export const serverNoteId = (f: FileItem) => {
  if (f.id >= NOTE_ID_OFFSET) {
    return f.id - NOTE_ID_OFFSET;
  }
  return null;
};
const firstLine = (text: string) => text.split('\n')[0].slice(0, 60);
export const noteFromApi = (n: ApiNote): FileItem => {
  return {
    id: NOTE_ID_OFFSET + n.id, task_id: n.task_id, type: 'note', name: firstLine(n.text), text: n.text, x: n.x, y: n.y,
  };
};
export const looseFileFromApi = (f: ApiFile): FileItem => {
  return {
    id: FILE_ID_OFFSET + f.id, task_id: null, type: f.kind, name: f.name, hint: f.kind === 'doc' ? 'открыть' : undefined, x: f.x, y: f.y,
  };
};
export function normUrl(raw: string | null | undefined): string | null {
  const v = (raw ?? '').trim();
  if (!v) {
    return null;
  }
  try {
    const u = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(v) ? v : `https://${v}`);
    if (u.protocol === 'http:' || u.protocol === 'https:') {
      return u.toString();
    }
    return null;
  }
  catch {
    return null;
  }
}
export const olympiadFromApi = (o: ApiOlympiad): Olympiad => ({ ...o, tours: o.tours.map((t, i) => ({ id: i + 1, ...t })) });
export const olympiadToApi = ({ id: _id, tours, ...rest }: Olympiad) => ({ ...rest, tours: tours.map(({ id: _t, ...t }) => t) });
export function removeOlympiad(id: number) {
  state.olympiads = state.olympiads.filter((o) => o.id !== id);
}
export async function reload() {
  const version = removalVersion;
  const [rows, olympiads, looseFiles, notes] = await Promise.all([getTasks(), getOlympiads(), getLooseFiles(), getNotes()]);
  const taskIds = new Set(rows.map((r) => r.id));
  state.tasks = rows.map((r) => fromApi(r, [], notes.filter((n) => n.task_id === r.id)));
  state.olympiads = olympiads.map(olympiadFromApi);
  state.loose = [...looseFiles.map(looseFileFromApi), ...notes.filter((n) => n.task_id === null || !taskIds.has(n.task_id)).map(noteFromApi)];
  if (!pendingRemovals.size) {
    for (const [key, entry] of committedRemovals) {
      if (entry.version <= version) {
        committedRemovals.delete(key);
      }
    }
  }
  applyRemovals();
  rememberNewest();
}
const SEEN_KEY = 'uchebrik_newest_seen';
export const fresh = reactive(new Set<number>());
const newestOf = () => {
  return state.tasks.reduce((m, t) => Math.max(m, t.created_at ? Date.parse(t.created_at) || 0 : 0), 0);
};
function seenBefore(): number | null {
  try {
    const v = Number(localStorage.getItem(SEEN_KEY));
    if (Number.isFinite(v) && v > 0) {
      return v;
    }
    return null;
  }
  catch {
    return null;
  }
}
function rememberNewest() {
  const newest = Math.max(newestOf(), seenBefore() ?? 0);
  if (!newest) {
    return;
  }
  try {
    localStorage.setItem(SEEN_KEY, String(newest));
  }
  catch { }
}
export const FRESH_MS = 6000;
function markFresh(since: number | null) {
  if (since === null) {
    return;
  }
  for (const t of state.tasks) {
    if (t.created_at && Date.parse(t.created_at) > since) {
      fresh.add(t.id);
    }
  }
  if (fresh.size) {
    setTimeout(() => fresh.clear(), FRESH_MS);
  }
}
export async function loadFromApi() {
  try {
    await login();
    const since = seenBefore();
    await reload();
    markFresh(since);
  }
  catch (e) {
    state.error = e instanceof Error ? e.message : 'Не удалось загрузить задания';
  }
  finally {
    state.loading = false;
  }
}
export function loadMock() {
  state.tasks = mockTasks();
  state.loose = [{ id: 900, task_id: null, type: 'note', name: 'Купить тетради', text: 'Купить тетради\nв клетку, 3 шт', x: 900, y: 140 }];
  state.olympiads = mockOlympiads();
  state.loading = false;
}
let nextId = 1000;
export const newId = () => nextId++;
export function saveTask(t: Task) {
  const i = state.tasks.findIndex((x) => x.id === t.id);
  if (i >= 0) {
    state.tasks[i] = t;
  }
  else {
    state.tasks.push(t);
  }
}
export function removeTask(id: number) {
  state.tasks = state.tasks.filter((t) => t.id !== id);
}
export function toggleDone(id: number) {
  const t = state.tasks.find((x) => x.id === id);
  if (t) {
    t.status = t.status === 'done' ? 'active' : 'done';
  }
}
export function moveTask(id: number, x: number, y: number) {
  const t = state.tasks.find((x2) => x2.id === id);
  if (t) {
    t.x = x;
    t.y = y;
  }
}
export function moveFile(f: FileItem, x: number, y: number) {
  for (const item of [...state.loose, ...state.tasks.flatMap((t) => t.files), f]) {
    if (item.id === f.id) {
      item.x = x;
      item.y = y;
    }
  }
}
export function saveOlympiad(o: Olympiad) {
  const i = state.olympiads.findIndex((x) => x.id === o.id);
  if (i >= 0) {
    state.olympiads[i] = o;
  }
  else {
    state.olympiads.push(o);
  }
}
export function toggleRegistered(id: number) {
  const o = state.olympiads.find((x) => x.id === id);
  if (o) {
    o.registered = !o.registered;
  }
}
