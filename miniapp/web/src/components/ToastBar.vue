<script setup lang="ts">
defineProps<{ text: string }>()
</script>

<template>
  <div v-if="text" class="toast" role="status">{{ text }}</div>
</template>

<style scoped>
.toast {
    position: fixed;
    left: 50%;
    top: calc(64px + var(--safe-top));
    transform: translateX(-50%);
    z-index: 50;
    padding: 0 22px;
    height: 44px;
    display: flex;
    align-items: center;
    border-radius: 22px;
    background: var(--bar);
    border: 1px solid var(--bar-line);
    font-weight: 600;
    font-size: 14px;
    white-space: nowrap;
}
@media (min-width: 1024px) {
    .toast {
        left: calc(50% + var(--nav-space, 264px) / 2);
        top: auto;
        bottom: 90px;
    }
}
</style>
