<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { fileUrl } from '../api';
import { serverFileId } from '../store';
import type { FileItem } from '../types';
import imageIcon from '../assets/icons/image.svg';
import docIcon from '../assets/icons/doc.svg';
import linkIcon from '../assets/icons/link.svg';
import noteIcon from '../assets/icons/note-add.svg?raw';
const props = defineProps<{
  file: FileItem;
}>();
const src = ref<string | null>(null);
onMounted(async () => {
  const id = serverFileId(props.file);
  if (props.file.type !== 'photo' || !id) {
    return;
  }
  try {
    src.value = await fileUrl(id);
  }
  catch {
    src.value = null;
  }
});
</script>

<template>
  <div v-if="file.type === 'photo'" class="photo" data-card>
    <div class="img" :style="src ? { backgroundImage: `url(${src})` } : {}"><img v-if="!src" :src="imageIcon" alt="" /></div>
    <span class="cap">{{ file.name }}</span>
  </div>
  <div v-else-if="file.type === 'doc'" class="doc" data-card>
    <span class="ico"><img :src="docIcon" alt="" /></span>
    <span class="txt"><b>{{ file.name }}</b><i>{{ file.hint ?? 'отправить в чат' }}</i></span>
  </div>
  <div v-else-if="file.type === 'note'" class="notec" data-card>
    <span class="note-icon" aria-hidden="true" v-html="noteIcon"></span>
    <p>{{ file.text ?? file.name }}</p>
  </div>
  <div v-else class="chipf" data-card>
    <img :src="linkIcon" alt="" />
    <b>{{ file.name }}</b>
  </div>
</template>

<style scoped>
.photo,
.doc,
.chipf,
.notec {
    background: var(--card);
    border: 1px solid var(--card-line);
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
    cursor: grab;
}
.photo {
    width: 154px;
    height: 150px;
    border-radius: 22px;
    padding: 6px;
}
.photo .img {
    height: 116px;
    border-radius: 17px;
    background: var(--img-bg) center / cover no-repeat;
    display: grid;
    place-items: center;
}
.photo .img img {
    width: 21px;
    height: 18.7px;
}
.cap {
    display: block;
    margin-top: 7px;
    text-align: center;
    font-size: 12.5px;
    color: var(--soft);
}
.doc {
    width: 170px;
    height: 64px;
    border-radius: 22px;
    padding: 12px;
    display: flex;
    align-items: center;
    gap: 10px;
}
.ico {
    width: 38px;
    height: 38px;
    border-radius: 12px;
    background: var(--ico-bg);
    display: grid;
    place-items: center;
    flex: none;
}
.ico img {
    width: 11.7px;
    height: 15px;
}
.txt {
    display: grid;
    gap: 4px;
    min-width: 0;
}
.txt b {
    font-weight: 600;
    font-size: 13px;
    line-height: 16px;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.txt i {
    font-style: normal;
    font-size: 11.5px;
    line-height: 14px;
    color: var(--soft);
}
.chipf {
    height: 33px;
    border-radius: 17px;
    padding: 0 12px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    max-width: 170px;
}
.chipf img {
    width: 13px;
    height: 13px;
    flex: none;
}
.chipf b {
    font-weight: 600;
    font-size: 13px;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.notec {
    width: 190px;
    border-radius: 20px;
    padding: 11px 13px;
    display: flex;
    gap: 9px;
    align-items: flex-start;
    background: var(--note-bg);
    border-color: var(--note-line);
}
.note-icon {
    width: 17px;
    height: 17px;
    flex: none;
    color: var(--ink);
    display: grid;
    place-items: center;
}
.note-icon :deep(svg) {
    width: 100%;
    height: 100%;
}
.notec p {
    margin: 0;
    font-size: 13px;
    line-height: 17px;
    color: var(--ink);
    white-space: pre-line;
    overflow-wrap: anywhere;
    display: -webkit-box;
    -webkit-line-clamp: 6;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
</style>
