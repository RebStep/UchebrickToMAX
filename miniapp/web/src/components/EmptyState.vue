<template>
  <div class="empty">
    <h2>Пока пусто</h2>
    <p>Пришли боту задание текстом или перешли сообщение учителя. Оно появится здесь.</p>
  </div>
</template>

<style scoped>
.empty {
    position: absolute;
    left: 50%;
    top: 42%;
    transform: translate(-50%, -50%);
    width: 320px;
    max-width: 90%;
    text-align: center;
    pointer-events: none;
    z-index: 1;
}
h2 {
    margin: 0 0 10px;
    font-weight: 600;
    font-size: 22px;
}
p {
    margin: 0;
    font-size: 14px;
    line-height: 17px;
    color: var(--soft);
}
</style>
