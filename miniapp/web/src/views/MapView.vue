<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import TaskCard from '../components/TaskCard.vue';
import FileCard from '../components/FileCard.vue';
import { activeTasks, fresh, groupOf, look, moveFile, moveTask, navigationInset, state, visibleTasks } from '../store';
import type { FileItem, Task } from '../types';
import { graphConnection } from '../graphEdges';
import { arrangeAttachments, arrangeGraph } from '../graphLayout';
import { planGraphSelection } from '../graphSelection';
import { didDrag, pickDropTask } from '../graphDrop';
import { createGraphMotion } from '../graphMotion';
import { fileCardSize, findGraphSpot, graphObstacles, type GraphObstacle } from '../graphPlacement';
const emit = defineEmits<{
  edit: [Task];
  attach: [Task];
  done: [Task];
  moved: [Task];
  movedFile: [FileItem];
  openFile: [FileItem];
  attachTo: [
    FileItem,
    Task,
    {
      x: number;
      y: number;
    }
  ];
  dropFiles: [
    File[],
    Task | null,
    {
      x: number;
      y: number;
    }
  ];
  detach: [FileItem, Task];
  arranged: [
    {
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
    }
  ];
  removeSelected: [
    {
      tasks: Task[];
      files: FileItem[];
    }
  ];
}>();
defineExpose({ zoomBy, fit, worldCenter, arrange, freeSpot, placeFiles, stopMotion: () => motion.stop() });
const viewport = ref<HTMLElement>();
const threadsSvg = ref<SVGSVGElement>();
const view = reactive({ x: 0, y: 0, s: 1 });
const motion = createGraphMotion({ now: () => performance.now(), request: (step) => requestAnimationFrame(step), cancel: cancelAnimationFrame });
const sizes = reactive<Record<string, {
  w: number;
  h: number;
}>>({});
const cardRects = reactive<Record<string, {
  x: number;
  y: number;
  w: number;
  h: number;
  radius: number;
  cornerPower: number;
}>>({});
const els = new Map<string, HTMLElement>();
const MIN = 0.25;
const MAX = 2.5;
const PHONE_SCALE = 0.7;
type Placed = {
  key: string;
  task?: Task;
  file?: FileItem;
  x: number;
  y: number;
  auto?: boolean;
};
const placed = computed(() => {
  const out: Placed[] = [];
  const seen = new Set<number>();
  const TASK_SIZE = { w: 252, h: 220 };
  const taken: GraphObstacle[] = [];
  for (const t of activeTasks.value) {
    if (t.x !== null && t.y !== null) {
      taken.push({ key: `t${t.id}`, x: t.x, y: t.y, ...TASK_SIZE });
    }
    for (const f of t.files) {
      if (f.x !== null && f.y !== null) {
        taken.push({ key: `f${f.id}`, x: f.x, y: f.y, ...fileCardSize(f.type) });
      }
    }
  }
  for (const f of state.loose) {
    if (f.x !== null && f.y !== null) {
      taken.push({ key: `f${f.id}`, x: f.x, y: f.y, ...fileCardSize(f.type) });
    }
  }
  for (const t of visibleTasks.value) {
    if (t.x !== null && t.y !== null) {
      out.push({ key: `t${t.id}`, task: t, x: t.x, y: t.y });
      continue;
    }
    const spot = findGraphSpot(TASK_SIZE, taken, { x: 40, y: 140 });
    taken.push({ key: `t${t.id}`, ...spot, ...TASK_SIZE });
    out.push({ key: `t${t.id}`, task: t, ...spot, auto: true });
  }
  const obstacles = out.map((p) => ({ key: p.key, x: p.x, y: p.y, w: 252, h: 240 }));
  const files: {
    file: FileItem;
    owner?: typeof obstacles[number];
  }[] = [];
  for (const t of visibleTasks.value) {
    for (const file of t.files) {
      if (seen.has(file.id)) {
        continue;
      }
      seen.add(file.id);
      files.push({ file, owner: obstacles.find((r) => r.key === `t${t.id}`) });
    }
  }
  for (const file of state.loose) {
    if (!seen.has(file.id)) {
      seen.add(file.id);
      files.push({ file });
    }
  }
  for (const { file: f } of files) {
    if (f.x != null && f.y != null) {
      obstacles.push({ key: `f${f.id}`, x: f.x, y: f.y, ...fileCardSize(f.type) });
    }
  }
  for (const { file: f, owner } of files) {
    const position = f.x != null && f.y != null ? { x: f.x, y: f.y }
      : findGraphSpot(fileCardSize(f.type), obstacles, owner ? { x: owner.x + owner.w + 24, y: owner.y } : { x: 620, y: 140 }, owner);
    if (f.x == null || f.y == null) {
      obstacles.push({ key: `f${f.id}`, ...position, ...fileCardSize(f.type) });
    }
    out.push({ key: `f${f.id}`, file: f, ...position });
  }
  return out;
});
watch(placed, (list) => {
  for (const i of list) {
    if (i.auto && i.task) {
      moveTask(i.task.id, i.x, i.y);
      emit('moved', i.task);
    }
  }
}, { immediate: true });
const threads = computed(() => {
  const lines: {
    d: string;
    x1: number;
    y1: number;
    x2: number;
    y2: number;
    task: Task;
    file: FileItem;
    key: string;
  }[] = [];
  for (const t of visibleTasks.value) {
    const parent = cardRects[`t${t.id}`];
    if (!parent) {
      continue;
    }
    for (const f of t.files) {
      const child = cardRects[`f${f.id}`];
      if (!child) {
        continue;
      }
      const connection = graphConnection(parent, child, view.s);
      lines.push({ ...connection, task: t, file: f, key: `${t.id}-${f.id}` });
    }
  }
  return lines;
});
const CUT_MS = 600;
const hoverLine = ref<string | null>(null);
const cutting = ref<string | null>(null);
let cutTimer = 0;
function startCut(l: {
  key: string;
  task: Task;
  file: FileItem;
}, e: PointerEvent) {
  motion.stop();
  (e.target as Element).setPointerCapture?.(e.pointerId);
  cancelCut();
  cutting.value = l.key;
  cutTimer = window.setTimeout(() => {
    cutting.value = null;
    try {
      navigator.vibrate?.(15);
    }
    catch { }
    emit('detach', l.file, l.task);
  }, CUT_MS);
}
function cancelCut() { clearTimeout(cutTimer); cutting.value = null; }
function hoverThread(key: string, e: PointerEvent) {
  if (e.pointerType === 'mouse' && e.buttons === 0 && pointers.size === 0) {
    hoverLine.value = key;
  }
}
function measure() {
  const origin = threadsSvg.value?.getBoundingClientRect();
  if (!origin) {
    return;
  }
  els.forEach((el, key) => {
    sizes[key] = { w: el.offsetWidth, h: el.offsetHeight };
    const card = el.querySelector<HTMLElement>('[data-card]') ?? el;
    const bounds = card.getBoundingClientRect();
    const style = getComputedStyle(card);
    const radius = parseFloat(style.borderTopLeftRadius) || 0;
    const shape = style.getPropertyValue('corner-shape');
    cardRects[key] = {
      x: bounds.left - origin.left, y: bounds.top - origin.top,
      w: bounds.width, h: bounds.height,
      radius: radius * bounds.width / card.offsetWidth,
      cornerPower: /squircle|superellipse\(2\)/.test(shape) ? 4 : 2,
    };
  });
}
function setEl(key: string, el: unknown) {
  if (el instanceof HTMLElement) {
    els.set(key, el);
  }
  else {
    els.delete(key);
    delete cardRects[key];
  }
}
const selected = reactive(new Set<string>());
const arrangement = computed(() => planGraphSelection(visibleTasks.value, state.loose, selected));
const marquee = ref<null | {
  l: number;
  t: number;
  w: number;
  h: number;
}>(null);
const dropTarget = ref<string | null>(null);
function clearSelection() { selected.clear(); }
function removeSelected() {
  motion.stop();
  const items = placed.value.filter((item) => selected.has(item.key));
  emit('removeSelected', {
    tasks: items.filter((item) => item.task).map((item) => item.task!),
    files: items.filter((item) => item.file).map((item) => item.file!),
  });
  clearSelection();
}
function toggle(key: string) {
  if (selected.has(key)) {
    selected.delete(key);
  }
  else {
    selected.add(key);
  }
}
function selectInRect(g: {
  sx: number;
  sy: number;
  base: Set<string>;
}, x: number, y: number) {
  const l = Math.min(g.sx, x);
  const r = Math.max(g.sx, x);
  const t = Math.min(g.sy, y);
  const b = Math.max(g.sy, y);
  marquee.value = { l, t, w: r - l, h: b - t };
  const vr = viewport.value!.getBoundingClientRect();
  selected.clear();
  g.base.forEach((k) => selected.add(k));
  els.forEach((el, key) => {
    const c = el.getBoundingClientRect();
    const cl = c.left - vr.left;
    const ct = c.top - vr.top;
    if (cl < r && cl + c.width > l && ct < b && ct + c.height > t) {
      selected.add(key);
    }
  });
}
const pointers = new Map<number, {
  x: number;
  y: number;
}>();
type CardGesture = {
  type: 'card';
  key: string;
  sx: number;
  sy: number;
  moved: boolean;
  toggle: boolean;
  group: {
    key: string;
    ox: number;
    oy: number;
  }[];
};
let gesture: null | {
  type: 'pan';
  clear: boolean;
  sx: number;
  sy: number;
} | CardGesture | {
  type: 'held';
} | {
  type: 'select';
  sx: number;
  sy: number;
  key: string | null;
  moved: boolean;
  base: Set<string>;
} = null;
const HOLD_MS = 450;
let holdTimer = 0;
const buzz = () => {
  try {
    navigator.vibrate?.(15);
  }
  catch { }
};
function cancelHold() { clearTimeout(holdTimer); holdTimer = 0; }
function startHold(p: {
  x: number;
  y: number;
}) {
  cancelHold();
  holdTimer = window.setTimeout(() => {
    holdTimer = 0;
    const g = gesture;
    if (g?.type === 'card' && !g.moved) {
      toggle(g.key);
      gesture = { type: 'held' };
      buzz();
    }
    else if (g?.type === 'pan') {
      gesture = { type: 'select', sx: p.x, sy: p.y, key: null, moved: true, base: new Set(selected) };
      marquee.value = { l: p.x, t: p.y, w: 0, h: 0 };
      buzz();
    }
  }, HOLD_MS);
}
let pinch: null | {
  dist: number;
  s: number;
  cx: number;
  cy: number;
  vx: number;
  vy: number;
} = null;
function point(e: {
  clientX: number;
  clientY: number;
}) {
  const r = viewport.value!.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}
