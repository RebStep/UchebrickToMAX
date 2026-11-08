import type { Kind, Olympiad } from './types';
export interface ApiTask {
  id: number;
  title: string;
  subject: string | null;
  kind: Kind;
  due_at: string | null;
  location: string | null;
  note: string | null;
  reg_deadline: string | null;
  duration_min?: number | null;
  registered?: boolean;
  next_remind_at?: string | null;
  work_schedule?: string;
  status: 'active' | 'done';
  x: number | null;
  y: number | null;
  created_at?: string;
  tz: string;
  links?: {
    id: number;
    url: string;
    x?: number | null;
    y?: number | null;
  }[];
  attachments?: {
    id: number;
    kind: 'photo' | 'doc';
    name: string;
    size: number;
    x?: number | null;
    y?: number | null;
  }[];
}
export type TaskFields = Partial<Pick<ApiTask, 'title' | 'subject' | 'kind' | 'due_at' | 'location' | 'note' | 'reg_deadline' | 'duration_min' | 'registered'>>;
let token = '';
async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  if (init.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(path, { keepalive: init.method === 'DELETE' || init.method === 'PATCH', ...init, headers: { ...headers, ...(init.headers as Record<string, string> | undefined) } });
  if (res.status === 401) {
    token = '';
    try {
      localStorage.removeItem(STORAGE_KEY);
    }
    catch { }
    throw new Error('Ссылка устарела. Откройте «Карта документов» в чате с ботом ещё раз');
  }
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}
type Session = {
  token: string;
  user: {
    id: number;
    first_name: string | null;
  };
};
const STORAGE_KEY = 'uchebrik_session';
function remember(s: Session) {
  token = s.token;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  }
  catch { }
}
function stored(): Session | null {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null');
  }
  catch {
    return null;
  }
}
export async function login(): Promise<{
  id: number;
  first_name: string | null;
}> {
  const initData = window.WebApp?.initData;
  if (initData) {
    const s = await call<Session>('/api/auth', { method: 'POST', body: JSON.stringify({ initData }) });
    remember(s);
    return s.user;
  }
  const params = new URLSearchParams(location.search);
  const link = params.get('t');
  if (link) {
    history.replaceState(null, '', location.pathname);
    const s = await call<Session>('/api/auth/link', { method: 'POST', body: JSON.stringify({ token: link }) });
    remember(s);
    return s.user;
  }
  const saved = stored();
  if (saved) {
    token = saved.token;
    return saved.user;
  }
  throw new Error('Откройте Учебрик по кнопке «Карта документов» в чате с ботом');
}
const json = (body: unknown) => JSON.stringify(body);
export const getTasks = () => {
  return call<{
    tasks: ApiTask[];
  }>('/api/tasks').then((r) => r.tasks);
};
export const createTask = (f: TaskFields) => {
  return call<{
    task: ApiTask;
  }>('/api/tasks', { method: 'POST', body: json(f) }).then((r) => r.task);
};
export const updateTask = (id: number, f: TaskFields) => {
  return call<{
    task: ApiTask;
  }>(`/api/tasks/${id}`, { method: 'PATCH', body: json(f) }).then((r) => r.task);
};
export const deleteTask = (id: number) => {
  return call<{
    deleted: boolean;
  }>(`/api/tasks/${id}`, { method: 'DELETE' });
};
export const markDone = (id: number) => {
  return call<{
    changed: boolean;
  }>(`/api/tasks/${id}/done`, { method: 'POST' });
};
export const markUndone = (id: number) => {
  return call<{
    changed: boolean;
  }>(`/api/tasks/${id}/undone`, { method: 'POST' });
};
export const getTask = (id: number) => {
  return call<{
    task: ApiTask;
  }>(`/api/tasks/${id}`).then((r) => r.task);
};
export const addLink = (id: number, url: string) => {
  return call<{
    link: {
      id: number;
      url: string;
    };
  }>(`/api/tasks/${id}/links`, { method: 'POST', body: json({ url }) });
};
export const deleteLink = (id: number, linkId: number) => {
  return call<{
    deleted: boolean;
  }>(`/api/tasks/${id}/links/${linkId}`, { method: 'DELETE' });
};
export const attachLinkToTask = (taskId: number, linkId: number) => {
  return call<{
    ok: boolean;
  }>(`/api/tasks/${taskId}/links/${linkId}/attach`, { method: 'PATCH' });
};
export async function uploadFile(taskId: number, file: File) {
  const res = await fetch(`/api/tasks/${taskId}/files?name=${encodeURIComponent(file.name)}`, {
    method: 'POST',
    body: file,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/octet-stream', 'X-File-Type': file.type || '' },
  });
  if (!res.ok) {
    throw new Error(res.status === 413 ? 'Файл больше 20 МБ' : `HTTP ${res.status}`);
  }
  return (await res.json()).file as {
    id: number;
    kind: 'photo' | 'doc';
    name: string;
    size: number;
  };
}
export type ApiFile = {
  id: number;
  kind: 'photo' | 'doc';
  name: string;
  size: number;
  x: number | null;
  y: number | null;
};
export type ApiNote = {
  id: number;
  task_id: number | null;
  text: string;
  x: number | null;
  y: number | null;
};
export async function uploadLooseFile(file: File, x: number, y: number) {
  const res = await fetch(`/api/files?name=${encodeURIComponent(file.name)}&x=${Math.round(x)}&y=${Math.round(y)}`, {
    method: 'POST',
    body: file,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/octet-stream', 'X-File-Type': file.type || '' },
  });
  if (!res.ok) {
    throw new Error(res.status === 413 ? 'Файл больше 20 МБ' : `HTTP ${res.status}`);
  }
  return (await res.json()).file as ApiFile;
}
export const getLooseFiles = () => {
  return call<{
    files: ApiFile[];
  }>('/api/files').then((r) => r.files);
};
export const attachFile = (fileId: number, taskId: number | null) => {
  return call<{
    ok: boolean;
  }>(`/api/files/${fileId}`, { method: 'PATCH', body: json({ task_id: taskId }) });
};
export const unlinkFile = (fileId: number, taskId: number, drop = false) => {
  return call<{
    ok: boolean;
    deleted: boolean;
  }>(`/api/files/${fileId}/links/${taskId}${drop ? '?drop=1' : ''}`, { method: 'DELETE' });
};
export const getNotes = () => {
  return call<{
    notes: ApiNote[];
  }>('/api/notes').then((r) => r.notes);
};
export const createNote = (n: {
  text: string;
  task_id?: number | null;
  x?: number;
  y?: number;
}) => {
  return call<{
    note: ApiNote;
  }>('/api/notes', { method: 'POST', body: json(n) }).then((r) => r.note);
};
export const updateNote = (id: number, n: {
  text?: string;
  task_id?: number | null;
}) => {
  return call<{
    note: ApiNote;
  }>(`/api/notes/${id}`, { method: 'PATCH', body: json(n) }).then((r) => r.note);
};
export const deleteNote = (id: number) => {
  return call<{
    deleted: boolean;
  }>(`/api/notes/${id}`, { method: 'DELETE' });
};
export const saveNotePosition = (id: number, x: number, y: number) => {
  return call<{
    ok: boolean;
  }>(`/api/notes/${id}/position`, { method: 'PUT', body: json({ x, y }) });
};
export const deleteFile = (fileId: number) => {
  return call<{
    deleted: boolean;
  }>(`/api/files/${fileId}`, { method: 'DELETE' });
};
const blobCache = new Map<number, Promise<string>>();
export function fileUrl(fileId: number): Promise<string> {
  if (!blobCache.has(fileId)) {
    blobCache.set(fileId, fetch(`/api/files/${fileId}`, { headers: { Authorization: `Bearer ${token}` } }).then(async (r) => {
      if (!r.ok) {
        throw new Error(`HTTP ${r.status}`);
      }
      return URL.createObjectURL(await r.blob());
    }));
  }
  const p = blobCache.get(fileId)!;
  p.catch(() => blobCache.delete(fileId));
  return p;
}
export type ApiOlympiad = Omit<Olympiad, 'tours'> & {
  tours: {
    title: string;
    starts_at: string | null;
    deadline: string | null;
    done: boolean;
  }[];
};
export type OlympiadFields = Omit<ApiOlympiad, 'id'>;
export const getOlympiads = () => {
  return call<{
    olympiads: ApiOlympiad[];
  }>('/api/olympiads').then((r) => r.olympiads);
};
export const createOlympiad = (o: OlympiadFields) => {
  return call<{
    olympiad: ApiOlympiad;
  }>('/api/olympiads', { method: 'POST', body: json(o) }).then((r) => r.olympiad);
};
export const updateOlympiad = (id: number, o: OlympiadFields) => {
  return call<{
    olympiad: ApiOlympiad;
  }>(`/api/olympiads/${id}`, { method: 'PUT', body: json(o) }).then((r) => r.olympiad);
};
export const setRegistered = (id: number, registered: boolean) => {
  return call<{
    ok: boolean;
  }>(`/api/olympiads/${id}/registered`, { method: 'PUT', body: json({ registered }) });
};
export const deleteOlympiad = (id: number) => {
  return call<{
    deleted: boolean;
  }>(`/api/olympiads/${id}`, { method: 'DELETE' });
};
export type Settings = {
  tz: string;
  quiet_from: string;
  quiet_to: string;
  repeat_min: number;
  repeat_max: number;
  ics_url: string;
  remind_mode: 'all' | 'selected' | 'none';
  work_schedule: 'classic' | 'school' | 'evening';
  morning_at: string | null;
  alice_enabled: boolean;
  alice_linked: boolean;
  alice_private_url: string | null;
};
export type SettingsPatch = Partial<Pick<Settings, 'quiet_from' | 'quiet_to' | 'repeat_min' | 'repeat_max' | 'remind_mode' | 'work_schedule' | 'morning_at'>>;
export const getSettings = () => {
  return call<{
    settings: Settings;
  }>('/api/settings').then((r) => r.settings);
};
export const saveSettings = (s: SettingsPatch) => {
  return call<{
    settings: Settings;
  }>('/api/settings', { method: 'PUT', body: json(s), keepalive: true }).then((r) => r.settings);
};
export const createBrowserLink = () => {
  return call<{
    url: string;
  }>('/api/settings/browser-link', { method: 'POST' });
};
export const logoutBrowsers = () => {
  return call<{
    ok: boolean;
  }>('/api/settings/logout', { method: 'POST' });
};
export const createAliceCode = () => {
  return call<{
    code: string;
    expires_in: number;
  }>('/api/settings/alice/code', { method: 'POST' });
};
export const createAlicePrivate = (reset = false) => {
  return call<{
    url: string;
  }>('/api/settings/alice/private', { method: 'POST', body: json({ reset }) });
};
export const deleteAlicePrivate = () => {
  return call<{
    ok: boolean;
  }>('/api/settings/alice/private', { method: 'DELETE' });
};
export const unlinkAlice = () => {
  return call<{
    ok: boolean;
  }>('/api/settings/alice', { method: 'DELETE' });
};
export function clearSession() {
  token = '';
  try {
    localStorage.removeItem(STORAGE_KEY);
  }
  catch { }
}
export type ObjectSelection = {
  tasks: number[];
  files: number[];
  notes: number[];
  links: number[];
};
export const deleteObjects = (selection: ObjectSelection) => {
  return call<{
    deleted: boolean;
  }>('/api/objects/delete', {
    method: 'POST', body: json(selection), keepalive: true,
  });
};
export const savePosition = (id: number, x: number, y: number) => {
  return call<{
    ok: boolean;
  }>(`/api/tasks/${id}/position`, { method: 'PUT', body: json({ x, y }) });
};
export const saveLinkPosition = (taskId: number, linkId: number, x: number, y: number) => {
  return call<{
    ok: boolean;
  }>(`/api/tasks/${taskId}/links/${linkId}/position`, { method: 'PUT', body: json({ x, y }) });
};
export const saveFilePosition = (fileId: number, x: number, y: number) => {
  return call<{
    ok: boolean;
  }>(`/api/files/${fileId}/position`, { method: 'PUT', body: json({ x, y }) });
};
export type VoiceTask = {
  title: string;
  subject: string | null;
  kind: Kind;
  due_at: string | null;
  reg_deadline: string | null;
  location: string | null;
  duration_min: number | null;
};
export type VoiceResult = {
  transcript: string;
  tasks: VoiceTask[];
};
export async function recognizeVoice(audio: Blob): Promise<VoiceResult> {
  if (import.meta.env.VITE_MOCK === '1') {
    await new Promise((r) => setTimeout(r, 800));
    const due = new Date(Date.now() + 86400000).toISOString();
    return { transcript: 'алгебра номер 24 к завтра', tasks: [{ title: '№24', subject: 'Алгебра', kind: 'homework', due_at: due, reg_deadline: null, location: null, duration_min: null }] };
  }
  const res = await fetch('/api/voice', {
    method: 'POST',
    body: audio,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/octet-stream' },
  });
  if (res.status === 413) {
    throw new Error('Запись слишком длинная');
  }
  if (res.status === 429) {
    throw new Error('Подожди, предыдущие записи ещё распознаются');
  }
  if (!res.ok) {
    throw new Error('Не удалось отправить запись');
  }
  const { id } = (await res.json()) as {
    id: number;
  };
  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    const job = await call<{
      status: string;
      result: VoiceResult | null;
      error: string | null;
    }>(`/api/voice/${id}`);
    if (job.status === 'done' && job.result) {
      return job.result;
    }
    if (job.status === 'error') {
      throw new Error(job.error || 'Не удалось распознать запись');
    }
  }
  throw new Error('Распознавание заняло слишком долго. Попробуй ещё раз');
}
