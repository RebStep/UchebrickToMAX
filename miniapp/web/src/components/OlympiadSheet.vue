<script setup lang="ts">
import { reactive, ref } from 'vue';
import Sheet from './Sheet.vue';
import RequiredMark from './RequiredMark.vue';
import DateField from './DateField.vue';
import { dateLong, dayKey, local, timeText, toIso } from '../format';
import { newId, normUrl } from '../store';
import type { Olympiad, Tour } from '../types';
const props = defineProps<{
  olympiad: Olympiad | null;
}>();
const emit = defineEmits<{
  close: [];
  save: [Olympiad];
  remove: [Olympiad];
}>();
const o = props.olympiad;
const day = (iso: string | null) => {
  if (iso) {
    return dayKey(local(iso));
  }
  return '';
};
function tourForm(t?: Tour) {
  const start = t?.starts_at ?? null;
  const end = t?.deadline ?? null;
  const at = start ?? end;
  const event = !!at && ((start === end && timeText(at) !== '00:00') || !!t?.duration_min);
  return {
    id: t?.id ?? newId(), title: t?.title ?? '', from: day(start ?? end), to: event ? '' : day(end),
    time: event && at ? timeText(at) : '09:00', event, duration: t?.duration_min?.toString() ?? '', done: t?.done ?? false,
  };
}
const form = reactive({
  name: o?.name ?? '', level: o?.level ?? '', subject: o?.subject ?? '', location: o?.location ?? '', note: o?.note ?? '',
  registered: o?.registered ?? false, regOpens: day(o?.reg_opens ?? null), regTo: day(o?.reg_deadline ?? null),
  remindersMuted: o?.reminders_muted ?? false,
  links: [...(o?.links ?? [])],
  tours: o?.tours.length ? o.tours.map(tourForm) : [tourForm()],
});
const readonly = ref(o !== null && o.tours.length > 0);
const newLink = ref('');
const error = ref('');
function submit() {
  if (!form.name.trim()) {
    return;
  }
  if (form.regOpens && form.regTo && form.regOpens > form.regTo) {
    error.value = 'Открытие регистрации должно быть раньше её окончания';
    return;
  }
  const tours: Tour[] = [];
  for (const t of form.tours) {
    if (!t.title.trim() && !t.from && !t.to) {
      continue;
    }
    if (!t.event && t.from && t.to && t.from > t.to) {
      error.value = 'Дата окончания тура должна быть не раньше начала';
      return;
    }
    const duration = t.event && t.duration.trim() ? Number(t.duration) : null;
    if (duration !== null && (!Number.isInteger(duration) || duration < 1 || duration > 1440)) {
      error.value = 'Длительность тура должна быть от 1 до 1440 минут';
      return;
    }
    const starts = toIso(t.from, t.event ? t.time || '09:00' : '00:00');
    tours.push({
      id: t.id, title: t.title.trim() || 'Тур', starts_at: starts,
      deadline: t.event ? starts : toIso(t.to || t.from, '23:59'), duration_min: duration, done: t.done,
    });
  }
  emit('save', {
    id: o?.id ?? newId(), name: form.name.trim(), level: form.level.trim() || null, subject: form.subject.trim() || null,
    location: form.location.trim() || null, note: form.note.trim() || null, registered: form.registered,
    reg_opens: toIso(form.regOpens, '00:00'), reg_deadline: toIso(form.regTo, '23:59'), tours, links: form.links,
    reminders_muted: form.remindersMuted,
  });
}
const fmt = (s: string | null) => {
  if (s) {
    return dateLong(local(s));
  }
  return '';
};
function addLink() {
  const url = normUrl(newLink.value.trim());
  if (!url) {
    error.value = 'Проверьте ссылку';
    return;
  }
  if (!form.links.includes(url) && form.links.length < 20) {
    form.links.push(url);
  }
  newLink.value = '';
  error.value = '';
}
</script>