const toWorld = (p: {
  x: number;
  y: number;
}) => ({ x: (p.x - view.x) / view.s, y: (p.y - view.y) / view.s });
function onDown(e: PointerEvent) {
  hoverLine.value = null;
  cancelCut();
  motion.stop();
  if ((e.target as HTMLElement).closest('button')) {
    return;
  }
  const mouse = e.pointerType === 'mouse';
  if (mouse && e.button > 2) {
    return;
  }
  if (mouse && e.button === 1) {
    e.preventDefault();
  }
  const p = point(e);
  pointers.set(e.pointerId, p);
  viewport.value!.setPointerCapture(e.pointerId);
  if (pointers.size === 2) {
    cancelHold();
    marquee.value = null;
    dropTarget.value = null;
    const [a, b] = [...pointers.values()];
    pinch = { dist: Math.hypot(a.x - b.x, a.y - b.y), s: view.s, cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2, vx: view.x, vy: view.y };
    gesture = null;
    return;
  }
  const cardEl = (e.target as HTMLElement).closest('[data-key]') as HTMLElement | null;
  const key = cardEl?.dataset.key ?? null;
  const multi = mouse && (e.shiftKey || e.ctrlKey || e.metaKey);
  if (mouse && e.button === 2) {
    gesture = { type: 'select', sx: p.x, sy: p.y, key, moved: false, base: new Set(multi ? selected : []) };
  }
  else if (key && !(mouse && e.button === 1)) {
    const keys = selected.has(key) ? [...selected] : [key];
    const group = keys.map((k) => placed.value.find((i) => i.key === k)).filter((i): i is Placed => !!i)
      .map((i) => ({ key: i.key, ox: i.x, oy: i.y }));
    gesture = { type: 'card', key, sx: p.x, sy: p.y, moved: false, toggle: multi, group };
  }
  else {
    gesture = { type: 'pan', clear: mouse ? e.button === 0 && !multi : true, sx: p.x, sy: p.y };
  }
  if (!mouse) {
    startHold(p);
  }
}
function taskUnder(clientX: number, clientY: number, skip: Set<string>, dragged?: Placed): Task | null {
  const targets = placed.value.filter((p) => p.task && !skip.has(p.key)).flatMap((p) => {
    const r = els.get(p.key)?.getBoundingClientRect();
    if (r) {
      return [{ id: p.task!.id, left: r.left, top: r.top, right: r.right, bottom: r.bottom }];
    }
    return [];
  });
  const vr = viewport.value!.getBoundingClientRect();
  const sz = dragged ? sizes[dragged.key] ?? fileCardSize(dragged.file!.type) : null;
  const left = dragged ? vr.left + view.x + dragged.x * view.s : 0;
  const top = dragged ? vr.top + view.y + dragged.y * view.s : 0;
  const id = pickDropTask({ x: clientX, y: clientY }, dragged && sz ? { left, top, right: left + sz.w * view.s, bottom: top + sz.h * view.s } : null, targets);
  return visibleTasks.value.find((t) => t.id === id) ?? null;
}
function onMove(e: PointerEvent) {
  const prev = pointers.get(e.pointerId);
  if (!prev) {
    return;
  }
  const p = point(e);
  pointers.set(e.pointerId, p);
  if (holdTimer && gesture && 'sx' in gesture && Math.hypot(p.x - gesture.sx, p.y - gesture.sy) > 6) {
    cancelHold();
  }
  if (pinch && pointers.size >= 2) {
    const [a, b] = [...pointers.values()];
    const s = Math.min(MAX, Math.max(MIN, pinch.s * (Math.hypot(a.x - b.x, a.y - b.y) / pinch.dist)));
    const ratio = s / pinch.s;
    view.s = s;
    view.x = pinch.cx - (pinch.cx - pinch.vx) * ratio + ((a.x + b.x) / 2 - pinch.cx);
    view.y = pinch.cy - (pinch.cy - pinch.vy) * ratio + ((a.y + b.y) / 2 - pinch.cy);
    return;
  }
  if (!gesture || gesture.type === 'held') {
    return;
  }
  if (gesture.type === 'select') {
    if (!gesture.moved && Math.hypot(p.x - gesture.sx, p.y - gesture.sy) < 4) {
      return;
    }
    gesture.moved = true;
    selectInRect(gesture, p.x, p.y);
  }
  else if (gesture.type === 'pan') {
    if (Math.hypot(p.x - gesture.sx, p.y - gesture.sy) > 4) {
      gesture.clear = false;
    }
    view.x += p.x - prev.x;
    view.y += p.y - prev.y;
  }
  else {
    const g = gesture;
    const dx = (p.x - g.sx) / view.s;
    const dy = (p.y - g.sy) / view.s;
    if (!g.moved && Math.hypot(dx, dy) * view.s < 6) {
      return;
    }
    g.moved = true;
    for (const m of g.group) {
      const item = placed.value.find((i) => i.key === m.key);
      if (!item) {
        continue;
      }
      const x = Math.round(m.ox + dx);
      const y = Math.round(m.oy + dy);
      if (item.task) {
        moveTask(item.task.id, x, y);
      }
      else if (item.file) {
        moveFile(item.file, x, y);
      }
    }
    const single = g.group.length === 1 ? placed.value.find((i) => i.key === g.key) : undefined;
    const t = single?.file ? taskUnder(e.clientX, e.clientY, new Set([g.key]), single) : null;
    dropTarget.value = t ? `t${t.id}` : null;
  }
}
function onUp(e: PointerEvent) {
  hoverLine.value = null;
  cancelCut();
  if (!pointers.delete(e.pointerId)) {
    return;
  }
  cancelHold();
  const touch = e.pointerType !== 'mouse';
  if (pointers.size < 2) {
    pinch = null;
  }
  const g = gesture;
  if (g?.type === 'card' && pointers.size === 0) {
    if (e.type === 'pointerup') {
      g.moved = didDrag({ x: g.sx, y: g.sy }, point(e), g.moved);
    }
    let item = placed.value.find((i) => i.key === g.key);
    if (g.moved) {
      if (e.type === 'pointerup') {
        const p = point(e);
        for (const m of g.group) {
          const it = placed.value.find((i) => i.key === m.key);
          const x = Math.round(m.ox + (p.x - g.sx) / view.s);
          const y = Math.round(m.oy + (p.y - g.sy) / view.s);
          if (it?.task) {
            moveTask(it.task.id, x, y);
          }
          else if (it?.file) {
            moveFile(it.file, x, y);
          }
        }
        item = placed.value.find((i) => i.key === g.key);
      }
      const target = e.type === 'pointerup' && g.group.length === 1 && item?.file
        ? taskUnder(e.clientX, e.clientY, new Set([g.key]), item) : null;
      dropTarget.value = null;
      const original = g.group.find((m) => m.key === g.key)!;
      if (target && item?.file) {
        emit('attachTo', item.file, target, { x: original.ox, y: original.oy });
      }
      for (const m of g.group) {
        const it = placed.value.find((i) => i.key === m.key);
        if (it?.task) {
          emit('moved', it.task);
        }
        else if (it?.file && !(target && m.key === g.key)) {
          emit('movedFile', it.file);
        }
      }
    }
    else if (e.type === 'pointerup' && (g.toggle || (touch && selected.size > 0))) {
      toggle(g.key);
    }
    else if (e.type === 'pointerup' && item?.task) {
      emit('edit', item.task);
    }
    else if (e.type === 'pointerup' && item?.file) {
      emit('openFile', item.file);
    }
  }
  if (g?.type === 'select') {
    marquee.value = null;
    if (!g.moved && e.type === 'pointerup') {
      if (g.key) {
        toggle(g.key);
      }
      else if (!g.base.size) {
        clearSelection();
      }
    }
  }
  if (g?.type === 'pan' && g.clear && e.type === 'pointerup') {
    clearSelection();
  }
  if (pointers.size === 0) {
    gesture = null;
    dropTarget.value = null;
  }
}
function zoomAt(cx: number, cy: number, s: number) {
  s = Math.min(MAX, Math.max(MIN, s));
  const ratio = s / view.s;
  view.x = cx - (cx - view.x) * ratio;
  view.y = cy - (cy - view.y) * ratio;
  view.s = s;
}
let zoomGoal: number | null = null;
let zoomPoint = { x: 0, y: 0 };
let zoomRaf = 0;
function smoothZoom(px: number, py: number, factor: number) {
  zoomGoal = Math.min(MAX, Math.max(MIN, (zoomGoal ?? view.s) * factor));
  zoomPoint = { x: px, y: py };
  if (zoomRaf) {
    return;
  }
  const step = () => {
    const next = view.s + (zoomGoal! - view.s) * 0.3;
    if (Math.abs(zoomGoal! - next) < 0.002) {
      zoomAt(zoomPoint.x, zoomPoint.y, zoomGoal!);
      zoomGoal = null;
      zoomRaf = 0;
      return;
    }
    zoomAt(zoomPoint.x, zoomPoint.y, next);
    zoomRaf = requestAnimationFrame(step);
  };
  zoomRaf = requestAnimationFrame(step);
}
function onWheel(e: WheelEvent) {
  motion.stop();
  e.preventDefault();
  const p = point(e);
  if (e.ctrlKey || e.metaKey) {
    const d = e.deltaY * (e.deltaMode === 1 ? 33 : e.deltaMode === 2 ? 400 : 1);
    const factor = Math.abs(d) >= 40 ? (d < 0 ? 1.12 : 1 / 1.12) : Math.exp(-d * 0.008);
    smoothZoom(p.x, p.y, factor);
  }
  else {
    view.x -= e.shiftKey ? e.deltaY : e.deltaX;
    view.y -= e.shiftKey ? 0 : e.deltaY;
  }
}
function zoomBy(f: number) {
  motion.stop();
  const r = viewport.value!.getBoundingClientRect();
  smoothZoom(r.width / 2, r.height / 2, f);
}
function worldCenter() {
  const r = viewport.value!.getBoundingClientRect();
  return toWorld({ x: r.width / 2 - 80, y: r.height / 2 - 40 });
}
function occupied() {
  const all = new Map(graphObstacles(state.tasks, state.loose, sizes).map((r) => [r.key, r]));
  for (const p of placed.value) {
    all.set(p.key, { key: p.key, x: p.x, y: p.y, ...(sizes[p.key] ?? (p.file ? fileCardSize(p.file.type) : { w: 252, h: 240 })) });
  }
  return [...all.values()];
}
function freeSpot(type: FileItem['type'], taskId: number | null = null, ignoreId?: number) {
  motion.stop();
  measure();
  const obstacles = occupied().filter((r) => r.key !== `f${ignoreId}`);
  const owner = obstacles.find((r) => r.key === `t${taskId}`);
  const preferred = owner ? { x: owner.x + owner.w + 24, y: owner.y } : worldCenter();
  return findGraphSpot(fileCardSize(type), obstacles, preferred, owner);
}
async function placeFiles(files: FileItem[], taskId: number | null, options: {
  fromCurrent?: boolean;
  persist?: boolean;
} = {}) {
  if (!files.length) {
    return;
  }
  hoverLine.value = null;
  cancelCut();
  motion.stop();
  await nextTick();
  measure();
  const keys = new Set(files.map((f) => `f${f.id}`));
  const obstacles = occupied().filter((r) => !keys.has(r.key));
  const owner = obstacles.find((r) => r.key === `t${taskId}`);
  const placements = files.map((f) => {
    const size = sizes[`f${f.id}`] ?? fileCardSize(f.type);
    const preferred = owner ? { x: owner.x + owner.w + 24, y: owner.y } : { x: f.x ?? worldCenter().x, y: f.y ?? worldCenter().y };
    const target = findGraphSpot(size, obstacles, preferred, owner);
    obstacles.push({ key: `f${f.id}`, ...target, ...size });
    const dx = owner ? target.x + size.w / 2 - owner.x - owner.w / 2 : 0;
    const dy = owner ? target.y + size.h / 2 - owner.y - owner.h / 2 : 1;
    const distance = Math.hypot(dx, dy) || 1;
    const start = options.fromCurrent && f.x !== null && f.y !== null ? { x: f.x, y: f.y }
      : { x: target.x + dx / distance * 16, y: target.y + dy / distance * 16 };
    return { f, target, start };
  });
  await new Promise<void>((resolve) => {
    return motion.start((progress) => {
      for (const { f, target, start } of placements) {
        moveFile(f, progress === 1 ? target.x : start.x + (target.x - start.x) * progress, progress === 1 ? target.y : start.y + (target.y - start.y) * progress);
      }
    }, () => {
      if (options.persist !== false) {
        for (const { f } of placements) {
          emit('movedFile', f);
        }
      } resolve();
    }, window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 420);
  });
}
const desktop = () => window.matchMedia('(min-width: 1024px)').matches;
function bounds(items = placed.value) {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const i of items) {
    const sz = sizes[i.key] ?? { w: 252, h: 160 };
    x0 = Math.min(x0, i.x);
    y0 = Math.min(y0, i.y);
    x1 = Math.max(x1, i.x + sz.w);
    y1 = Math.max(y1, i.y + sz.h);
  }
  return { x0, y0, x1, y1 };
}
function initialView() {
  measure();
  if (!placed.value.length) {
    return;
  }
  const { x0, y0 } = bounds();
  view.s = desktop() ? 1 : PHONE_SCALE;
  view.x = 24 - x0 * view.s;
  view.y = (desktop() ? 80 : 64) - y0 * view.s;
  if (desktop()) {
    view.x = navigationInset.value + 26 - x0;
  }
}
let revealTimer = 0;
let tweenRaf = 0;
function revealFresh() {
  const first = placed.value.find((i) => i.task && fresh.has(i.task.id));
  if (!first || !viewport.value) {
    return;
  }
  measure();
  const rect = cardRects[first.key];
  if (!rect) {
    return;
  }
  const r = viewport.value.getBoundingClientRect();
  const left = desktop() ? navigationInset.value : 0;
  const top = desktop() ? 80 : 64;
  const bottom = desktop() ? 90 : 150;
  if (rect.x >= left && rect.x + rect.w <= r.width && rect.y >= top && rect.y + rect.h <= r.height - bottom) {
    return;
  }
  const dx = left + (r.width - left) / 2 - (rect.x + rect.w / 2);
  const dy = top + (r.height - top - bottom) / 2 - (rect.y + rect.h / 2);
  const fromX = view.x;
  const fromY = view.y;
  const t0 = performance.now();
  cancelAnimationFrame(tweenRaf);
  const step = (now: number) => {
    const k = Math.min(1, (now - t0) / 450);
    const e = 1 - (1 - k) ** 3;
    view.x = fromX + dx * e;
    view.y = fromY + dy * e;
    if (k < 1) {
      tweenRaf = requestAnimationFrame(step);
    }
  };
  tweenRaf = requestAnimationFrame(step);
}
watch(() => fresh.size, (n) => {
  if (n) {
    clearTimeout(revealTimer);
    revealTimer = window.setTimeout(revealFresh, 450);
  }
}, { immediate: true });
function fittedView(items: Placed[]) {
  const r = viewport.value!.getBoundingClientRect();
  if (!items.length) {
    return { ...view };
  }
  const { x0, y0, x1, y1 } = bounds(items);
  const topPad = desktop() ? 80 : 64;
  const bottomPad = desktop() ? 90 : 150;
  const side = 24;
  const left = desktop() ? navigationInset.value : 0;
  const s = Math.min(desktop() ? 1 : PHONE_SCALE, (r.width - left - side * 2) / (x1 - x0), (r.height - topPad - bottomPad) / (y1 - y0));
  const scale = Math.max(MIN, s);
  return {
    s: scale,
    x: left + (r.width - left - (x1 - x0) * scale) / 2 - x0 * scale,
    y: topPad + (r.height - topPad - bottomPad - (y1 - y0) * scale) / 2 - y0 * scale,
  };
}
function fit(items = placed.value) {
  motion.stop();
  measure();
  Object.assign(view, fittedView(items));
}
const dragging = ref(false);
let dragDepth = 0;
const hasFiles = (e: DragEvent) => [...(e.dataTransfer?.types ?? [])].includes('Files');
function onDragEnter(e: DragEvent) {
  if (hasFiles(e)) {
    dragDepth++;
    dragging.value = true;
  }
}
function onDragLeave() {
  if (--dragDepth <= 0) {
    dragDepth = 0;
    dragging.value = false;
    dropTarget.value = null;
  }
}
function onDragOver(e: DragEvent) {
  if (!hasFiles(e)) {
    return;
  }
  e.preventDefault();
  const t = taskUnder(e.clientX, e.clientY, new Set());
  dropTarget.value = t ? `t${t.id}` : null;
  e.dataTransfer!.dropEffect = 'copy';
}
function onDrop(e: DragEvent) {
  e.preventDefault();
  dragDepth = 0;
  dragging.value = false;
  const files = Array.from(e.dataTransfer?.files ?? []);
  const t = taskUnder(e.clientX, e.clientY, new Set());
  dropTarget.value = null;
  if (files.length) {
    emit('dropFiles', files, t, toWorld(point(e)));
  }
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    clearSelection();
  }
}
let ro: ResizeObserver | undefined;
onMounted(async () => {
  viewport.value!.addEventListener('wheel', onWheel, { passive: false });
  window.addEventListener('keydown', onKey);
  window.addEventListener('resize', measure);
  await nextTick();
  const saved = savedView();
  if (saved) {
    Object.assign(view, { ...saved, s: Math.min(MAX, Math.max(MIN, saved.s)) });
  }
  else if (placed.value.length) {
    initialView();
  }
  else {
    const stop = watch(placed, async (list) => {
      if (list.length) {
        stop();
        await nextTick();
        initialView();
      }
    });
  }
  ro = new ResizeObserver(measure);
  els.forEach((el) => ro!.observe(el));
});
watch(placed, async (list) => {
  const keys = new Set(list.map((item) => item.key));
  for (const key of selected) {
    if (!keys.has(key)) {
      selected.delete(key);
    }
  }
  await nextTick();
  measure();
  els.forEach((el) => ro?.observe(el));
}, { flush: 'post' });
watch(navigationInset, (next, previous) => {
  if (desktop()) {
    view.x += next - previous;
  }
});
watch(view, async () => { await nextTick(); measure(); }, { flush: 'post' });
onBeforeUnmount(() => {
  cancelAnimationFrame(tweenRaf);
  clearTimeout(revealTimer);
  motion.finish();
  viewport.value?.removeEventListener('wheel', onWheel);
  window.removeEventListener('keydown', onKey);
  window.removeEventListener('resize', measure);
  cancelAnimationFrame(zoomRaf);
  cancelHold();
  ro?.disconnect();
});
const dots = computed(() => {
  if (look.mapBg === 'plain') {
    return {};
  }
  const image = look.mapBg === 'grid'
    ? 'linear-gradient(var(--grid-line) 1px, transparent 1px), linear-gradient(90deg, var(--grid-line) 1px, transparent 1px)'
    : 'radial-gradient(var(--dot) 1.3px, transparent 1.7px)';
  let step = (look.mapBg === 'grid' ? 32 : 24) * view.s;
  while (step < 18) {
    step *= 2;
  }
  return { backgroundImage: image, backgroundSize: `${step}px ${step}px`, backgroundPosition: `${view.x}px ${view.y}px` };
});
function arrange() {
  motion.stop();
  cancelAnimationFrame(zoomRaf);
  zoomRaf = 0;
  zoomGoal = null;
  measure();
  const { tasks, files, anchored, loose, canArrange } = arrangement.value;
  if (!canArrange) {
    return;
  }
  const at = (key: string) => placed.value.find((p) => p.key === key)!;
  const previousView = { ...view };
  const before = {
    restoreView: () => { motion.stop(); Object.assign(view, previousView); },
    tasks: tasks.map((t) => ({ t, x: at(`t${t.id}`).x, y: at(`t${t.id}`).y })),
    files: files.map((f) => ({ f, x: at(`f${f.id}`).x, y: at(`f${f.id}`).y })),
  };
  const affected = new Set([...tasks.map((t) => `t${t.id}`), ...before.files.map(({ f }) => `f${f.id}`)]);
  const packed = new Set([...tasks.map((t) => `t${t.id}`), ...tasks.flatMap((t) => t.files.map((f) => `f${f.id}`)), ...loose.map((f) => `f${f.id}`)]);
  const cluster = placed.value.filter((p) => packed.has(p.key));
  const left = cluster.length ? Math.min(...cluster.map((p) => p.x)) : 0;
  const top = cluster.length ? Math.min(...cluster.map((p) => p.y)) : 0;
  const stationary = placed.value.filter((p) => !affected.has(p.key)).map((p) => {
    return {
      key: p.key, x: p.x, y: p.y, ...(sizes[p.key] ?? { w: 252, h: 160 }),
    };
  });
  const rank = { photo: 0, doc: 1, link: 2, note: 3 };
  const positions = arrangeGraph({
    tasks: tasks.map((t) => {
      return {
        key: `t${t.id}`, group: groupOf(t), due: t.due_at ? Date.parse(t.due_at) : Infinity,
        files: [...t.files].sort((a, b) => rank[a.type] - rank[b.type]).map((f) => `f${f.id}`),
      };
    }),
    loose: loose.map((f) => `f${f.id}`), sizes, left, top,
    maxWidth: desktop() ? 1440 : 560,
    obstacles: stationary,
  });
  const reserved = [...stationary, ...[...positions].map(([key, p]) => ({ key, ...p, ...(sizes[key] ?? { w: 252, h: 160 }) }))];
  for (const group of anchored) {
    const owner = stationary.find((p) => p.key === `t${group.task.id}`)!;
    const targets = arrangeAttachments(owner, group.files.map((f) => `f${f.id}`), sizes, reserved);
    for (const [key, p] of targets) {
      positions.set(key, p);
      reserved.push({ key, ...p, ...(sizes[key] ?? { w: 190, h: 64 }) });
    }
  }
  const shown = new Set([...affected, ...anchored.map((group) => `t${group.task.id}`)]);
  const targetView = fittedView(placed.value.filter((p) => shown.has(p.key)).map((p) => ({ ...p, ...(positions.get(p.key) ?? {}) })));
  const mix = (from: number, to: number, progress: number) => {
    if (progress === 1) {
      return to;
    }
    return from + (to - from) * progress;
  };
  motion.start((progress) => {
    for (const { t, x, y } of before.tasks) {
      const p = positions.get(`t${t.id}`)!;
      moveTask(t.id, mix(x, p.x, progress), mix(y, p.y, progress));
    }
    for (const { f, x, y } of before.files) {
      const p = positions.get(`f${f.id}`)!;
      moveFile(f, mix(x, p.x, progress), mix(y, p.y, progress));
    }
    Object.assign(view, {
      x: mix(previousView.x, targetView.x, progress), y: mix(previousView.y, targetView.y, progress),
      s: mix(previousView.s, targetView.s, progress),
    });
  }, () => {
    for (const t of tasks) {
      emit('moved', t);
    }
    for (const { f } of before.files) {
      emit('movedFile', f);
    }
    emit('arranged', before);
  }, window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 560);
}
const VIEW_KEY = 'uchebrik_map_view';
function savedView(): {
  x: number;
  y: number;
  s: number;
} | null {
  try {
    const v = JSON.parse(localStorage.getItem(VIEW_KEY) ?? 'null');
    if (v && [v.x, v.y, v.s].every(Number.isFinite)) {
      return v;
    }
    return null;
  }
  catch {
    return null;
  }
}
let viewTimer = 0;
watch(view, () => {
  clearTimeout(viewTimer);
  viewTimer = window.setTimeout(() => {
    try {
      localStorage.setItem(VIEW_KEY, JSON.stringify({ x: view.x, y: view.y, s: view.s }));
    }
    catch { }
  }, 300);
});
</script>

