<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue';
import { sheetDock } from './sheetDock';
import { planBulkRemoval } from './bulkRemoval';
import AppHeader from './components/AppHeader.vue';
import SubjectChips from './components/SubjectChips.vue';
import BottomNav from './components/BottomNav.vue';
import ZoomControls from './components/ZoomControls.vue';
import TaskEditor from './components/TaskEditor.vue';
import OlympiadSheet from './components/OlympiadSheet.vue';
import ConfirmDialog from './components/ConfirmDialog.vue';
import ToastBar from './components/ToastBar.vue';
import UndoBar from './components/UndoBar.vue';
import EmptyState from './components/EmptyState.vue';
import MapView from './views/MapView.vue';
import CalendarView from './views/CalendarView.vue';
import OlympiadsView from './views/OlympiadsView.vue';
import SettingsView from './views/SettingsView.vue';
import noteAddIcon from './assets/icons/note-add.svg?raw';
import AttachSheet from './components/AttachSheet.vue';
import NoteSheet from './components/NoteSheet.vue';
import { unlinkFile, addLink, attachFile, createNote, createOlympiad, createTask, deleteNote, deleteOlympiad, deleteFile, deleteLink, deleteTask, deleteObjects, fileUrl, markDone, markUndone, saveFilePosition, saveLinkPosition, saveNotePosition, savePosition, setRegistered, updateNote, updateOlympiad, updateTask, uploadFile, uploadLooseFile, type TaskFields } from './api';
import { loadFromApi, loadMock, newId, normUrl, reload, removeTask, serverFileId, serverLinkId, serverNoteId, saveOlympiad, saveTask, state, subjects, toast, toggleDone, toggleRegistered, offerUndo, runUndo, stageRemoval, flushUndo, activeTasks, olympiadFromApi, olympiadToApi, removeOlympiad, type Tab } from './store';
import type { FileItem, Olympiad, Task } from './types';
import { moveFile, moveTask, navCollapsed, navigationInset, toggleNavigation } from './store';
import { fileCardSize, findGraphSpot, graphObstacles } from './graphPlacement';
import { attachLinkToTask } from './api';
import { createAttachmentQueue, linkAttachmentLocally } from './attachments';
const map = ref<InstanceType<typeof MapView>>();
const editing = ref<Task | null>(null);
const creating = ref(false);
const olympiad = ref<Olympiad | null>(null);
const creatingOlympiad = ref(false);
const confirmDelete = ref<Task | null>(null);
const desktopQuery = window.matchMedia('(min-width: 1024px)');
sheetDock.desktop.value = desktopQuery.matches;
const onDesktopChange = () => {
  sheetDock.desktop.value = desktopQuery.matches;
  if (desktopQuery.matches) {
    const latest = sheetDock.panels[sheetDock.panels.length - 1];
    if (latest) {
      sheetDock.activate(latest.id);
    }
  }
};
onMounted(() => desktopQuery.addEventListener('change', onDesktopChange));
onBeforeUnmount(() => {
  desktopQuery.removeEventListener('change', onDesktopChange);
  document.documentElement.style.removeProperty('--panel-w');
});
watchEffect(() => document.documentElement.style.setProperty('--panel-w', `${sheetDock.inset.value}px`));
watch(() => state.tab, () => sheetDock.collapseAll(), { flush: 'sync' });
const select = (tab: Tab) => { state.tab = tab; };
const edit = (t: Task) => { creating.value = false; editing.value = t; sheetDock.activate('task'); };
const openOlympiad = (o: Olympiad) => { creatingOlympiad.value = false; olympiad.value = o; sheetDock.activate('olympiad'); };
const closeEditor = () => { editing.value = null; creating.value = false; };
const MOCK = import.meta.env.VITE_MOCK === '1';
const busy = ref(false);
const attachmentQueue = createAttachmentQueue();
async function save(t: Task, uploads: File[] = []) {
  if (busy.value) {
    return;
  }
  const oldFileIds = new Set(state.tasks.flatMap((task) => task.files.map((f) => f.id)));
  const wantedLinks = new Set(t.files.filter((f) => f.type === 'link').map((f) => normUrl(f.url ?? f.name)));
  const kept = new Set(t.files.map((f) => f.id));
  const removed = (creating.value ? [] : state.tasks.find((x) => x.id === t.id)?.files ?? []).filter((f) => {
    if (f.type === 'link') {
      return !wantedLinks.has(normUrl(f.url ?? f.name));
    }
    return f.type !== 'note' && !kept.has(f.id);
  });
  if (!MOCK) {
    const fields: TaskFields = {
      title: t.title, subject: t.subject, kind: t.kind, due_at: t.due_at, location: t.location, note: t.note, reg_deadline: t.reg_deadline,
      duration_min: t.duration_min, registered: t.registered,
    };
    busy.value = true;
    try {
      const row = creating.value ? await createTask(fields) : await updateTask(t.id, fields);
      const prev = creating.value ? [] : (state.tasks.find((x) => x.id === t.id)?.files ?? []).filter((f) => f.type === 'link');
      const want = [...new Set(t.files.filter((f) => f.type === 'link').map((f) => normUrl(f.url ?? f.name)))]
        .filter((u): u is string => !!u);
      for (const u of want) {
        if (!prev.some((f) => f.url === u)) {
          await addLink(row.id, u);
        }
      }
      for (const file of uploads) {
        await uploadFile(row.id, file);
      }
      await reload();
      for (const f of removed) {
        queueFileRemoval(f, row.id);
      }
      closeEditor();
      await settleFiles(state.tasks.find((task) => task.id === row.id)?.files.filter((f) => !oldFileIds.has(f.id)) ?? [], row.id);
      toast('Сохранено');
      return;
    }
    catch (e) {
      toast(e instanceof Error && e.message.includes('20 МБ') ? e.message : 'Не сохранилось, попробуйте ещё раз');
      return;
    }
    finally {
      busy.value = false;
    }
  }
  saveTask(t);
  for (const f of removed) {
    queueFileRemoval(f, t.id);
  }
  closeEditor();
  await settleFiles(t.files.filter((f) => !oldFileIds.has(f.id)), t.id);
  toast('Сохранено');
}
async function done(t: Task) {
  const wasActive = t.status === 'active';
  if (!MOCK) {
    try {
      if (wasActive) {
        await markDone(t.id);
      }
      else {
        await markUndone(t.id);
      }
    }
    catch {
      toast('Не получилось, попробуйте ещё раз');
      return;
    }
  }
  toggleDone(t.id);
  closeEditor();
  if (wasActive) {
    offerUndo({ title: 'Сделано', detail: t.title, revert: () => undoDone(t) });
  }
  else {
    toast('Вернул в работу');
  }
}
async function undoDone(t: Task) {
  if (!MOCK) {
    try {
      await markUndone(t.id);
    }
    catch {
      toast('Не получилось вернуть');
      return;
    }
  }
  if (state.tasks.find((x) => x.id === t.id)?.status === 'done') {
    toggleDone(t.id);
  }
  toast('Вернул в работу');
}
const newItem = () => {
  if (state.tab === 'olympiads') {
    olympiad.value = null;
    creatingOlympiad.value = true;
    sheetDock.activate('olympiad');
  }
  else {
    editing.value = null;
    creating.value = true;
    sheetDock.activate('task');
  }
};
function remove() {
  const t = confirmDelete.value;
  confirmDelete.value = null;
  if (!t) {
    return;
  }
  const index = state.tasks.findIndex((x) => x.id === t.id);
  stageRemoval({
    title: 'Задание удалено', detail: t.title,
    hide: () => removeTask(t.id),
    restore: () => {
      if (!state.tasks.some((x) => x.id === t.id)) {
        state.tasks.splice(Math.max(0, index), 0, t);
      }
    },
    commit: () => {
      if (MOCK) {
        return undefined;
      }
      return deleteTask(t.id);
    },
  });
  closeEditor();
}
const preview = ref<string | null>(null);
function removeSelected(selection: {
  tasks: Task[];
  files: FileItem[];
}) {
  const count = selection.tasks.length + selection.files.length;
  if (!count) {
    return;
  }
  if (count > 500) {
    toast('Выдели не больше 500 объектов за раз');
    return;
  }
  const ids = {
    tasks: selection.tasks.map((t) => t.id),
    files: selection.files.map(serverFileId).filter((id): id is number => id !== null),
    notes: selection.files.map(serverNoteId).filter((id): id is number => id !== null),
    links: selection.files.map(serverLinkId).filter((id): id is number => id !== null),
  };
  const plan = planBulkRemoval(state, selection);
  stageRemoval({
    title: 'Объекты удалены', detail: `Объектов: ${count}`, ...plan, missingIsSuccess: false,
    commit: () => {
      if (MOCK) {
        return undefined;
      }
      return deleteObjects(ids);
    },
  });
  if (editing.value && selection.tasks.some((t) => t.id === editing.value?.id)) {
    closeEditor();
  }
  if (noteEditing.value && selection.files.some((f) => f.id === noteEditing.value?.id)) {
    closeNote();
  }
}
async function openFile(f: FileItem) {
  if (f.type === 'note') {
    noteEditing.value = f;
    return;
  }
  if (f.type === 'link' && f.url) {
    window.open(f.url, '_blank', 'noopener');
    return;
  }
  const id = serverFileId(f);
  if (!id) {
    return;
  }
  try {
    const url = await fileUrl(id);
    if (f.type === 'photo') {
      preview.value = url;
    }
    else {
      const a = document.createElement('a');
      a.href = url;
      a.download = f.name;
      a.click();
    }
  }
  catch {
    toast('Файл не открылся');
  }
}
async function moved(t: Task) {
  if (MOCK || t.x === null || t.y === null) {
    return;
  }
  try {
    await savePosition(t.id, t.x, t.y);
  }
  catch {
    toast('Позиция не сохранилась');
  }
}
async function movedFile(f: FileItem) {
  if (MOCK || f.x === null || f.y === null) {
    return;
  }
  const linkId = serverLinkId(f);
  const fileId = serverFileId(f);
  const noteId = serverNoteId(f);
  try {
    if (linkId && f.task_id) {
      await saveLinkPosition(f.task_id, linkId, f.x, f.y);
    }
    else if (fileId) {
      await saveFilePosition(fileId, f.x, f.y);
    }
    else if (noteId) {
      await saveNotePosition(noteId, f.x, f.y);
    }
  }
  catch {
    toast('Позиция не сохранилась');
  }
}
const attaching = ref<Task | null>(null);
const noteEditing = ref<FileItem | null>(null);
const creatingNote = ref<{
  taskId: number | null;
} | null>(null);
async function run(action: () => Promise<unknown>, ok: string) {
  if (busy.value) {
    return false;
  }
  busy.value = true;
  try {
    await action();
    await reload();
    toast(ok);
    return true;
  }
  catch (e) {
    toast(e instanceof Error && e.message.includes('20 МБ') ? e.message : 'Не получилось, попробуйте ещё раз');
    return false;
  }
  finally {
    busy.value = false;
  }
}
const demoOnly = () => { toast('В демо-режиме файлы не сохраняются'); return false; };
function freeFilePosition(type: FileItem['type'], taskId: number | null, ignoreId?: number) {
  if (map.value) {
    return map.value.freeSpot(type, taskId, ignoreId);
  }
  const obstacles = graphObstacles(state.tasks, state.loose).filter((r) => r.key !== `f${ignoreId}`);
  const owner = obstacles.find((r) => r.key === `t${taskId}`);
  return findGraphSpot(fileCardSize(type), obstacles, owner ? { x: owner.x + owner.w + 24, y: owner.y } : { x: 40, y: 140 }, owner);
}
async function settleFiles(items: FileItem[], taskId: number | null, options: {
  fromCurrent?: boolean;
  persist?: boolean;
} = {}) {
  const files = [...new Map(items.map((f) => [f.id, f])).values()];
  if (!files.length) {
    return;
  }
  if (map.value) {
    await map.value.placeFiles(files, taskId, options);
    return;
  }
  for (const f of files) {
    const p = freeFilePosition(f.type, taskId, f.id);
    moveFile(f, p.x, p.y);
    if (options.persist !== false) {
      await movedFile(f);
    }
  }
}
const currentFiles = () => [...state.loose, ...state.tasks.flatMap((t) => t.files)];
async function attachFiles(files: File[]) {
  const t = attaching.value;
  if (!t) {
    return;
  }
  if (MOCK) {
    attaching.value = null;
    demoOnly();
    return;
  }
  const ids = new Set<number>();
  if (await run(async () => {
    for (const f of files) {
      ids.add((await uploadFile(t.id, f)).id);
    }
  }, 'Прикрепил')) {
    attaching.value = null;
    await settleFiles(currentFiles().filter((f) => ids.has(serverFileId(f) ?? -1)), t.id);
  }
}
async function attachLink(url: string) {
  const t = attaching.value;
  if (!t) {
    return;
  }
  const u = normUrl(url);
  if (!u) {
    toast('Это не похоже на ссылку');
    return;
  }
  if (MOCK) {
    const item: FileItem = { id: newId(), task_id: t.id, type: 'link', name: u.replace(/^https?:\/\//, ''), url: u, x: null, y: null };
    t.files.push(item);
    attaching.value = null;
    await settleFiles([item], t.id);
    return;
  }
  let id = 0;
  if (await run(async () => { id = (await addLink(t.id, u)).link.id; }, 'Ссылка добавлена')) {
    attaching.value = null;
    await settleFiles(currentFiles().filter((f) => serverLinkId(f) === id), t.id);
  }
}
async function attachNote(text: string) {
  const t = attaching.value;
  if (!t) {
    return;
  }
  attaching.value = null;
  await saveNote({ text, task_id: t.id }, null);
}
function newNote() { creatingNote.value = { taskId: null }; }
const closeNote = () => { noteEditing.value = null; creatingNote.value = null; };
function placeNoteLocally(item: FileItem, taskId: number | null) {
  state.loose = state.loose.filter((f) => f.id !== item.id);
  for (const t of state.tasks) {
    t.files = t.files.filter((f) => f.id !== item.id);
  }
  item.task_id = taskId;
  const owner = taskId === null ? null : state.tasks.find((t) => t.id === taskId);
  if (owner) {
    owner.files.push(item);
  }
  else {
    state.loose.push(item);
  }
}
async function saveNote(n: {
  text: string;
  task_id: number | null;
}, existing: FileItem | null) {
  if (MOCK) {
    const item = existing ?? { id: newId(), task_id: null, type: 'note' as const, name: '', x: null, y: null };
    item.text = n.text;
    item.name = n.text.split('\n')[0].slice(0, 60);
    if (!existing) {
      Object.assign(item, freeFilePosition('note', n.task_id));
    }
    placeNoteLocally(item, n.task_id);
    closeNote();
    if (!existing) {
      await settleFiles([item], n.task_id);
    }
    return;
  }
  const id = existing ? serverNoteId(existing) : null;
  const where = existing ? undefined : freeFilePosition('note', n.task_id);
  let createdId = 0;
  const ok = await run(async () => {
    if (id) {
      await updateNote(id, n);
    }
    else {
      createdId = (await createNote({ ...n, ...where })).id;
    }
  }, existing ? 'Сохранено' : 'Заметка добавлена');
  if (ok) {
    closeNote();
    if (!existing) {
      await settleFiles(currentFiles().filter((f) => serverNoteId(f) === createdId), n.task_id);
    }
  }
}
function queueFileRemoval(item: FileItem, taskId?: number) {
  const owners = taskId === undefined
    ? state.tasks.filter((t) => t.files.some((f) => f.id === item.id)).map((t) => ({ id: t.id, index: t.files.findIndex((f) => f.id === item.id) }))
    : [{ id: taskId, index: state.tasks.find((t) => t.id === taskId)?.files.findIndex((f) => f.id === item.id) ?? -1 }];
  const looseIndex = taskId === undefined ? state.loose.findIndex((f) => f.id === item.id) : -1;
  stageRemoval({
    title: item.type === 'note' ? 'Заметка удалена' : item.type === 'link' ? 'Ссылка удалена' : 'Файл удалён', detail: item.name,
    hide: () => {
      for (const t of state.tasks) {
        if (taskId === undefined || t.id === taskId) {
          t.files = t.files.filter((f) => f.id !== item.id);
        }
      }
      if (taskId === undefined) {
        state.loose = state.loose.filter((f) => f.id !== item.id);
      }
    },
    restore: () => {
      for (const owner of owners) {
        const t = state.tasks.find((x) => x.id === owner.id);
        if (t && !t.files.some((f) => f.id === item.id)) {
          t.files.splice(owner.index < 0 ? t.files.length : owner.index, 0, item);
        }
      }
      if (looseIndex >= 0 && !state.loose.some((f) => f.id === item.id)) {
        state.loose.splice(looseIndex, 0, item);
      }
    },
    commit: () => {
      if (MOCK) {
        return;
      }
      const noteId = serverNoteId(item);
      const linkId = serverLinkId(item);
      const fileId = serverFileId(item);
      if (noteId) {
        return deleteNote(noteId);
      }
      if (linkId && taskId !== undefined) {
        return deleteLink(taskId, linkId);
      }
      if (fileId) {
        if (taskId === undefined) {
          return deleteFile(fileId);
        }
        return unlinkFile(fileId, taskId, true);
      }
    },
  });
}
function removeNote(item: FileItem) {
  queueFileRemoval(item);
  closeNote();
}
async function attachTo(item: FileItem, task: Task, original: {
  x: number;
  y: number;
}) {
  await attachmentQueue.enqueue(item.id, async () => {
    const current = currentFiles().find((f) => f.id === item.id) ?? item;
    const change = linkAttachmentLocally(state, current, task.id);
    if (!change) {
      toast('Задание больше недоступно');
      return;
    }
    const animation = settleFiles([change.file], task.id, { fromCurrent: true, persist: false });
    try {
      if (!MOCK && !change.alreadyAttached) {
        const noteId = serverNoteId(current);
        const fileId = serverFileId(current);
        const linkId = serverLinkId(current);
        if (noteId) {
          await updateNote(noteId, { task_id: task.id });
        }
        else if (fileId) {
          await attachFile(fileId, task.id);
        }
        else if (linkId) {
          await attachLinkToTask(task.id, linkId);
        }
        else {
          throw new Error('unknown_attachment');
        }
      }
      await animation;
      const refreshed = currentFiles().find((f) => f.id === item.id);
      if (refreshed && !state.tasks.find((t) => t.id === task.id)?.files.some((f) => f.id === item.id)) {
        linkAttachmentLocally(state, refreshed, task.id);
      }
      await movedFile(change.file);
      toast(`Прикрепил к «${task.title.slice(0, 30)}»`);
    }
    catch {
      map.value?.stopMotion();
      change.rollback();
      moveFile(current, original.x, original.y);
      await movedFile(current);
      toast('Не удалось прикрепить. Объект возвращён на прежнее место');
    }
  });
}
function detach(item: FileItem, task: Task) {
  if (item.type === 'link') {
    queueFileRemoval(item, task.id);
    return;
  }
  const index = task.files.findIndex((f) => f.id === item.id);
  const wasLoose = state.loose.some((f) => f.id === item.id);
  stageRemoval({
    title: 'Связь убрана', detail: item.name,
    hide: () => {
      const owner = state.tasks.find((t) => t.id === task.id);
      if (owner) {
        owner.files = owner.files.filter((f) => f.id !== item.id);
      }
      if (!state.tasks.some((t) => t.files.some((f) => f.id === item.id)) && !state.loose.some((f) => f.id === item.id)) {
        state.loose.push({ ...item, task_id: null });
      }
    },
    restore: () => {
      if (!wasLoose) {
        state.loose = state.loose.filter((f) => f.id !== item.id);
      }
      const owner = state.tasks.find((t) => t.id === task.id);
      if (owner && !owner.files.some((f) => f.id === item.id)) {
        owner.files.splice(Math.max(0, index), 0, item);
      }
    },
    commit: () => {
      if (MOCK) {
        return;
      }
      const noteId = serverNoteId(item);
      const fileId = serverFileId(item);
      if (noteId) {
        return updateNote(noteId, { task_id: null });
      }
      if (fileId) {
        return unlinkFile(fileId, task.id);
      }
    },
  });
}
async function dropFiles(files: File[], task: Task | null, at: {
  x: number;
  y: number;
}) {
  if (MOCK) {
    demoOnly();
    return;
  }
  const ids = new Set<number>();
  const ok = await run(async () => {
    for (const [i, f] of files.entries()) {
      if (task) {
        ids.add((await uploadFile(task.id, f)).id);
      }
      else {
        ids.add((await uploadLooseFile(f, at.x + i * 24, at.y + i * 24)).id);
      }
    }
  }, task ? 'Прикрепил' : files.length > 1 ? 'Файлы на карте' : 'Файл на карте');
  if (ok) {
    await settleFiles(currentFiles().filter((f) => ids.has(serverFileId(f) ?? -1)), task?.id ?? null);
  }
}
function arranged(before: {
  tasks: {
    t: Task;
    x: number;
    y: number;
  }[];
  files: {
    f: FileItem;
    x: number;
    y: number;
  }[];
  restoreView: () => void;
}) {
  offerUndo({
    title: 'Разложил по предметам',
    detail: `Карточек: ${before.tasks.length + before.files.length}`,
    revert: () => {
      for (const { t, x, y } of before.tasks) {
        moveTask(t.id, x, y);
        moved(t);
      }
      for (const { f, x, y } of before.files) {
        moveFile(f, x, y);
        movedFile(f);
      }
      before.restoreView();
      toast('Вернул как было');
    },
  });
}
const closeOly = () => { olympiad.value = null; creatingOlympiad.value = false; };
async function saveOly(o: Olympiad) {
  if (busy.value) {
    return;
  }
  const isNew = creatingOlympiad.value;
  if (!MOCK) {
    busy.value = true;
    try {
      const row = isNew ? await createOlympiad(olympiadToApi(o)) : await updateOlympiad(o.id, olympiadToApi(o));
      o = olympiadFromApi(row);
    }
    catch {
      toast('Не сохранилось, попробуйте ещё раз');
      return;
    }
    finally {
      busy.value = false;
    }
  }
  saveOlympiad(o);
  closeOly();
  toast(isNew ? 'Олимпиада добавлена' : 'Сохранено');
}
async function register(o: Olympiad) {
  if (!MOCK) {
    try {
      await setRegistered(o.id, !o.registered);
    }
    catch {
      toast('Не получилось, попробуйте ещё раз');
      return;
    }
  }
  toggleRegistered(o.id);
}
const confirmOly = ref<Olympiad | null>(null);
function removeOly() {
  const o = confirmOly.value;
  confirmOly.value = null;
  if (!o) {
    return;
  }
  const index = state.olympiads.findIndex((x) => x.id === o.id);
  stageRemoval({
    title: 'Олимпиада удалена', detail: o.name,
    hide: () => removeOlympiad(o.id),
    restore: () => {
      if (!state.olympiads.some((x) => x.id === o.id)) {
        state.olympiads.splice(Math.max(0, index), 0, o);
      }
    },
    commit: () => {
      if (MOCK) {
        return undefined;
      }
      return deleteOlympiad(o.id);
    },
  });
  closeOly();
}
onMounted(() => {
  if (MOCK) {
    loadMock();
  }
  else {
    loadFromApi();
  }
});
let lastSync = Date.now();
async function syncIfIdle() {
  if (MOCK || document.visibilityState !== 'visible' || busy.value || attachmentQueue.size || state.error) {
    return;
  }
  if (editing.value || creating.value || olympiad.value || creatingOlympiad.value || noteEditing.value || creatingNote.value || attaching.value) {
    return;
  }
  if (Date.now() - lastSync < 5000) {
    return;
  }
  lastSync = Date.now();
  try {
    await reload();
  }
  catch { }
}
onMounted(() => {
  document.addEventListener('visibilitychange', syncIfIdle);
  window.addEventListener('focus', syncIfIdle);
  window.addEventListener('pagehide', flushUndo);
});
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', syncIfIdle);
  window.removeEventListener('focus', syncIfIdle);
  window.removeEventListener('pagehide', flushUndo);
});
</script>

