<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue';
import Sheet from './Sheet.vue';
import RequiredMark from './RequiredMark.vue';
import DateField from './DateField.vue';
import type { FileItem, Kind, Task } from '../types';
import { local, pad, toIso } from '../format';
import { maskTime, resolveTime } from '../dateInput';
import { newId } from '../store';
import okIcon from '../assets/icons/check-green.svg';
import microphoneIcon from '../assets/icons/microphone.svg?raw';
import { recognizeVoice } from '../api';
const props = defineProps<{
  task: Task | null;
}>();
const emit = defineEmits<{
  close: [];
  save: [Task, File[]];
  remove: [Task];
  done: [Task];
}>();
type PickedFile = {
  name: string;
  item?: FileItem;
  file?: File;
};
const TITLES: Record<Kind, string> = { homework: 'Домашнее задание', todo: 'Дело', event: 'Событие', project: 'Проект', olympiad: 'Олимпиада' };
const title = computed(() => {
  if (initial) {
    return TITLES[form.kind] ?? 'Задание';
  }
  return 'Новое дело';
});
const KINDS: {
  id: Kind;
  label: string;
}[] = [
    { id: 'homework', label: 'Домашка' }, { id: 'todo', label: 'Дело' }, { id: 'event', label: 'Событие' },
    { id: 'project', label: 'Период' }, { id: 'olympiad', label: 'Олимпиада' },
  ];
const split = (iso: string | null) => {
  if (!iso) {
    return { d: '', t: '' };
  }
  const l = local(iso);
  return { d: `${l.y}-${pad(l.m)}-${pad(l.d)}`, t: `${pad(l.hh)}:${pad(l.mm)}` };
};
const initial = props.task;
const due = split(initial?.due_at ?? null);
const reg = split(initial?.reg_deadline ?? null);
const form = reactive({
  title: initial?.title ?? '',
  subject: initial?.subject ?? '',
  kind: (initial?.kind ?? 'homework') as Kind,
  date: due.d,
  time: due.t || '23:59',
  location: initial?.location ?? '',
  note: initial?.note ?? '',
  duration: initial?.duration_min?.toString() ?? '',
  regTo: reg.d,
  registered: initial?.registered ?? false,
  links: (initial?.files ?? []).filter((f) => f.type === 'link').map((f) => f.url ?? f.name),
  files: (initial?.files ?? []).filter((f) => f.type !== 'link' && f.type !== 'note').map((f): PickedFile => ({ name: f.name, item: f })),
});
const newLink = ref('');
const fileInput = ref<HTMLInputElement>();
const error = ref('');
const isEvent = computed(() => form.kind === 'event' || form.kind === 'olympiad');
function onTime(e: Event) {
  const input = e.target as HTMLInputElement;
  form.time = maskTime(input.value);
  input.value = form.time;
}
function fixTime() {
  form.time = resolveTime(form.time) ?? '23:59';
}
function addLink() {
  const v = newLink.value.trim();
  if (v) {
    form.links.push(v);
  }
  newLink.value = '';
}
function onFiles(e: Event) {
  const input = e.target as HTMLInputElement;
  for (const f of Array.from(input.files ?? [])) {
    form.files.push({ name: f.name, file: f });
  }
  input.value = '';
}
const MAX_SECONDS = 120;
const isMiniApp = Boolean(window.WebApp?.initData);
const voice = reactive({ state: 'idle' as 'idle' | 'recording' | 'working', seconds: 0, heard: '', more: 0, error: '' });
let recorder: MediaRecorder | null = null;
let timer = 0;
function pickMime() {
  for (const m of ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(m)) {
      return m;
    }
  }
  return '';
}
async function startVoice() {
  voice.error = '';
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    voice.error = 'Здесь микрофон недоступен. Открой карту в браузере или надиктуй голосовое боту в чате';
    return;
  }
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  }
  catch {
    voice.error = 'Нет доступа к микрофону. Разреши его в настройках браузера';
    return;
  }
  const mime = pickMime();
  const chunks: Blob[] = [];
  recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  recorder.ondataavailable = (e) => {
    if (e.data.size) {
      chunks.push(e.data);
    }
  };
  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    clearInterval(timer);
    if (voice.state !== 'recording') {
      return;
    }
    voice.state = 'working';
    try {
      fill(await recognizeVoice(new Blob(chunks, { type: recorder?.mimeType || mime || 'audio/webm' })));
    }
    catch (e) {
      voice.error = (e as Error).message;
    }
    finally {
      voice.state = 'idle';
    }
  };
  recorder.start();
  voice.state = 'recording';
  voice.seconds = 0;
  timer = window.setInterval(() => {
    if (++voice.seconds >= MAX_SECONDS) {
      stopVoice();
    }
  }, 1000);
}
function stopVoice() {
  if (recorder && recorder.state === 'recording') {
    recorder.stop();
  }
}
function fill(r: Awaited<ReturnType<typeof recognizeVoice>>) {
  voice.heard = r.transcript;
  const t = r.tasks[0];
  voice.more = Math.max(0, r.tasks.length - 1);
  if (!t) {
    return;
  }
  form.title = t.title;
  form.subject = t.subject ?? '';
  form.kind = t.kind;
  const d = split(t.due_at);
  form.date = d.d;
  form.time = d.t || '23:59';
  form.location = t.location ?? form.location;
  form.duration = t.duration_min?.toString() ?? form.duration;
  form.regTo = split(t.reg_deadline).d || form.regTo;
}
onBeforeUnmount(() => {
  voice.state = 'idle';
  stopVoice();
  clearInterval(timer);
});
const clock = computed(() => `${Math.floor(voice.seconds / 60)}:${String(voice.seconds % 60).padStart(2, '0')}`);
function submit() {
  if (!form.title.trim()) {
    error.value = 'Напишите, что нужно сделать';
    return;
  }
  const duration = form.duration.trim() ? Number(form.duration) : null;
  if (duration !== null && (!Number.isInteger(duration) || duration < 1 || duration > 1440)) {
    error.value = 'Укажите длительность от 1 до 1440 минут';
    return;
  }
  const id = initial?.id ?? newId();
  const files: FileItem[] = [
    ...form.links.map((n, i): FileItem => ({ id: newId() + i, task_id: id, type: 'link', name: n, url: n, x: null, y: null })),
    ...form.files.map((p, i): FileItem => {
      return p.item ?? ({ id: newId() + 100 + i, task_id: id, type: /\.(png|jpe?g|gif|webp|heic)$/i.test(p.name) ? 'photo' : 'doc', name: p.name, x: null, y: null });
    }),
    ...(initial?.files ?? []).filter((f) => f.type === 'note'),
  ];
  const uploads = form.files.filter((p) => p.file).map((p) => p.file!);
  emit('save', {
    id, title: form.title.trim(), subject: form.subject.trim() || null, kind: form.kind,
    due_at: toIso(form.date, form.time), location: form.location.trim() || null, note: form.note.trim() || null,
    reg_deadline: isEvent.value ? toIso(form.regTo, '23:59') : null,
    duration_min: duration,
    registered: isEvent.value && !!form.regTo && form.registered,
    status: initial?.status ?? 'active', x: initial?.x ?? null, y: initial?.y ?? null, files,
  }, uploads);
}
</script>