<template>
  <div ref="viewport" class="viewport" :class="{ files: dragging }" :style="dots"
       @pointerdown="onDown" @pointermove="onMove" @pointerup="onUp" @pointercancel="onUp" @contextmenu.prevent
       @dragenter="onDragEnter" @dragleave="onDragLeave" @dragover="onDragOver" @drop="onDrop">
      <svg ref="threadsSvg" class="threads" width="100%" height="100%">
        <path v-for="l in threads" :key="l.key" :d="l.d" fill="none" class="thread"
              :data-task-id="l.task.id" :data-file-id="l.file.id"
              :class="{ hot: hoverLine === l.key, cut: cutting === l.key }" :stroke-width="1.5 * view.s" />
        <path v-for="l in threads" :key="'h' + l.key" :d="l.d" class="hit" fill="none" :stroke-width="16 * view.s"
              @pointermove="hoverThread(l.key, $event)" @pointerleave="hoverLine = null; cancelCut()"
              @pointerdown.stop="startCut(l, $event)" @pointerup="cancelCut" @pointercancel="cancelCut">
          <title>Подержи, чтобы убрать связь</title>
        </path>
        <template v-for="(l, i) in threads" :key="'d' + i">
          <circle :cx="l.x1" :cy="l.y1" :r="3 * view.s" fill="var(--soft)" />
          <circle :cx="l.x2" :cy="l.y2" :r="3 * view.s" fill="var(--soft)" />
        </template>
      </svg>
    <div class="world" :style="{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.s})` }">
      <TransitionGroup name="card">
        <div v-for="i in placed" :key="i.key" :ref="(el) => setEl(i.key, el)" class="item"
             :class="{ sel: selected.has(i.key), drop: dropTarget === i.key, fresh: !!i.task && fresh.has(i.task.id) }" :data-key="i.key"
             :style="{ left: i.x + 'px', top: i.y + 'px' }" @transitionend.self="measure">
          <TaskCard v-if="i.task" :task="i.task" @edit="emit('edit', i.task!)" @attach="emit('attach', i.task!)" @done="emit('done', i.task!)" />
          <FileCard v-else-if="i.file" :file="i.file" />
        </div>
      </TransitionGroup>
    </div>
    <div v-if="marquee" class="marquee" :style="{ left: marquee.l + 'px', top: marquee.t + 'px', width: marquee.w + 'px', height: marquee.h + 'px' }"></div>
    <Transition name="pop">
      <div v-if="selected.size" class="selbar" @pointerdown.stop>
        <button v-if="arrangement.canArrange" class="arr" aria-label="Разложить выделенные по предметам" title="Разложить выделенные по предметам" @click="arrange">
          <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="2.5" y="2.5" width="6" height="6" rx="1.6"/><rect x="11.5" y="2.5" width="6" height="6" rx="1.6"/><rect x="2.5" y="11.5" width="6" height="6" rx="1.6"/><rect x="11.5" y="11.5" width="6" height="6" rx="1.6"/></svg>
        </button>
        <button class="del" :aria-label="`Удалить выделенное: ${selected.size}`" :title="`Удалить выделенное: ${selected.size}`" @click="removeSelected">
          <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 5.5h13M8 5.5V3.8h4v1.7M5.5 5.5l.7 10.2c.05.8.7 1.3 1.4 1.3h4.8c.7 0 1.35-.5 1.4-1.3l.7-10.2M8.3 9v5M11.7 9v5"/></svg>
        </button>
      </div>
    </Transition>
    <p v-if="dragging" class="drophint">Отпусти на задании — прикреплю, на пустом месте — положу на карту</p>
  </div>