<template>
  <div class="app" :class="{ 'nav-collapsed': navCollapsed }" :style="{ '--nav-space': navigationInset + 'px' }">
    <aside class="side">
      <div class="side-head">
        <AppHeader class="brand" :compact="navCollapsed" />
        <button class="side-toggle" :aria-label="navCollapsed ? 'Развернуть навигацию' : 'Свернуть навигацию'" :title="navCollapsed ? 'Развернуть навигацию' : 'Свернуть навигацию'" :aria-expanded="!navCollapsed" aria-controls="sidebar-nav" @click="toggleNavigation">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6" /></svg>
        </button>
      </div>
      <BottomNav id="sidebar-nav" vertical :compact="navCollapsed" :tab="state.tab" @select="select" />
    </aside>

    <main class="main">
      <Transition name="view" mode="out-in">
      <MapView v-if="state.tab === 'map'" ref="map" @edit="edit" @attach="(t) => (attaching = t)" @done="done" @moved="moved" @moved-file="movedFile" @arranged="arranged"
               @open-file="openFile" @attach-to="attachTo" @detach="detach" @drop-files="dropFiles" @remove-selected="removeSelected" />
      <CalendarView v-else-if="state.tab === 'calendar'" @open="edit" @open-olympiad="openOlympiad" />
      <SettingsView v-else-if="state.tab === 'settings'" />
      <OlympiadsView v-else @add="newItem" @open="openOlympiad" @register="register" />
      </Transition>

      <header v-if="state.tab === 'map'" class="top">
        <SubjectChips :subjects="subjects" :active="state.filter" @select="(s) => (state.filter = s)" />
      </header>
      <EmptyState v-if="state.tab === 'map' && !state.loading && !state.error && !activeTasks.length" />
      <p v-if="state.error" class="error">{{ state.error }}</p>
      <button v-if="state.tab === 'map' || state.tab === 'calendar'" class="fab" :class="{ 'calendar-fab': state.tab === 'calendar' }" aria-label="Новое дело" title="Новое дело" @click="newItem"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg></button>
      <button v-if="state.tab === 'map'" class="fabnote" aria-label="Добавить заметку" title="Добавить заметку" @click="newNote"><span class="note-icon" aria-hidden="true" v-html="noteAddIcon"></span></button>
      <ZoomControls v-if="state.tab === 'map'" class="zoom" @in="map?.zoomBy(1.25)" @out="map?.zoomBy(0.8)" @fit="map?.fit()" />
    </main>
    <BottomNav class="bottom-nav" :tab="state.tab" @select="select" />

    <TaskEditor v-if="editing || creating" :key="editing?.id ?? 'new'" :task="editing" @close="closeEditor" @save="save" @done="done" @remove="(t) => (confirmDelete = t)" />
    <OlympiadSheet v-if="olympiad || creatingOlympiad" :key="olympiad?.id ?? 'new'" :olympiad="olympiad" @close="closeOly" @save="saveOly" @remove="(o) => (confirmOly = o)" />
    <ConfirmDialog v-if="confirmDelete" question="Удалить задание?" confirm-label="Удалить" danger @cancel="confirmDelete = null" @confirm="remove" />
    <ConfirmDialog v-if="confirmOly" question="Удалить олимпиаду?" confirm-label="Удалить" danger @cancel="confirmOly = null" @confirm="removeOly" />
    <AttachSheet v-if="attaching" :task="attaching" @close="attaching = null" @files="attachFiles" @link="attachLink" @note="attachNote" />
    <NoteSheet v-if="noteEditing || creatingNote" :key="noteEditing?.id ?? 'new'" :note="noteEditing" :task-id="creatingNote?.taskId"
               @close="closeNote" @save="(n) => saveNote(n, noteEditing)" @remove="removeNote" />
    <UndoBar @undo="runUndo" />
    <ToastBar :text="state.toast" />
    <div v-if="preview" class="lightbox" @click="preview = null"><img :src="preview" alt="" /></div>
  </div>
