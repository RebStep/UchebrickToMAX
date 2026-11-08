<script setup lang="ts">
import { computed } from 'vue';
import type { Task } from '../types';
import { dueLabel, local, dateLong, timeText } from '../format';
import { subjectColors } from '../subjects';
import editIcon from '../assets/icons/card-edit.svg';
import attachIcon from '../assets/icons/card-attach.svg';
import checkIcon from '../assets/icons/card-check.svg';
import pinIcon from '../assets/icons/pin.svg';
const props = defineProps<{
  task: Task;
  selected?: boolean;
}>();
defineEmits<{
  edit: [];
  attach: [];
  done: [];
}>();
const done = computed(() => props.task.status === 'done');
const isEvent = computed(() => props.task.kind === 'event' || props.task.kind === 'olympiad');
const colors = computed(() => subjectColors(props.task.kind === 'olympiad' ? 'олимпиада' : props.task.subject));
const KIND_LABEL: Record<string, string> = { homework: 'Домашка', todo: 'Дело', event: 'Событие', project: 'Проект', olympiad: 'Олимпиада' };
const label = computed(() => {
  if (props.task.kind === 'olympiad') {
    return 'Олимпиада';
  }
  return props.task.subject ?? KIND_LABEL[props.task.kind] ?? 'Дело';
});
const due = computed(() => dueLabel(props.task.due_at, done.value));
const overdue = computed(() => !done.value && due.value.tone === 'overdue');
const when = computed(() => {
  if (!props.task.due_at) {
    return '';
  }
  return `${dateLong(local(props.task.due_at))}, ${timeText(props.task.due_at)}`;
});
const reg = computed(() => {
  if (!props.task.reg_deadline) {
    return '';
  }
  return `регистрация до ${dateLong(local(props.task.reg_deadline))}`;
});
</script>

<template>
  <article class="card" :class="{ event: isEvent, overdue, done, selected }" data-card>
    <header class="top">
      <span class="plaque" :style="{ background: colors.bg, color: colors.text }">{{ label }}</span>
      <div class="acts">
        <button aria-label="Изменить" @click.stop="$emit('edit')"><img :src="editIcon" alt="" /></button>
        <button aria-label="Прикрепить" @click.stop="$emit('attach')"><img :src="attachIcon" alt="" /></button>
        <button aria-label="Сделано" @click.stop="$emit('done')"><img :src="checkIcon" alt="" /></button>
      </div>
    </header>

    <template v-if="isEvent">
      <p class="type">СОБЫТИЕ</p>
      <h3 class="title">{{ task.title }}</h3>
      <p v-if="when" class="when">{{ when }}</p>
      <p v-if="task.location" class="place"><img :src="pinIcon" alt="" />{{ task.location }}</p>
      <p v-if="reg" class="reg">{{ reg }}</p>
    </template>
    <template v-else>
      <h3 class="title">{{ task.title }}</h3>
      <footer class="bottom">
        <span class="pill" :class="done ? 'done' : due.tone">{{ due.text }}</span>
        <span v-if="task.location" class="loc">{{ task.location }}<img :src="pinIcon" alt="" /></span>
      </footer>
    </template>
  </article>
</template>

<style scoped>
.card {
    width: 252px;
    padding: 14px 14px 17px;
    border-radius: 26px;
    background: var(--card);
    border: 1px solid var(--card-line);
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
    cursor: grab;
}
.card.overdue {
    border: 1.5px solid var(--danger);
    padding: 13.5px 13.5px 16.5px;
}
.card.event {
    border: 2px solid var(--purple);
    padding: 13px 13px 16px;
}
.card.selected {
    border-color: var(--accent);
    box-shadow: inset 0 0 0 1px var(--accent);
}
.top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 28px;
}
.plaque {
    height: 28px;
    border-radius: 14px;
    padding: 0 9px;
    display: inline-flex;
    align-items: center;
    font-weight: 600;
    font-size: 12.5px;
    white-space: nowrap;
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
}
.acts {
    display: flex;
    gap: 4px;
}
.acts button {
    width: 28px;
    height: 28px;
    display: block;
}
.acts img {
    width: 28px;
    height: 28px;
}
.title {
    margin: 17px 0 0;
    font-weight: 600;
    font-size: 15.5px;
    line-height: 19px;
    color: var(--ink);
    overflow-wrap: anywhere;
}
.done .title {
    color: var(--soft);
    text-decoration: line-through;
}
.bottom {
    margin-top: 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 28px;
}
.pill {
    height: 28px;
    border-radius: 18px;
    padding: 0 14px;
    display: inline-flex;
    align-items: center;
    font-weight: 500;
    font-size: 13px;
    background: var(--chip);
    color: var(--ink);
}
.pill.today {
    background: var(--accent);
    color: #fff;
}
.pill.overdue {
    background: var(--danger);
    color: #fff;
}
.pill.done {
    color: var(--soft);
}
.loc {
    font-size: 12.5px;
    color: var(--soft);
    display: inline-flex;
    align-items: center;
    gap: 4px;
}
.loc img,
.place img {
    width: 10px;
    height: 11px;
}
.type {
    margin: 18px 0 0;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.6px;
    color: var(--soft);
}
.event .title {
    margin-top: 5px;
}
.when {
    margin: 10px 0 0;
    font-weight: 600;
    font-size: 21px;
    line-height: 25px;
    color: var(--ink);
}
.place {
    margin: 9px 0 0;
    font-size: 12.5px;
    color: var(--soft);
    display: flex;
    align-items: center;
    gap: 7px;
}
.reg {
    margin: 7px 0 0;
    font-weight: 600;
    font-size: 12.5px;
    color: var(--danger);
}
</style>