<template>
  <Sheet dock-id="olympiad" :title="readonly ? o!.name : 'Олимпиада'" :subtitle="readonly ? [o!.subject, o!.level].filter(Boolean).join(' ') : undefined" @close="emit('close')">
    <template v-if="readonly">
      <div v-if="o!.location || o!.note" class="info"><p v-if="o!.location" class="loc">{{ o!.location }}</p><p v-if="o!.note">{{ o!.note }}</p></div>
      <p v-for="url in o!.links ?? []" :key="url" class="link"><a :href="url" target="_blank" rel="noopener noreferrer">{{ url }}</a></p>
      <div v-for="(t, i) in o!.tours" :key="t.id" class="tour">
        <div class="tt"><b>{{ i + 1 }} тур</b><small>{{ t.title }}</small></div>
        <small v-if="t.starts_at && t.starts_at === t.deadline">{{ fmt(t.starts_at) }} · {{ timeText(t.starts_at) }}<template v-if="t.duration_min"> · {{ t.duration_min }} мин</template></small>
        <small v-else>{{ [fmt(t.starts_at), fmt(t.deadline)].filter(Boolean).join(' – ') || 'Дата неизвестна' }}</small>
        <small v-if="i === 0 && o!.reg_deadline" class="red">Регистрация до {{ fmt(o!.reg_deadline) }}</small>
      </div>
    </template>
    <template v-else>
      <label class="lbl" for="olympiad-name">Название<RequiredMark /></label><input id="olympiad-name" v-model="form.name" class="field" placeholder="Технокубок" required />
      <label class="lbl">Доп. информация</label><input v-model="form.level" class="field" placeholder="нет" />
      <label class="lbl">Предмет</label><input v-model="form.subject" class="field" placeholder="без предмета" />
      <label class="lbl">Место</label><input v-model="form.location" class="field" placeholder="Кабинет, адрес или ссылка" />
      <label class="lbl">Описание</label><textarea v-model="form.note" class="field area" rows="3" placeholder="Что угодно: решать можно в любой день, что взять с собой, пароль…"></textarea>
      <button class="sw" :class="{ on: form.registered }" @click="form.registered = !form.registered">Уже зарегистрирован</button>
      <button class="sw" :class="{ on: form.remindersMuted }" @click="form.remindersMuted = !form.remindersMuted">{{ form.remindersMuted ? 'Напоминания выключены' : 'Напоминания включены' }}</button>
      <div class="two"><div><label class="lbl">Регистрация с</label><DateField v-model="form.regOpens" :with-picker="false" /></div><div><label class="lbl">до</label><DateField v-model="form.regTo" :with-picker="false" /></div></div>
      <label class="lbl">Ссылки</label>
      <div v-for="(url, i) in form.links" :key="url" class="link"><span>{{ url }}</span><button type="button" @click="form.links.splice(i, 1)">Убрать</button></div>
      <div class="two"><input v-model="newLink" class="field" type="url" placeholder="https://" @keyup.enter="addLink" /><button type="button" @click="addLink">Добавить ссылку</button></div>
      <div v-for="(t, i) in form.tours" :key="t.id" class="tour">
        <p class="div"><span>ТУР {{ i + 1 }}</span></p>
        <label class="lbl">Название тура</label><input v-model="t.title" class="field" placeholder="Например: Отборочный…" />
        <button class="sw" :class="{ on: t.event }" @click="t.event = !t.event">{{ t.event ? 'Тур в точное время' : 'Период или неизвестная дата' }}</button>
        <div class="two">
          <div><label class="lbl">{{ t.event ? 'Дата' : 'Дата с' }}</label><DateField v-model="t.from" :with-picker="false" /></div>
          <div v-if="t.event"><label class="lbl">Время</label><input v-model="t.time" type="time" class="field" /></div>
          <div v-else><label class="lbl">Дата до</label><DateField v-model="t.to" :with-picker="false" /></div>
        </div>
        <input v-if="t.event" v-model="t.duration" class="field" inputmode="numeric" maxlength="4" placeholder="Длительность в минутах" />
        <div class="two"><button class="sw" :class="{ on: t.done }" @click="t.done = !t.done">{{ t.done ? '✓ Написал' : 'Отметить, что написал' }}</button>
          <button class="sw" @click="form.tours.splice(i, 1)">Убрать тур</button></div>
      </div>
      <button v-if="form.tours.length < 20" class="sw" @click="form.tours.push(tourForm())">Добавить тур</button>
      <p v-if="error" class="red">{{ error }}</p>
    </template>
    <template #footer>
      <button v-if="o" class="del" @click="emit('remove', o)">Удалить</button>
      <button v-if="!readonly" class="save" @click="submit">{{ o ? 'Сохранить' : 'Добавить' }}</button>
      <button v-else class="save" @click="readonly = false">Изменить</button>
    </template>
  </Sheet>
</template>

<style scoped>
.info {
    background: var(--field);
    border-radius: 16px;
    padding: 12px;
    font-size: 13px;
    display: grid;
    gap: 6px;
    margin-bottom: 14px;
}
.info p {
    margin: 0;
}
.loc {
    color: var(--soft);
}
.tour {
    display: grid;
    gap: 3px;
    margin: 10px 0;
    padding: 0 3px;
}
.tt {
    display: flex;
    gap: 8px;
    align-items: baseline;
}
.tour small {
    color: var(--soft);
    font-size: 11.5px;
}
.red {
    color: var(--danger) !important;
    font-weight: 600;
}
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
    outline: none;
    color-scheme: var(--scheme);
}
.field:focus {
    border-color: var(--accent);
}
.area {
    height: auto;
    padding: 10px 12px;
    resize: none;
    line-height: 18px;
}
.sw {
    width: 100%;
    height: 40px;
    margin-top: 10px;
    border-radius: 13px;
    background: var(--field);
    border: 1px solid var(--card-line);
    color: var(--soft);
    font-size: 14px;
}
.sw.on {
    border-color: var(--ok);
    color: var(--ok);
    background: rgba(52, 199, 89, 0.08);
}
.two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
}
.link {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    overflow-wrap: anywhere;
    font-size: 13px;
}
.link a {
    color: var(--accent);
}
.div {
    margin: 18px 0 0;
    text-align: center;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.5px;
    color: var(--soft);
    border-top: 1px solid var(--card-line);
    line-height: 0;
}
.div span {
    background: var(--board);
    padding: 0 12px;
}
.del {
    height: 46px;
    padding: 0 16px;
    border-radius: 16px;
    background: rgba(255, 77, 87, 0.12);
    color: var(--danger);
    font-weight: 600;
    font-size: 14px;
}
.save {
    flex: 1;
    height: 46px;
    border-radius: 16px;
    background: var(--accent);
    color: #fff;
    font-weight: 600;
    font-size: 14px;
}
</style>