<template>
  <Sheet dock-id="task" :title="title" @close="emit('close')">
    <template v-if="!initial && !isMiniApp">
      <button v-if="voice.state === 'idle'" class="mic" @click="startVoice"><span class="mic-icon" aria-hidden="true" v-html="microphoneIcon"></span>Надиктовать</button>
      <button v-else-if="voice.state === 'recording'" class="mic rec" @click="stopVoice">
        <span class="dot"></span> Запись {{ clock }}. Нажми, чтобы закончить
      </button>
      <div v-else class="mic wait">Распознаю…</div>
      <p v-if="voice.heard" class="heard">«{{ voice.heard }}»<template v-if="voice.more"><br />Ещё {{ voice.more }} — надиктуй их отдельно</template></p>
      <p v-if="voice.error" class="err">{{ voice.error }}</p>
    </template>

    <label class="lbl" for="task-title">Что сделать<RequiredMark /></label>
    <textarea id="task-title" v-model="form.title" class="field area" rows="2" placeholder="Решить упражнение…" required></textarea>

    <label class="lbl">Предмет</label>
    <input v-model="form.subject" class="field" placeholder="без предмета" />

    <label class="lbl">Тип</label>
    <div class="kinds">
      <button v-for="k in KINDS" :key="k.id" :class="{ on: form.kind === k.id }" @click="form.kind = k.id">{{ k.label }}</button>
    </div>

    <label class="lbl">Срок</label>
    <div class="dt">
      <DateField v-model="form.date" />
      <input :value="form.time" class="field time" inputmode="numeric" maxlength="5" placeholder="23:59" @input="onTime" @blur="fixTime" />
      <button class="clear" aria-label="Без срока" @click="form.date = ''">✕</button>
    </div>

    <label class="lbl">Место</label>
    <input v-model="form.location" class="field" placeholder="Кабинет, адрес или ссылка" />

    <label class="lbl" for="task-duration">{{ isEvent ? 'Длительность в минутах' : 'Сколько займёт в минутах' }}</label>
    <input id="task-duration" v-model="form.duration" class="field" inputmode="numeric" maxlength="4" placeholder="30" />

    <label class="lbl">Описание</label>
    <textarea v-model="form.note" class="field area tall" rows="3" placeholder="Что угодно: решать можно в любой день, что взять с собой, пароль…"></textarea>

    <template v-if="isEvent">
      <label class="lbl">Регистрация до</label>
      <DateField v-model="form.regTo" :with-picker="false" />
      <label v-if="form.regTo" class="lbl"><input v-model="form.registered" type="checkbox" /> Уже зарегистрировался</label>
    </template>

    <label class="lbl">Ссылки</label>
    <div class="chips"><span v-for="(l, i) in form.links" :key="l + i" class="tag">{{ l }}<button @click="form.links.splice(i, 1)">✕</button></span></div>
    <div class="add"><input v-model="newLink" class="field" placeholder="Вставь ссылку…" @keydown.enter="addLink" /><button class="plus" aria-label="Добавить ссылку" @click="addLink">+</button></div>

    <label class="lbl">Файлы</label>
    <div class="chips"><span v-for="(f, i) in form.files" :key="f.name + i" class="tag">{{ f.name }}<button @click="form.files.splice(i, 1)">✕</button></span></div>
    <div class="add">
      <button class="field pick" @click="fileInput?.click()">Выбери файл или перетащи его сюда…</button>
      <button class="plus" aria-label="Выбрать файл" @click="fileInput?.click()">↓</button>
      <input ref="fileInput" type="file" multiple hidden @change="onFiles" />
    </div>
    <p v-if="error" class="err">{{ error }}</p>

    <template #footer>
      <button v-if="initial" class="del" @click="emit('remove', initial!)">Удалить</button>
      <button class="save" @click="submit">Сохранить</button>
      <button v-if="initial" class="okb" aria-label="Сделано" @click="emit('done', initial!)"><img :src="okIcon" alt="" /></button>
    </template>
  </Sheet>