</template>

<style scoped>
.viewport {
    position: absolute;
    inset: 0;
    overflow: hidden;
    touch-action: none;
    cursor: grab;
    user-select: none;
    -webkit-user-select: none;
    background-color: var(--screen);
}
.viewport.files {
    box-shadow: inset 0 0 0 3px var(--accent);
}
.world {
    position: absolute;
    left: 0;
    top: 0;
    transform-origin: 0 0;
    z-index: 1;
}
.threads {
    position: absolute;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
    z-index: 0;
}
.thread {
    stroke: var(--thread);
    transition:
        stroke 0.15s ease,
        stroke-width 0.15s ease;
    animation: thread-in 0.24s ease both;
}
@keyframes thread-in {
    from {
        opacity: 0;
    }
    to {
        opacity: 1;
    }
}
.thread.hot {
    stroke: var(--danger);
    stroke-width: 2.5;
}
.thread.cut {
    stroke: var(--danger);
    stroke-width: 3;
    stroke-dasharray: 6 5;
    animation: thread-cut 0.6s linear both;
}
@keyframes thread-cut {
    from {
        opacity: 1;
    }
    to {
        opacity: 0.25;
    }
}
.hit {
    stroke: transparent;
    pointer-events: stroke;
    cursor: pointer;
}
.item {
    position: absolute;
    z-index: 1;
    border-radius: 24px;
    transition:
        box-shadow 0.18s ease,
        scale 0.18s var(--ease-out),
        translate 0.18s var(--ease-out),
        opacity 0.25s ease;
}
@media (hover: hover) {
    .item:hover {
        translate: 0 -2px;
        z-index: 3;
    }
    .item:hover > * {
        box-shadow: 0 12px 30px var(--lift);
    }
}
.item > * {
    transition: box-shadow 0.18s ease;
}
.card-enter-from {
    opacity: 0;
    scale: 0.92;
}
.card-leave-to {
    opacity: 0;
    scale: 0.85;
}
.card-leave-active {
    transition:
        opacity 0.22s ease,
        scale 0.22s ease;
    pointer-events: none;
}
.item.sel {
    z-index: 5;
}
.item.sel :deep([data-card]) {
    border-color: var(--accent);
    box-shadow: inset 0 0 0 1px var(--accent);
}
.item.drop {
    scale: 1.03;
    z-index: 4;
}
.item.fresh {
    z-index: 4;
}
.item.fresh :deep([data-card]) {
    border-color: var(--accent);
    animation: fresh-ring 1.9s ease-out 3 both;
}
@keyframes fresh-ring {
    0% {
        box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent) 60%, transparent);
    }
    80%,
    100% {
        box-shadow: 0 0 0 14px color-mix(in srgb, var(--accent) 0%, transparent);
    }
}
@media (prefers-reduced-motion: reduce) {
    .item.fresh :deep([data-card]) {
        animation: none;
        box-shadow: 0 0 0 2px var(--accent);
    }
}
.item.drop :deep([data-card]) {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent);
}
.marquee {
    position: absolute;
    z-index: 15;
    pointer-events: none;
    border: 1.5px solid var(--accent);
    border-radius: 8px;
    background: rgba(47, 140, 255, 0.14);
}
.selbar {
    position: absolute;
    right: 12px;
    top: calc(56px + var(--safe-top));
    z-index: 16;
    display: flex;
    align-items: center;
    gap: 8px;
}
.selbar button {
    width: 42px;
    height: 42px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: var(--bar);
    border: 1px solid var(--bar-line);
    color: var(--ink);
}
.selbar .del {
    background: var(--danger);
    border-color: var(--danger);
    color: #fff;
}
@media (min-width: 1024px) {
    .selbar {
        top: 64px;
        right: 20px;
    }
}
.drophint {
    position: absolute;
    left: 50%;
    bottom: 96px;
    transform: translateX(-50%);
    z-index: 16;
    margin: 0;
    padding: 10px 18px;
    border-radius: 20px;
    background: var(--bar);
    border: 1px solid var(--bar-line);
    font-weight: 600;
    font-size: 13px;
    pointer-events: none;
}
</style>
