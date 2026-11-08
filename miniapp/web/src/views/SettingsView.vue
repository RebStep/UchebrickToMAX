<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { clearSession, createAliceCode, createAlicePrivate, createBrowserLink, deleteAlicePrivate, getSettings, logoutBrowsers, saveSettings, unlinkAlice, type Settings, type SettingsPatch } from '../api';
import { applyLook, flushUndo, look, state, toast, type MapBg, type Theme, type Palette } from '../store';
import { MODES, THEMES } from '../themes';
import { createSettingsSaver, waitForSettingsSaves } from '../settingsSaver';
import ConfirmDialog from '../components/ConfirmDialog.vue';
const MOCK = import.meta.env.VITE_MOCK === '1';
const s = reactive<Settings>({
  tz: 'Europe/Samara', quiet_from: '22:00', quiet_to: '07:00', repeat_min: 60, repeat_max: 5, ics_url: '',
  remind_mode: 'all', work_schedule: 'classic', morning_at: null, alice_enabled: MOCK, alice_linked: false, alice_private_url: null
});
const loaded = ref(MOCK);
const quietOff = computed(() => s.quiet_from === s.quiet_to);
const error = ref('');
const saving = ref(false);
const actionBusy = ref(false);
const confirmAction = ref<'logout' | 'unlink' | 'private-off' | null>(null);
const aliceMode = ref<'private' | 'public'>('private');
const aliceCode = ref('');
const aliceUntil = ref(0);
const clock = ref(Date.now());
const aliceSeconds = computed(() => Math.max(0, Math.ceil((aliceUntil.value - clock.value) / 1000)));
let clockTimer = 0;
const isMiniApp = Boolean(window.WebApp?.initData);
async function load() {
  if (MOCK) {
    return;
  }
  try {
    await waitForSettingsSaves();
    Object.assign(s, await getSettings());
    loaded.value = true;
    error.value = '';
  }
  catch {
    error.value = 'Настройки не загрузились. Попробуй ещё раз.';
  }
}
onMounted(load);
const saver = createSettingsSaver({
  request: saveSettings,
  accepted: (settings, pending) => { Object.assign(s, settings, pending); error.value = ''; toast('Сохранено'); },
  failed: () => { error.value = 'Не удалось сохранить настройки. Нажми «Повторить».'; toast('Настройки не сохранились'); },
  busy: (value) => { saving.value = value; },
});
function save(patch: SettingsPatch) {
  if (!loaded.value) {
    return;
  }
  Object.assign(s, patch);
  error.value = '';
  if (MOCK) {
    toast('Сохранено');
  }
  else {
    saver.save(patch);
  }
}
onBeforeUnmount(() => {
  clearInterval(clockTimer); if (!MOCK) {
    void saver.flush();
  }
});
function toggleQuiet() {
  save(!quietOff.value ? { quiet_from: '00:00', quiet_to: '00:00' } : { quiet_from: '22:00', quiet_to: '07:00' });
}
function setTime(key: 'quiet_from' | 'quiet_to' | 'morning_at', event: Event) {
  const value = (event.target as HTMLInputElement).value;
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(value)) {
    error.value = 'Укажи время в формате ЧЧ:ММ';
    return;
  }
  if (key === 'morning_at' && value >= '12:00') {
    error.value = 'Для утреннего плана выбери время до 12:00';
    return;
  }
  save({ [key]: value });
}
async function linkAlice() {
  if (actionBusy.value) {
    return;
  }
  actionBusy.value = true;
  try {
    const result = MOCK ? { code: '123456', expires_in: 300 } : await createAliceCode();
    aliceCode.value = result.code;
    clock.value = Date.now();
    aliceUntil.value = clock.value + result.expires_in * 1000;
    clearInterval(clockTimer);
    clockTimer = window.setInterval(() => {
      clock.value = Date.now();
      if (!aliceSeconds.value) {
        aliceCode.value = '';
        clearInterval(clockTimer);
      }
    }, 1000);
  }
  catch {
    error.value = 'Не удалось получить код Алисы. Попробуй ещё раз.';
  }
  finally {
    actionBusy.value = false;
  }
}
async function confirm() {
  const action = confirmAction.value;
  confirmAction.value = null;
  if (!action || actionBusy.value) {
    return;
  }
  actionBusy.value = true;
  try {
    if (action === 'unlink') {
      if (!MOCK) {
        await unlinkAlice();
      }
      s.alice_linked = false;
      aliceCode.value = '';
      clearInterval(clockTimer);
      toast('Алиса отвязана');
    }
    else if (action === 'private-off') {
      if (!MOCK) {
        await deleteAlicePrivate();
      }
      s.alice_private_url = null;
      toast('Приватный навык отключён');
    }
    else {
      if (MOCK) {
        toast('В демо-режиме сессий нет');
        return;
      }
      if (!await saver.flush()) {
        return;
      }
      await waitForSettingsSaves();
      await flushUndo();
      await logoutBrowsers();
      clearSession();
      state.tasks = [];
      state.olympiads = [];
      state.loose = [];
      state.error = 'Сессии завершены. Открой карту из бота для нового входа.';
      state.tab = 'map';
    }
  }
  catch {
    error.value = 'Не получилось. Попробуй ещё раз.';
  }
  finally {
    actionBusy.value = false;
  }
}
async function openBrowser() {
  if (actionBusy.value) {
    return;
  }
  const target = window.open('', '_blank');
  if (!target) {
    error.value = 'Разреши открытие новой вкладки и попробуй ещё раз';
    return;
  }
  target.opener = null;
  actionBusy.value = true;
  try {
    if (MOCK) {
      target.location.href = location.origin;
      return;
    }
    const { url } = await createBrowserLink();
    target.location.href = url;
  }
  catch {
    target.close();
    error.value = 'Не удалось открыть карту в браузере';
  }
  finally {
    actionBusy.value = false;
  }
}
const setLook = (patch: Partial<{
  mapBg: MapBg;
  theme: Theme;
  palette: Palette;
}>) => { Object.assign(look, patch); applyLook(); };
function selectPalette(palette: Palette) {
  setLook({ palette, ...(palette === 'plain-dark' ? { theme: 'dark' as const } : palette === 'plain-light' ? { theme: 'light' as const } : {}) });
}
async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Ссылка скопирована');
  }
  catch {
    toast('Не скопировалось — выдели ссылку и скопируй вручную');
  }
}
async function getAlicePrivate(reset = false) {
  if (actionBusy.value) {
    return;
  }
  actionBusy.value = true;
  try {
    const result = MOCK ? { url: 'https://example.ru/alice/u/demo-token-for-preview-only' } : await createAlicePrivate(reset);
    s.alice_private_url = result.url;
    if (reset) {
      toast('Новый адрес готов — вставь его в навык');
    }
  }
  catch {
    error.value = 'Не удалось получить адрес. Попробуй ещё раз.';
  }
  finally {
    actionBusy.value = false;
  }
}
const confirmQuestion = computed(() => {
  if (confirmAction.value === 'logout') {
    return 'Выйти из всех браузеров и отключить старые ссылки для входа?';
  }
  if (confirmAction.value === 'private-off') {
    return 'Отключить приватный навык? Старый адрес перестанет работать.';
  }
  return 'Отвязать Алису от профиля?';
});
const confirmLabel = computed(() => {
  if (confirmAction.value === 'logout') {
    return 'Выйти';
  }
  return confirmAction.value === 'private-off' ? 'Отключить' : 'Отвязать';
});
const REPEATS = computed(() => [...new Set([30, 60, 120, s.repeat_min])].sort((a, b) => a - b));
const REPEAT_COUNTS = computed(() => [...new Set([1, 2, 3, 5, s.repeat_max])].sort((a, b) => a - b));
const REMIND_MODES = [
  { id: 'all', label: 'По всем', description: 'Напоминаю по всем заданиям. Отдельные можно выключить в боте.' },
  { id: 'selected', label: 'По выбранным', description: 'Напоминаю только по заданиям, которые выбраны в боте.' },
  { id: 'none', label: 'Никак', description: 'Список дел остаётся доступен, напоминания выключены.' },
] as const;
const WORK_PRESETS = [
  { id: 'classic', label: 'Как обычно', description: 'За сутки до срока.' },
  { id: 'school', label: 'После школы', description: 'Подбираю время после уроков.' },
  { id: 'evening', label: 'Вечером', description: 'Подбираю время на вечер.' },
] as const;
const remindHint = computed(() => REMIND_MODES.find((m) => m.id === s.remind_mode)?.description ?? '');
const workHint = computed(() => WORK_PRESETS.find((p) => p.id === s.work_schedule)?.description ?? '');
const times = (n: number) => `${n} раз${n >= 2 && n <= 4 ? 'а' : ''}`;
const every = (m: number) => {
  if (m < 60) {
    return `${m} мин`;
  }
  return `${m / 60} ч`;
};
const BGS: {
  id: MapBg;
  label: string;
}[] = [{ id: 'dots', label: 'Точки' }, { id: 'grid', label: 'Клетка' }, { id: 'plain', label: 'Чистый' }];
</script>

