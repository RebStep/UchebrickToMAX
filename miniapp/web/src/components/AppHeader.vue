<script setup lang="ts">
import logoSquare from '../assets/icons/logo-square.svg'
import logoGlyph from '../assets/icons/logo-glyph.svg'

defineProps<{ compact?: boolean }>()
</script>

<template>
  <div class="brand-header" :class="{ compact }">
    <span class="logo" aria-hidden="true">
      <img :src="logoSquare" alt="" class="sq" />
      <img :src="logoGlyph" alt="" class="gl" />
    </span>
    <span v-if="!compact" class="name">Учебрик</span>
  </div>
</template>

<style scoped>
.brand-header {
    height: 46px;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 10px;
    min-width: 0;
}
.compact {
    justify-content: center;
}
.logo {
    position: relative;
    width: 32px;
    height: 32px;
    display: block;
    flex-shrink: 0;
}
.sq {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
}
.gl {
    position: absolute;
    left: 27.2727%;
    top: 22.7273%;
    width: 46.3636%;
    height: 55%;
}
.name {
    font-weight: 600;
    font-size: 19px;
    color: var(--ink);
}
</style>