</template>

<style scoped>
.app {
    position: fixed;
    inset: 0;
    overflow: hidden;
    background: var(--screen);
}
.main {
    position: absolute;
    inset: 0;
}
.side {
    display: none;
}
.top {
    position: absolute;
    left: 0;
    right: 0;
    top: calc(12px + var(--safe-top));
    padding: 0 16px;
    display: grid;
    gap: 13px;
    pointer-events: none;
    z-index: 5;
}
.top > * {
    pointer-events: auto;
}
.top :deep(.chips) {
    margin: 0 -16px;
    padding: 0 16px;
}
.top :deep(.chips) {
    pointer-events: none;
    user-select: none;
    -webkit-user-select: none;
}
.top :deep(.chip) {
    pointer-events: auto;
}
.error {
    position: absolute;
    left: 24px;
    right: 24px;
    top: 38%;
    text-align: center;
    color: var(--danger);
    margin: 0;
    z-index: 4;
}
.lightbox {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: rgba(0, 0, 0, 0.92);
    display: grid;
    place-items: center;
    padding: 16px;
}
.lightbox img {
    max-width: 100%;
    max-height: 100%;
    border-radius: 18px;
}
.fab {
    position: absolute;
    left: 18px;
    bottom: calc(84px + var(--safe-bottom));
    width: 50px;
    height: 50px;
    z-index: 6;
    border-radius: 50%;
    background: var(--action-fill, var(--accent));
    color: #fff;
    display: grid;
    place-items: center;
    box-shadow: var(--glass-shadow);
}
.fab svg {
    width: 28px;
    height: 28px;
    fill: none;
    stroke: currentColor;
    stroke-width: 3;
    stroke-linecap: round;
    transition: rotate 0.25s var(--spring);
}
@media (hover: hover) {
    .fab:hover svg {
        rotate: 90deg;
    }
}
.fabnote {
    position: absolute;
    left: 22px;
    bottom: calc(144px + var(--safe-bottom));
    width: 42px;
    height: 42px;
    z-index: 6;
    border-radius: 50%;
    background: var(--glass-background);
    border: 1px solid var(--bar-line);
    display: grid;
    place-items: center;
}
.note-icon {
    width: 20px;
    height: 20px;
    display: grid;
    place-items: center;
}
.note-icon :deep(svg) {
    width: 100%;
    height: 100%;
}
.zoom {
    position: absolute;
    right: 18px;
    bottom: calc(84px + var(--safe-bottom));
    z-index: 6;
}
.bottom-nav {
    position: absolute;
    left: 14px;
    right: 14px;
    bottom: calc(10px + var(--safe-bottom));
    z-index: 6;
}