<template>
  <section class="set">
    <h1>Настройки</h1>
    <p v-if="saving" class="save-status" role="status">Сохраняю…</p>
    <p v-if="error" class="save-error" role="alert">{{ error }} <button @click="loaded ? saver.flush() : load()">Повторить</button></p>
    <div class="scroll">
      <h4>Напоминания</h4>
      <div class="box" :class="{ dim: !loaded }">
        <p class="lbl">По каким заданиям напоминать</p>
        <div class="seg" role="group" aria-label="Режим напоминаний">
          <button v-for="m in REMIND_MODES" :key="m.id" :class="{ on: s.remind_mode === m.id }" :aria-pressed="s.remind_mode === m.id" @click="save({ remind_mode: m.id })">{{ m.label }}</button>
        </div>
        <p class="txt small hint">{{ remindHint }}</p>
        <template v-if="s.remind_mode !== 'none'">
          <div class="pair">
            <div class="col">
              <p class="lbl">Сколько раз напоминать</p>
              <div class="seg wrap" role="group" aria-label="Количество напоминаний"><button v-for="n in REPEAT_COUNTS" :key="n" :class="{ on: s.repeat_max === n }" :aria-pressed="s.repeat_max === n" @click="save({ repeat_max: n })">{{ times(n) }}</button></div>
            </div>
            <div v-if="s.repeat_max > 1" class="col">
              <p class="lbl">Повторять каждые</p>
              <div class="seg wrap" role="group" aria-label="Интервал повторов"><button v-for="m in REPEATS" :key="m" :class="{ on: s.repeat_min === m }" :aria-pressed="s.repeat_min === m" @click="save({ repeat_min: m })">{{ every(m) }}</button></div>
            </div>
          </div>
          <p class="txt small">Повторы приходят, пока не нажмёшь «Сделано» или «Начинаю».</p>
          <p class="lbl">Планирование домашки</p>
          <div class="seg" role="group" aria-label="Планирование домашки">
            <button v-for="p in WORK_PRESETS" :key="p.id" :class="{ on: s.work_schedule === p.id }" :aria-pressed="s.work_schedule === p.id" @click="save({ work_schedule: p.id })">{{ p.label }}</button>
          </div>
          <p class="txt small hint">{{ workHint }}</p>
        </template>
      </div>

      <h4>Распорядок дня</h4>
      <div class="box" :class="{ dim: !loaded }">
        <div class="row">
          <span><b>Тихие часы</b><small>В это время я ничего не присылаю</small></span>
          <button class="sw" role="switch" :aria-checked="!quietOff" :class="{ on: !quietOff }" :aria-label="quietOff ? 'Включить тихие часы' : 'Выключить тихие часы'" @click="toggleQuiet"><i></i></button>
        </div>
        <div v-if="!quietOff" class="times">
          <label>с <input type="time" class="field" :value="s.quiet_from" @change="setTime('quiet_from', $event)" /></label>
          <label>до <input type="time" class="field" :value="s.quiet_to" @change="setTime('quiet_to', $event)" /></label>
        </div>
        <div class="row">
          <span><b>Утренний план</b><small>Присылать список дел на день</small></span>
          <button class="sw" role="switch" :aria-checked="s.morning_at !== null" :class="{ on: s.morning_at !== null }" :aria-label="s.morning_at ? 'Выключить утренний план' : 'Включить утренний план'" @click="save({ morning_at: s.morning_at ? null : '07:30' })"><i></i></button>
        </div>
        <label v-if="s.morning_at" class="morning">Время плана <input type="time" class="field" max="11:59" :value="s.morning_at" @change="setTime('morning_at', $event)" /></label>
        <p class="txt small">Часовой пояс: {{ s.tz }}</p>
      </div>

      <h4>Календарь</h4>
      <div class="box">
        <p class="txt">Сроки заданий в календаре телефона или компьютера. Ссылка личная — никому её не отправляй.</p>
        <div v-if="s.ics_url" class="ics"><input class="field" readonly :value="s.ics_url" @focus="($event.target as HTMLInputElement).select()" /><button class="copy" @click="copyText(s.ics_url)">Копировать</button></div>
        <p v-else class="txt">{{ MOCK ? 'В демо-режиме ссылки нет.' : 'Загружаю…' }}</p>
        <p class="txt small">Яндекс Календарь: «Добавить» → «Подписаться на календарь». Google Календарь (на компьютере): «Другие календари» → «+» → «Добавить по URL».</p>
      </div>
      <h4>Алиса</h4>
      <div class="box" :class="{ dim: !loaded }">
        <p class="lbl">Способ подключения</p>
        <div class="seg" role="group" aria-label="Способ подключения Алисы">
          <button :class="{ on: aliceMode === 'private' }" :aria-pressed="aliceMode === 'private'" @click="aliceMode = 'private'">Приватный (для теста)</button>
          <button :class="{ on: aliceMode === 'public' }" :aria-pressed="aliceMode === 'public'" @click="aliceMode = 'public'">Публичный (нужна модерация)</button>
        </div>
        <template v-if="aliceMode === 'private'">
          <p class="txt small hint">Свой навык в твоём кабинете Яндекса. Работает только с твоего аккаунта, модерация приватного навыка проходит почти сразу. Так можно проверить, что Алиса действительно работает с Учебриком.</p>
          <template v-if="s.alice_private_url">
            <div class="ics"><input class="field" readonly :value="s.alice_private_url" @focus="($event.target as HTMLInputElement).select()" /><button class="copy" @click="copyText(s.alice_private_url!)">Копировать</button></div>
            <ol class="steps">
              <li>Скопируй адрес выше. Он личный, никому его не отправляй.</li>
              <li>Открой <b>dialogs.yandex.ru/developer</b> → «Создать навык Алисы».</li>
              <li>Заполни обязательные поля: название, описание, примеры запросов, голос, категорию, имя разработчика и иконку. Всё можно кратко.</li>
              <li>В разделе Backend выбери «Webhook URL» и вставь адрес.</li>
              <li>Нажми «Сохранить», затем «Отправить на модерацию». У приватного навыка она проходит почти автоматически.</li>
              <li>Когда модерация пройдена, нажми «Опубликовать». Это тоже быстро. Навык заработает только после этих трёх шагов.</li>
              <li>Открой вкладку «Тестирование» (или скажи колонке с тем же аккаунтом): «что задано» или продиктуй задание, но перед этим привяжи его (следуя инструкии Алисы). Задание придёт в MAX черновиком.</li>
            </ol>
            <button class="action" :disabled="actionBusy" @click="getAlicePrivate(true)">Выдать новый адрес</button>
            <button class="action danger-text" :disabled="actionBusy" @click="confirmAction = 'private-off'">Отключить приватный навык</button>
          </template>
          <button v-else class="action" :disabled="actionBusy" @click="getAlicePrivate()">Получить адрес для навыка</button>
        </template>
        <template v-else-if="s.alice_enabled">
          <p class="txt small hint">Общий навык «Учебрик» в каталоге Алисы. Появится после модерации Яндекса.</p>
        <p class="txt">{{ s.alice_linked ? 'Алиса привязана к твоему профилю.' : 'Подключи навык «Учебрик», чтобы записывать задания голосом и узнавать ближайшие дела.' }}</p>
        <div v-if="aliceCode && aliceSeconds" class="alice-code" role="status"><b>{{ aliceCode }}</b><span>Скажи в навыке «Учебрик»: «привяжи {{ aliceCode }}».</span><small>Код действует ещё {{ Math.floor(aliceSeconds / 60) }}:{{ String(aliceSeconds % 60).padStart(2, '0') }}</small></div>
        <button class="action" :disabled="actionBusy" @click="linkAlice">{{ aliceCode ? 'Новый код' : 'Привязать Алису' }}</button>
        <button v-if="s.alice_linked || aliceCode" class="action danger-text" :disabled="actionBusy" @click="confirmAction = 'unlink'">Отвязать Алису</button>
        </template>
        <p v-else class="txt small hint">Общий навык пока не подключён на этом сервере. Для проверки используй приватный.</p>
      </div>

      <h4>Браузеры</h4>
      <div class="box" :class="{ dim: !loaded }">
        <button v-if="isMiniApp" class="action" :disabled="actionBusy" @click="openBrowser">Открыть карту в браузере</button>
        <p class="txt">Заверши все сеансы карты и отключи старые ссылки для входа.</p>
        <button class="action danger-text" :disabled="actionBusy" @click="confirmAction = 'logout'">Выйти из всех браузеров</button>
      </div>

      <h4>Оформление</h4>
      <div class="box">
        <p class="lbl">Тема</p>
        <div class="seg" role="group" aria-label="Светлая или тёмная тема"><button v-for="m in MODES" :key="m.id" :class="{ on: look.theme === m.id }" :aria-pressed="look.theme === m.id" @click="setLook({ theme: m.id })">{{ m.label }}</button></div>
        <p class="lbl">Тема оформления</p>
        <div class="themes" role="group" aria-label="Тема оформления">
          <button v-for="t in THEMES" :key="t.id" class="theme" :class="{ on: look.palette === t.id }" :aria-pressed="look.palette === t.id" @click="selectPalette(t.id)">
            <span class="theme-preview" :class="t.id" :style="{ backgroundColor: t.color, '--preview-card': t.incoming, '--preview-accent': t.outgoing }" aria-hidden="true"><i></i><i></i><span v-if="look.palette === t.id" class="theme-check">✓</span></span>
            <b>{{ t.label }}</b><small>{{ t.description }}</small>
          </button>
        </div>
        <p class="lbl">Фон карты</p>
        <div class="bgs">
          <button v-for="b in BGS" :key="b.id" class="bg" :class="{ on: look.mapBg === b.id }" @click="setLook({ mapBg: b.id })">
            <span class="pv" :class="b.id"></span>{{ b.label }}
          </button>
        </div>
      </div>

    </div>
    <ConfirmDialog v-if="confirmAction" :question="confirmQuestion" :confirm-label="confirmLabel" danger @cancel="confirmAction = null" @confirm="confirm" />
  </section>
