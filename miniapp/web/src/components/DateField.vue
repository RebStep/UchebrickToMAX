<script setup lang="ts">
import { ref, watch } from 'vue';
import calIcon from '../assets/icons/calendar-small.svg';
import { isoToText, maskDate, resolveDate } from '../dateInput';
import { local } from '../format';
const props = withDefaults(defineProps<{
  modelValue: string;
  withPicker?: boolean;
  placeholder?: string;
}>(), { withPicker: true, placeholder: 'дд.мм' });
const emit = defineEmits<{
  'update:modelValue': [string];
}>();
const text = ref(isoToText(props.modelValue));
const picker = ref<HTMLInputElement>();
watch(() => props.modelValue, (v) => {
  if (isoToText(v) !== text.value) {
    text.value = isoToText(v);
  }
});
function onInput(e: Event) {
  const input = e.target as HTMLInputElement;
  const masked = maskDate(input.value);
  input.value = masked;
  text.value = masked;
}
function commit() {
  if (!text.value.trim()) {
    return emit('update:modelValue', '');
  }
  const now = local(new Date());
  const iso = resolveDate(text.value, { y: now.y, m: now.m, d: now.d });
  if (iso) {
    emit('update:modelValue', iso);
    text.value = isoToText(iso);
  }
  else {
    text.value = isoToText(props.modelValue);
  }
}
</script>

<template>
  <div class="df">
    <input :value="text" class="field" inputmode="numeric" autocomplete="off" maxlength="10" :placeholder="placeholder" @input="onInput" @blur="commit" @keydown.enter.prevent="commit" />
    <button v-if="withPicker" class="cal" type="button" aria-label="Выбрать дату" @click="picker?.showPicker?.()"><img :src="calIcon" alt="" /></button>
    <input ref="picker" class="native" type="date" tabindex="-1" :value="modelValue" @change="emit('update:modelValue', ($event.target as HTMLInputElement).value)" />
  </div>
</template>

<style scoped>
.df {
    position: relative;
    display: flex;
    gap: 6px;
    flex: 1;
    min-width: 0;
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
}
.field:focus {
    border-color: var(--accent);
}
.field::placeholder {
    color: var(--soft);
}
.cal {
    width: 39px;
    height: 40px;
    border-radius: 13px;
    background: var(--field);
    display: grid;
    place-items: center;
    flex: none;
}
.cal img {
    width: 17px;
    height: 18px;
}
.native {
    position: absolute;
    right: 0;
    bottom: 0;
    width: 1px;
    height: 1px;
    opacity: 0;
    pointer-events: none;
    color-scheme: var(--scheme);
}
</style>
