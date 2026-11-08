<script setup lang="ts">
import fitIcon from '../assets/icons/zoom-fit.svg'
defineEmits<{ in: []; out: []; fit: [] }>()
</script>

<template>
  <div class="zoom">
    <button aria-label="Отдалить" @click="$emit('out')">−</button>
    <span class="sep"></span>
    <button aria-label="Показать всё" @click="$emit('fit')"><img :src="fitIcon" alt="" /></button>
    <span class="sep"></span>
    <button aria-label="Приблизить" @click="$emit('in')">+</button>
  </div>
</template>

<style scoped>
.zoom {
    position: relative;
    height: 50px;
    width: 134px;
    border-radius: 999px;
    background: var(--glass-background);
    border: 1px solid var(--bar-line);
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr) 1px) minmax(0, 1fr);
    align-items: center;
    padding: 5px;
    overflow: hidden;
}
button {
    width: 38px;
    min-width: 0;
    height: 38px;
    justify-self: center;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-weight: 600;
    font-size: 22px;
    color: var(--ink);
}
button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -3px;
}
@media (hover: hover) {
    button:hover {
        background: var(--glass-hover);
        box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.18);
    }
}
button img {
    width: 12px;
    height: 12px;
}
.sep {
    width: 1px;
    height: 24px;
    background: var(--bar-line);
}
</style>