</template>

<style scoped>
.save-status,
.save-error {
    margin: 4px 4px 8px;
    font-size: 13px;
}
.save-status {
    color: var(--soft);
}
.save-error {
    color: var(--danger);
}
.save-error button {
    color: var(--accent);
    text-decoration: underline;
    margin-left: 6px;
}
.hint {
    margin: -4px 2px 2px;
}
.pair {
    display: grid;
    gap: 8px;
}
.col {
    display: grid;
    gap: 6px;
    align-content: start;
    min-width: 0;
}
@media (min-width: 600px) {
    .pair {
        grid-template-columns: 1fr 1fr;
        gap: 16px;
    }
}
.seg.wrap {
    display: flex;
    flex-wrap: wrap;
}
.seg.wrap button {
    flex: 1;
    min-width: 56px;
    padding: 0 8px;
}
.morning {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 13px;
    color: var(--soft);
}
.morning .field {
    width: 110px;
}
.action {
    min-height: 38px;
    padding: 10px 16px;
    border: 1px solid var(--card-line);
    border-radius: 21px;
    background: var(--chip);
    font-size: 14px;
    font-weight: 500;
}
.action:disabled {
    opacity: 0.5;
}
.danger-text {
    color: var(--danger);
}
.alice-code {
    display: grid;
    gap: 8px;
    text-align: center;
    padding: 14px;
    border-radius: 18px;
    background: var(--board);
    font-size: 13px;
}
.alice-code b {
    font-size: 28px;
    letter-spacing: 5px;
}
.alice-code small {
    color: var(--soft);
}

