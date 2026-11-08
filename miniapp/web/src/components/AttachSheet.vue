<script setup lang="ts">
import { ref } from 'vue';
import Sheet from './Sheet.vue';
import type { Task } from '../types';
import imageIcon from '../assets/icons/image.svg';
import linkIcon from '../assets/icons/link.svg';
import noteIcon from '../assets/icons/note.svg';
defineProps<{
  task: Task;
}>();
const emit = defineEmits<{
  close: [];
  files: [File[]];
  link: [string];
  note: [string];
}>();
const mode = ref<'menu' | 'link' | 'note'>('menu');
const link = ref('');
const note = ref('');
const input = ref<HTMLInputElement>();
function onFiles(e: Event) {
  const files = Array.from((e.target as HTMLInputElement).files ?? []);
  if (files.length) {
    emit('files', files);
  }
}
const sendLink = () => {
  if (link.value.trim()) {
    emit('link', link.value.trim());
  }
};
const sendNote = () => {
  if (note.value.trim()) {
    emit('note', note.value.trim());
  }
};
</script>

<template>
  <Sheet title="Добавить" :subtitle="task.title" @close="emit('close')">
    <div v-if="mode === 'menu'" class="opts">
      <button class="opt" @click="input?.click()"><span class="ic"><img :src="imageIcon" alt="" /></span><b>Фото или файл</b><small>с телефона или компьютера</small></button>
      <button class="opt" @click="mode = 'link'"><span class="ic"><img :src="linkIcon" alt="" /></span><b>Ссылка</b><small>сайт, видео, документ в облаке</small></button>
      <button class="opt" @click="mode = 'note'"><span class="ic"><img :src="noteIcon" alt="" /></span><b>Заметка</b><small>что угодно текстом</small></button>
      <input ref="input" type="file" multiple hidden @change="onFiles" />
      <p class="tip">Файлы можно и просто перетащить на карточку задания на карте.</p>
    </div>
    <template v-else-if="mode === 'link'">
      <input v-model="link" class="field" placeholder="Вставь ссылку…" autofocus @keydown.enter="sendLink" />
    </template>
    <template v-else>
      <textarea v-model="note" class="field area" rows="5" maxlength="2000" placeholder="Например: взять калькулятор и линейку" autofocus
                @keydown.enter.ctrl.prevent="sendNote" @keydown.enter.meta.prevent="sendNote"></textarea>
    </template>
    <template v-if="mode !== 'menu'" #footer>
      <button class="back" @click="mode = 'menu'">Назад</button>
      <button class="save" @click="mode === 'link' ? sendLink() : sendNote()">Добавить</button>
    </template>
  </Sheet>
</template>

<style scoped>
.opts {
    display: grid;
    gap: 8px;
}
.opt {
    display: grid;
    grid-template-columns: 44px 1fr;
    grid-template-rows: auto auto;
    column-gap: 12px;
    align-items: center;
    text-align: left;
    padding: 12px;
    border-radius: 18px;
    background: var(--card);
    border: 1px solid var(--card-line);
}
.opt:hover {
    border-color: var(--accent);
}
.ic {
    grid-row: 1 / 3;
    width: 44px;
    height: 44px;
    border-radius: 14px;
    background: var(--ico-bg);
    display: grid;
    place-items: center;
}
.ic img {
    width: 18px;
    height: 18px;
}
.opt b {
    font-weight: 600;
    font-size: 14.5px;
}
.opt small {
    color: var(--soft);
    font-size: 12px;
}
.tip {
    margin: 6px 4px 0;
    color: var(--soft);
    font-size: 12px;
}
.field {
    width: 100%;
    height: 44px;
    border-radius: 13px;
    background: var(--field);
    border: 1px solid transparent;
    padding: 0 12px;
    font-size: 14px;
    outline: none;
}
.field:focus {
    border-color: var(--accent);
}
.area {
    height: auto;
    padding: 10px 12px;
    resize: none;
    line-height: 19px;
}
.back {
    height: 46px;
    padding: 0 18px;
    border-radius: 16px;
    background: var(--field);
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
