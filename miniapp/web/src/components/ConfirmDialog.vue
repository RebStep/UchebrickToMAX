<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue';
import warningIcon from '../assets/icons/warning.svg';
defineProps<{
  question: string;
  confirmLabel: string;
  danger?: boolean;
}>();
const emit = defineEmits<{
  cancel: [];
  confirm: [];
}>();
const onKey = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    emit('cancel');
  }
  if (e.key === 'Enter') {
    emit('confirm');
  }
};
onMounted(() => window.addEventListener('keydown', onKey));
onBeforeUnmount(() => window.removeEventListener('keydown', onKey));
</script>

<template>
  <div class="shade" @pointerdown.self="emit('cancel')">
    <div class="dlg" role="alertdialog" aria-modal="true">
      <img :src="warningIcon" alt="" class="ic" />
      <p>{{ question }}</p>
      <div class="btns">
        <div><button class="cancel" @click="emit('cancel')">Отмена</button><small>Esc</small></div>
        <div><button :class="danger ? 'danger' : 'ok'" @click="emit('confirm')">{{ confirmLabel }}</button><small>Enter</small></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.shade {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: var(--shade);
    display: grid;
    place-items: center;
    padding: 24px;
    animation: ui-fade 0.16s ease both;
}
.dlg {
    animation: ui-pop 0.24s var(--spring) both;
}
.dlg {
    position: relative;
    width: 100%;
    max-width: 380px;
    background: var(--board);
    border: 1px solid var(--bar-line);
    border-radius: 30px;
    padding: 40px 16px 14px;
    text-align: center;
}
.ic {
    position: absolute;
    left: 50%;
    top: -24px;
    transform: translateX(-50%);
    width: 49px;
    height: 49px;
}
p {
    margin: 0 0 22px;
    font-weight: 600;
    font-size: 16px;
}
.btns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
}
.btns small {
    display: block;
    margin-top: 4px;
    font-size: 11px;
    color: var(--soft);
}
button {
    width: 100%;
    height: 46px;
    border-radius: 16px;
    font-weight: 600;
    font-size: 14px;
}
.cancel {
    background: var(--chip);
}
.danger {
    background: var(--danger);
    color: #fff;
}
.ok {
    background: var(--accent);
    color: #fff;
}
</style>