.set {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    padding: calc(12px + var(--safe-top)) 16px 0;
    background: var(--screen);
}
h1 {
    margin: 0 0 4px;
    font-weight: 600;
    font-size: 24px;
}
.scroll {
    flex: 1;
    overflow-y: auto;
    scrollbar-width: none;
    padding-bottom: 100px;
}
h4 {
    margin: 14px 4px 6px;
    font-weight: 500;
    font-size: 12px;
    color: var(--soft);
}
.box {
    background: var(--card);
    border: 1px solid var(--card-line);
    border-radius: 18px;
    padding: 12px;
    display: grid;
    gap: 8px;
    transition: opacity 0.2s;
}
.box.dim {
    opacity: 0.5;
    pointer-events: none;
}
.lbl {
    margin: 2px 2px 0;
    font-size: 12px;
    color: var(--soft);
}
.themes {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
}
.theme {
    min-width: 0;
    display: grid;
    align-content: start;
    gap: 5px;
    padding: 6px 6px 8px;
    border: 1.5px solid var(--card-line);
    border-radius: 16px;
    background: var(--board);
    text-align: left;
}
.theme.on {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
}
.theme:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
}
.theme b,
.theme small {
    padding: 0 4px;
}
.theme b {
    font-size: 13px;
    font-weight: 600;
}
.theme small {
    color: var(--soft);
    font-size: 11px;
    line-height: 1.35;
}
.theme-preview {
    height: 48px;
    border-radius: 13px;
    position: relative;
    overflow: hidden;
    display: grid;
    align-content: center;
    gap: 4px;
    padding: 8px;
}
.theme-preview.lavender {
    background:
        radial-gradient(at 0% 100%, #b17aff, transparent 70%), radial-gradient(at 100% 100%, #66dcff, transparent 70%),
        #faf7ff;
}
.theme-preview i {
    display: block;
    width: 60%;
    height: 12px;
    border-radius: 9px;
    background: var(--preview-card);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}
.theme-preview i + i {
    width: 58%;
    height: 12px;
    justify-self: end;
    background: var(--preview-accent);
}
.theme-check {
    position: absolute;
    right: 8px;
    top: 8px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: #fff;
    color: #471aff;
    font-size: 12px;
    font-weight: 600;
}
@media (min-width: 600px) {
    .themes {
        grid-template-columns: repeat(4, minmax(0, 1fr));
    }
}
.seg {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 1fr;
    gap: 6px;
}
.seg button {
    height: 34px;
    border-radius: 11px;
    background: var(--chip);
    color: var(--soft);
    font-weight: 500;
    font-size: 13px;
}
.seg button.on {
    background: var(--accent);
    color: #fff;
    font-weight: 600;
}
.bgs {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
}
.bg {
    display: grid;
    gap: 6px;
    justify-items: center;
    padding: 8px;
    border-radius: 16px;
    background: var(--chip);
    border: 1.5px solid transparent;
    font-size: 13px;
    color: var(--soft);
}
.bg.on {
    border-color: var(--accent);
    color: var(--ink);
}
.pv {
    width: 100%;
    height: 40px;
    border-radius: 11px;
    background-color: var(--screen);
}
.pv.dots {
    background-image: radial-gradient(var(--dot) 1.3px, transparent 1.7px);
    background-size: 12px 12px;
}
.pv.grid {
    background-image:
        linear-gradient(var(--grid-line) 1px, transparent 1px),
        linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
    background-size: 12px 12px;
}
.row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}
.row span:first-child {
    display: grid;
    gap: 2px;
}
.row b {
    font-weight: 600;
    font-size: 14.5px;
}
.row small {
    color: var(--soft);
    font-size: 12px;
}
.sw {
    width: 50px;
    height: 30px;
    border-radius: 15px;
    background: var(--chip);
    position: relative;
    flex: none;
}
.sw i {
    position: absolute;
    left: 3px;
    top: 3px;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: #fff;
    transition: translate 0.2s var(--ease-out);
}
.sw.on {
    background: var(--ok);
}
.sw.on i {
    translate: 20px 0;
}
.times {
    display: flex;
    gap: 10px;
}
.times label {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--soft);
    font-size: 13px;
}
.field {
    width: 100%;
    height: 40px;
    border-radius: 13px;
    background: var(--chip);
    border: 1px solid transparent;
    padding: 0 12px;
    font-size: 14px;
    outline: none;
    color-scheme: var(--scheme);
}
.field:focus {
    border-color: var(--accent);
}
.step {
    display: flex;
    align-items: center;
    gap: 10px;
}
.step button {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: var(--chip);
    font-size: 18px;
    font-weight: 600;
}
.step button:disabled {
    opacity: 0.35;
}
.step b {
    min-width: 20px;
    text-align: center;
}
.txt {
    margin: 0;
    font-size: 13px;
    line-height: 1.45;
    color: var(--soft);
}
.txt.small {
    font-size: 12px;
}
.ics {
    display: flex;
    gap: 8px;
}
.steps {
    margin: 0;
    padding-left: 18px;
    display: grid;
    gap: 4px;
    font-size: 12px;
    line-height: 1.45;
    color: var(--soft);
}
.steps b {
    color: var(--ink);
    font-weight: 600;
}
.copy {
    height: 40px;
    padding: 0 14px;
    border-radius: 13px;
    background: var(--accent);
    color: #fff;
    font-weight: 600;
    font-size: 13.5px;
    flex: none;
}
@media (min-width: 1024px) {
    .set {
        padding: 28px max(32px, calc((100% - var(--nav-space, 264px) - 720px) / 2)) 0
            calc(var(--nav-space, 264px) + max(32px, calc((100% - var(--nav-space, 264px) - 720px) / 2)));
    }
    .scroll {
        padding-bottom: 40px;
    }
}
</style>
