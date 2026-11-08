<script setup lang="ts">
import { ref } from 'vue'
import Sheet from './Sheet.vue'
import RequiredMark from './RequiredMark.vue'
import type { FileItem } from '../types'

const props = defineProps<{ note: FileItem | null; taskId?: number | null }>()
const emit = defineEmits<{ close: []; save: [{ text: string; task_id: number | null }]; remove: [FileItem] }>()

const text = ref(props.note?.text ?? props.note?.name ?? '')
const taskId = props.note ? props.note.task_id : props.taskId ?? null
const error = ref('')

function submit() {
  if (!text.value.trim()) { error.value = 'Напиши хоть что-нибудь'; return }
  emit('save', { text: text.value.trim(), task_id: taskId })
}
</script>

<template>
  <Sheet :title="note ? 'Заметка' : 'Новая заметка'" @close="emit('close')">
    <label class="lbl" for="note-text">Текст заметки<RequiredMark /></label>
    <textarea id="note-text" v-model="text" class="field area" rows="7" maxlength="2000" placeholder="Что угодно: что взять с собой, пароль, идея…" autofocus required
              @keydown.enter.ctrl.prevent="submit" @keydown.enter.meta.prevent="submit"></textarea>
    <p v-if="error" class="err">{{ error }}</p>
    <template #footer>
      <button v-if="note" class="del" @click="emit('remove', note!)">Удалить</button>
      <button class="save" @click="submit">Сохранить</button>
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
    height: 42px;
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
    line-height: 19px;
}
.err {
    color: var(--danger);
    font-size: 13px;
    margin: 8px 0 0;
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