@media (min-width: 720px) and (max-width: 1023px) {
    .app {
        max-width: 900px;
        left: 50%;
        right: auto;
        width: 100%;
        transform: translateX(-50%);
    }
}

@media (min-width: 1024px) {
    .side {
        display: flex;
        flex-direction: column;
        gap: 14px;
        position: absolute;
        left: 12px;
        top: 12px;
        bottom: 12px;
        width: calc(var(--nav-space) - 28px);
        padding: 18px 14px;
        border: 1px solid var(--bar-line);
        border-radius: 30px;
        background: var(--side-bg);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        box-shadow: var(--panel-shadow);
        z-index: 7;
        transition:
            width 0.2s var(--ease-out),
            padding 0.2s var(--ease-out);
    }
    .side-head {
        display: flex;
        align-items: center;
        gap: 8px;
        min-width: 0;
    }
    .brand {
        flex: 1;
        padding-left: 14px;
    }
    .side-toggle {
        width: 30px;
        height: 30px;
        border-radius: 50%;
        display: grid;
        place-items: center;
        flex: none;
        color: var(--soft);
    }
    .side-toggle svg {
        width: 17px;
        height: 17px;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        stroke-linecap: round;
        stroke-linejoin: round;
    }
    .side-toggle:hover {
        background: var(--glass-hover);
        color: var(--ink);
    }
    .side-toggle:focus-visible {
        outline: 2px solid var(--accent);
        outline-offset: 2px;
    }
    .nav-collapsed .side {
        bottom: auto;
        padding: 18px 10px;
    }
    .nav-collapsed .side-head {
        flex-direction: column;
        gap: 4px;
    }
    .nav-collapsed .brand {
        flex: none;
        padding-left: 0;
    }
    .nav-collapsed .side-toggle svg {
        rotate: 180deg;
    }
    .main {
        left: 0;
    }
    .bottom-nav {
        display: none;
    }
    .top {
        top: 20px;
        left: var(--nav-space);
        padding: 0 20px;
    }
    .top :deep(.chips) {
        margin: 0;
        padding: 0;
        flex-wrap: wrap;
    }
    .zoom,
    .fab,
    .fabnote {
        transition: right 0.22s var(--ease-out);
    }
    .zoom {
        right: calc(24px + var(--panel-w, 0px));
        bottom: 24px;
    }
    .fab {
        left: auto;
        right: calc(170px + var(--panel-w, 0px));
        bottom: 24px;
    }
    .fab.calendar-fab {
        right: calc(24px + var(--panel-w, 0px));
    }
    .fabnote {
        left: auto;
        right: calc(232px + var(--panel-w, 0px));
        bottom: 28px;
    }
    @media (hover: hover) {
        .fabnote:hover {
            border-color: var(--accent);
        }
    }
}
</style>