</template>

<style scoped>
.lbl {
    display: block;
    margin: 10px 0 4px;
    font-weight: 500;
    font-size: 11.5px;
    color: var(--soft);
}
.field {
    width: 100%;
    height: 40px;
    border-radius: 13px;
    background: var(--field);
    border: 1px solid transparent;
    padding: 0 12px;
    font-size: 14px;
    color: var(--ink);
    outline: none;
    color-scheme: var(--scheme);
}
.field:focus {
    border-color: var(--accent);
}
.field::placeholder {
    color: var(--soft);
}
.area {
    height: auto;
    padding: 10px 12px;
    resize: none;
    line-height: 18px;
}
.tall {
    min-height: 84px;
}
.kinds {
    display: flex;
    gap: 5px;
    flex-wrap: wrap;
}
.kinds button {
    height: 38px;
    padding: 0 14px;
    border-radius: 19px;
    background: var(--field);
    font-weight: 500;
    font-size: 13.5px;
}
.kinds button.on {
    background: var(--accent);
    color: #fff;
    font-weight: 600;
}
.dt {
    display: flex;
    gap: 6px;
    align-items: center;
}
.time {
    width: 72px;
    flex: none;
    text-align: center;
}
.clear {
    width: 22px;
    color: var(--soft);
    font-size: 13px;
}
.chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 6px;
}
.tag {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 25px;
    padding: 0 8px;
    border-radius: 13px;
    background: var(--field);
    font-weight: 600;
    font-size: 12.5px;
}
.tag button {
    color: var(--soft);
    font-size: 11px;
}
.add {
    display: flex;
    gap: 6px;
}
.pick {
    text-align: left;
    color: var(--soft);
    flex: 1;
}
.plus {
    width: 40px;
    height: 40px;
    border-radius: 13px;
    background: var(--accent);
    color: #fff;
    font-size: 22px;
    font-weight: 600;
    flex: none;
}
.mic {
    width: 100%;
    height: 44px;
    border-radius: 13px;
    background: var(--field);
    font-weight: 600;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin-top: 4px;
}
.mic.rec {
    background: rgba(255, 77, 87, 0.12);
    color: var(--danger);
}
.mic-icon {
    width: 20px;
    height: 20px;
    display: grid;
    place-items: center;
}
.mic-icon :deep(svg) {
    width: 100%;
    height: 100%;
}
.mic.wait {
    color: var(--soft);
}
.dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--danger);
    animation: blink 1s infinite;
}
@keyframes blink {
    50% {
        opacity: 0.25;
    }
}
@media (prefers-reduced-motion: reduce) {
    .dot {
        animation: none;
    }
}
.heard {
    margin: 8px 0 0;
    font-size: 13px;
    color: var(--soft);
    line-height: 17px;
}
.err {
    color: var(--danger);
    font-size: 13px;
    margin: 8px 0 0;
}
.del {
    height: 38px;
    padding: 0 16px;
    border-radius: 13px;
    background: rgba(255, 77, 87, 0.12);
    color: var(--danger);
    font-weight: 600;
    font-size: 13.5px;
}
.save {
    flex: 1;
    height: 38px;
    border-radius: 13px;
    background: var(--accent);
    color: #fff;
    font-weight: 600;
    font-size: 13.5px;
}
.okb {
    width: 38px;
    height: 38px;
    border-radius: 13px;
    background: var(--ok);
    display: grid;
    place-items: center;
}
.okb img {
    width: 13px;
    height: 14px;
}
</style>
